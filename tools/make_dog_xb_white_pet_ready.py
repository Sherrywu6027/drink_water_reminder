from collections import deque
from pathlib import Path
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "archive" / "desktop_pets_removed_20260812" / "dog_XB"
OUT_DIR = ROOT / "assets" / "desktop_pets" / "dog_XB_white_pet_ready"
MAX_SOURCE_EDGE = 768
OUTPUT_SIZE = 384


def resize_for_processing(image):
    image = image.convert("RGBA")
    max_edge = max(image.size)
    if max_edge <= MAX_SOURCE_EDGE:
        return image
    scale = MAX_SOURCE_EDGE / max_edge
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def is_black_line(r, g, b, a):
    if a == 0:
        return False
    return max(r, g, b) <= 90


def is_background_candidate(r, g, b, a):
    if a == 0:
        return True
    brightness = (r + g + b) / 3
    spread = max(r, g, b) - min(r, g, b)
    # The source dog images contain a baked gray/white checkerboard.  The dog
    # itself is also white, so the flood fill must rely on the black outline as
    # a barrier instead of deleting all white pixels globally.
    return brightness >= 185 and spread <= 45


def find_edge_background(image):
    width, height = image.size
    pix = image.load()
    visited = set()
    queue = deque()

    def add_if_bg(x, y):
        if (x, y) in visited:
            return
        rgba = pix[x, y]
        if is_black_line(*rgba):
            return
        if is_background_candidate(*rgba):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(width):
        add_if_bg(x, 0)
        add_if_bg(x, height - 1)
    for y in range(height):
        add_if_bg(0, y)
        add_if_bg(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                add_if_bg(nx, ny)
    return visited


def cutout(src, dst):
    image = resize_for_processing(Image.open(src))
    background = find_edge_background(image)
    pix = image.load()
    for x, y in background:
        r, g, b, a = pix[x, y]
        pix[x, y] = (r, g, b, 0)

    # Remove isolated checkerboard crumbs created by antialiasing/resizing while
    # keeping the white dog body intact.
    alpha = image.getchannel("A").filter(ImageFilter.MedianFilter(3))
    image.putalpha(alpha)

    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    image.thumbnail((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((OUTPUT_SIZE - image.size[0]) // 2, (OUTPUT_SIZE - image.size[1]) // 2),
    )
    canvas.save(dst)
    return len(background), canvas.size


def main():
    if not SRC_DIR.is_dir():
        raise SystemExit("source directory not found: {}".format(SRC_DIR))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC_DIR.glob("*.png")):
        removed, size = cutout(src, OUT_DIR / src.name)
        print(src.name, "removed", removed, "size", size)


if __name__ == "__main__":
    main()

from collections import deque
from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("dog_XB", "dog_XJM", "capybara")
MAX_SOURCE_EDGE = 512
OUTPUT_SIZE = 384


def is_edge_background(r, g, b, a):
    if a == 0:
        return True
    brightness = (r + g + b) / 3
    spread = max(r, g, b) - min(r, g, b)
    # Only pixels connected to the image edge are considered by the flood-fill
    # caller. This threshold intentionally covers baked checkerboard/near-white
    # canvas backgrounds while preserving enclosed white details in the pet.
    return brightness >= 210 and spread <= 38


def resize_for_processing(image):
    image = image.convert("RGBA")
    max_edge = max(image.size)
    if max_edge <= MAX_SOURCE_EDGE:
        return image
    scale = MAX_SOURCE_EDGE / max_edge
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.LANCZOS)


def find_edge_background(image):
    width, height = image.size
    pix = image.load()
    visited = set()
    queue = deque()

    def add_if_bg(x, y):
        if (x, y) in visited:
            return
        if is_edge_background(*pix[x, y]):
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
    base = ROOT / "assets" / "desktop_pets"
    for target in TARGETS:
        src_dir = base / target
        dst_dir = base / f"{target}_pet_ready"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.glob("*.png")):
            removed, size = cutout(src, dst_dir / src.name)
            print(target, src.name, "removed", removed, "size", size)


if __name__ == "__main__":
    main()

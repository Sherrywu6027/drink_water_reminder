from collections import deque
from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("dog_XB", "dog_XJM")


def is_edge_background(r, g, b, a):
    if a == 0:
        return True
    brightness = (r + g + b) / 3
    spread = max(r, g, b) - min(r, g, b)
    return brightness >= 236 and spread <= 30


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
    image = Image.open(src).convert("RGBA")
    background = find_edge_background(image)
    pix = image.load()
    for x, y in background:
        r, g, b, a = pix[x, y]
        pix[x, y] = (r, g, b, 0)
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    canvas_size = max(image.size[0], image.size[1], 256)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((canvas_size - image.size[0]) // 2, (canvas_size - image.size[1]) // 2),
    )
    canvas.save(dst)
    return len(background), canvas.size


def main():
    base = ROOT / "assets" / "desktop_pets"
    for target in TARGETS:
        src_dir = base / target
        dst_dir = base / f"{target}_transparent_edge"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src in sorted(src_dir.glob("*.png")):
            removed, size = cutout(src, dst_dir / src.name)
            print(target, src.name, "removed", removed, "size", size)


if __name__ == "__main__":
    main()

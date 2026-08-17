from collections import deque
from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "archive" / "eye_duck_original_png_20260811"
OUT_DIR = ROOT / "assets" / "desktop_pets" / "eye_duck"


def is_background_candidate(r, g, b):
    brightness = (r + g + b) / 3
    spread = max(r, g, b) - min(r, g, b)
    # Only very light neutral pixels are eligible, and only if connected to an edge.
    return brightness >= 238 and spread <= 22


def connected_background_mask(image):
    width, height = image.size
    rgba = image.convert("RGBA")
    pix = rgba.load()
    visited = set()
    queue = deque()

    def try_add(x, y):
        if (x, y) in visited:
            return
        r, g, b, a = pix[x, y]
        if a == 0 or is_background_candidate(r, g, b):
            visited.add((x, y))
            queue.append((x, y))

    for x in range(width):
        try_add(x, 0)
        try_add(x, height - 1)
    for y in range(height):
        try_add(0, y)
        try_add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < width and 0 <= ny < height:
                try_add(nx, ny)

    return visited


def apply_cutout(src, out):
    image = Image.open(src).convert("RGBA")
    mask = connected_background_mask(image)
    pix = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            if (x, y) in mask:
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
    canvas.save(out)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC_DIR.glob("*.png")):
        out = OUT_DIR / src.name
        apply_cutout(src, out)
        print(src.name)


if __name__ == "__main__":
    main()

from collections import deque
from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "archive" / "eye_duck_bad_white_cutout_20260811"
OUT_DIR = ROOT / "assets" / "desktop_pets" / "eye_duck"


def edge_connected_transparent(image):
    width, height = image.size
    pix = image.load()
    visited = set()
    queue = deque()

    def transparentish(x, y):
        return pix[x, y][3] < 255

    def try_add(x, y):
        if (x, y) in visited:
            return
        if transparentish(x, y):
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


def repair(src, out):
    image = Image.open(src).convert("RGBA")
    background = edge_connected_transparent(image)
    pix = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pix[x, y]
            if a < 255 and (x, y) not in background:
                pix[x, y] = (r, g, b, 255)
            elif (x, y) in background:
                pix[x, y] = (r, g, b, 0)
    image.save(out)


def main():
    for src in sorted(SRC_DIR.glob("*.png")):
        out = OUT_DIR / src.name
        repair(src, out)
        print(src.name)


if __name__ == "__main__":
    main()

from pathlib import Path
from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "assets" / "desktop_pets" / "dog_XTM"
OUT_DIR = ROOT / "assets" / "desktop_pets" / "dog_XB_white_pet_ready"


def make_white_dog(src, dst):
    image = Image.open(src).convert("RGBA")
    alpha = image.getchannel("A")

    # Expand the black outline slightly to close small gaps, then fill the
    # inside area.  This reconstructs the white body for a white dog whose
    # original background was also white/checkerboard.
    outline = alpha.point(lambda a: 255 if a > 20 else 0).filter(ImageFilter.MaxFilter(7))
    outside = Image.new("L", image.size, 0)
    outside.paste(255, (0, 0, image.width, 1))
    outside.paste(255, (0, image.height - 1, image.width, image.height))
    outside.paste(255, (0, 0, 1, image.height))
    outside.paste(255, (image.width - 1, 0, image.width, image.height))

    # Flood fill edge-connected transparent area without crossing the outline.
    outside_pixels = outside.load()
    outline_pixels = outline.load()
    stack = []
    for x in range(image.width):
        stack.append((x, 0))
        stack.append((x, image.height - 1))
    for y in range(image.height):
        stack.append((0, y))
        stack.append((image.width - 1, y))

    while stack:
        x, y = stack.pop()
        if not (0 <= x < image.width and 0 <= y < image.height):
            continue
        if outside_pixels[x, y] == 128:
            continue
        if outline_pixels[x, y] > 0:
            continue
        outside_pixels[x, y] = 128
        stack.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))

    inside = Image.new("L", image.size, 0)
    inside_pixels = inside.load()
    for y in range(image.height):
        for x in range(image.width):
            if outside_pixels[x, y] != 128:
                inside_pixels[x, y] = 255

    result = Image.new("RGBA", image.size, (255, 255, 255, 255))
    result.putalpha(inside.filter(ImageFilter.GaussianBlur(0.6)))
    result.alpha_composite(image)
    dst.parent.mkdir(parents=True, exist_ok=True)
    result.save(dst)


def main():
    if not SRC_DIR.is_dir():
        raise SystemExit("source directory not found: {}".format(SRC_DIR))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC_DIR.glob("*.png")):
        make_white_dog(src, OUT_DIR / src.name)
        print("WROTE", OUT_DIR / src.name)


if __name__ == "__main__":
    main()

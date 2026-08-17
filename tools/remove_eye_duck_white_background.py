from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PET_DIR = ROOT / "assets" / "desktop_pets" / "eye_duck"


def whiteness_alpha(r, g, b):
    # Treat near-white and very light gray-green pixels as background.
    brightness = (r + g + b) / 3
    color_spread = max(r, g, b) - min(r, g, b)
    if brightness >= 248 and color_spread <= 18:
        return 0
    if brightness >= 242 and color_spread <= 12:
        return 40
    if brightness >= 235 and color_spread <= 9:
        return 120
    return 255


def process(path):
    image = Image.open(path).convert("RGBA")
    pixels = []
    for r, g, b, a in image.getdata():
        new_alpha = min(a, whiteness_alpha(r, g, b))
        pixels.append((r, g, b, new_alpha))
    image.putdata(pixels)
    # Trim fully transparent border, then place on square transparent canvas
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    canvas_size = max(image.size[0], image.size[1], 256)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - image.size[0]) // 2
    y = (canvas_size - image.size[1]) // 2
    canvas.alpha_composite(image, (x, y))
    canvas.save(path)


def main():
    for path in sorted(PET_DIR.glob("*.png")):
        process(path)
        print(path.name)


if __name__ == "__main__":
    main()

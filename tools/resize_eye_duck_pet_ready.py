from pathlib import Path
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "assets" / "desktop_pets" / "eye_duck"
OUT_DIR = ROOT / "assets" / "desktop_pets" / "eye_duck_pet_ready"
OUTPUT_SIZE = 384


def resize_pet_image(src, dst):
    image = Image.open(src).convert("RGBA")
    image.thumbnail((OUTPUT_SIZE, OUTPUT_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (OUTPUT_SIZE, OUTPUT_SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(
        image,
        ((OUTPUT_SIZE - image.width) // 2, (OUTPUT_SIZE - image.height) // 2),
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dst, optimize=True)
    print("WROTE", dst)


def main():
    if not SRC_DIR.is_dir():
        raise SystemExit("source directory not found: {}".format(SRC_DIR))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(SRC_DIR.glob("*.png")):
        resize_pet_image(src, OUT_DIR / src.name)


if __name__ == "__main__":
    main()

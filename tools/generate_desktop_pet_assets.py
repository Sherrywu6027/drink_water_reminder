from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "desktop_pets"
SIZE = 256

PETS = {
    "water_sprite": ("#2f80ed", "#85c1ff", "#d9efff"),
    "eye_cat": ("#7b61ff", "#c7b8ff", "#efeaff"),
    "active_bear": ("#f2994a", "#ffd199", "#fff0d8"),
    "stand_penguin": ("#145A32", "#6fcf97", "#f2fff7"),
}


def ellipse(draw, box, fill, outline=None, width=1):
    draw.ellipse(box, fill=fill, outline=outline, width=width)


def draw_pet(pet_id, colors, pose):
    body, accent, belly = colors
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = -8 if pose == "happy" else (0 if pose == "idle_0" else -4)
    arm = -28 if pose == "happy" else (-8 if pose == "idle_1" else 0)

    d.ellipse((58, 224, 198, 242), fill=(0, 0, 0, 38))

    if pet_id == "eye_cat":
        d.polygon([(70, 62 + bob), (91, 18 + bob), (112, 70 + bob)], fill=accent, outline=body)
        d.polygon([(144, 70 + bob), (165, 18 + bob), (186, 62 + bob)], fill=accent, outline=body)
    elif pet_id == "active_bear":
        ellipse(d, (52, 54 + bob, 94, 96 + bob), accent, body, 5)
        ellipse(d, (162, 54 + bob, 204, 96 + bob), accent, body, 5)
    elif pet_id == "water_sprite":
        d.polygon([(128, 20 + bob), (78, 96 + bob), (178, 96 + bob)], fill=accent, outline=body)

    if pet_id == "stand_penguin":
        ellipse(d, (61, 46 + bob, 195, 216 + bob), body, "#0b3520", 6)
        ellipse(d, (91, 104 + bob, 165, 204 + bob), belly)
    else:
        ellipse(d, (72, 116 + bob, 184, 218 + bob), body, "#1f3b2f", 5)
        ellipse(d, (58, 62 + bob, 198, 176 + bob), body, "#1f3b2f", 5)
        ellipse(d, (96, 136 + bob, 160, 208 + bob), belly)

    d.line([(76, 142 + bob), (34, 170 + bob + arm)], fill=body, width=16)
    d.line([(180, 142 + bob), (222, 170 + bob - arm)], fill=body, width=16)
    ellipse(d, (22, 160 + bob + arm, 50, 188 + bob + arm), accent, body, 3)
    ellipse(d, (206, 160 + bob - arm, 234, 188 + bob - arm), accent, body, 3)

    if pose == "happy":
        d.arc((84, 100 + bob, 110, 124 + bob), 20, 160, fill="#17221d", width=4)
        d.arc((146, 100 + bob, 172, 124 + bob), 20, 160, fill="#17221d", width=4)
        d.arc((104, 122 + bob, 152, 164 + bob), 20, 160, fill="#17221d", width=5)
    else:
        ellipse(d, (84, 100 + bob, 104, 120 + bob), "#17221d")
        ellipse(d, (152, 100 + bob, 172, 120 + bob), "#17221d")
        ellipse(d, (90, 104 + bob, 96, 110 + bob), "#ffffff")
        ellipse(d, (158, 104 + bob, 164, 110 + bob), "#ffffff")
        d.arc((108, 120 + bob, 148, 150 + bob), 20, 160, fill="#17221d", width=4)

    ellipse(d, (62, 126 + bob, 88, 144 + bob), "#ffb3c1")
    ellipse(d, (168, 126 + bob, 194, 144 + bob), "#ffb3c1")
    ellipse(d, (80, 210 + bob, 116, 236 + bob), accent, body, 3)
    ellipse(d, (140, 210 + bob, 176, 236 + bob), accent, body, 3)

    if pet_id == "water_sprite":
        ellipse(d, (156, 78 + bob, 178, 96 + bob), "#ffffff")
    elif pet_id == "active_bear":
        ellipse(d, (120, 122 + bob, 136, 138 + bob), "#6b3d1d")
    elif pet_id == "stand_penguin":
        d.polygon([(119, 124 + bob), (137, 124 + bob), (128, 142 + bob)], fill="#f2c94c")

    return img


def main():
    for pet_id, colors in PETS.items():
        pet_dir = OUT / pet_id
        pet_dir.mkdir(parents=True, exist_ok=True)
        for pose in ("idle_0", "idle_1", "happy"):
            draw_pet(pet_id, colors, pose).save(pet_dir / f"{pose}.png")


if __name__ == "__main__":
    main()

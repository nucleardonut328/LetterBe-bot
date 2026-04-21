"""
PhotoLetters Image Processor
"""

from PIL import Image, ImageDraw, ImageFont
import io
import os
from typing import List

CANVAS_W = 1600
CANVAS_H = 520

FONTS_CONFIG = {
    "impact": {"name": "Impact", "size_mult": 1.0},
    "arial_black": {"name": "Arial Black", "size_mult": 0.95},
    "bebas": {"name": "Bebas Neue", "size_mult": 1.05},
    "teko": {"name": "Teko", "size_mult": 1.1},
}


def _find_system_font() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def get_font(font_id: str, size: int) -> ImageFont.FreeTypeFont:
    font_path = _find_system_font()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def compress_image(image_bytes: bytes, max_width: int = 1200) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    scale = min(1.0, max_width / img.width)
    if scale < 1.0:
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=82)
    output.seek(0)
    return output.getvalue()


def create_collage(
    photos: List[bytes],
    word: str,
    font_id: str = "impact",
    bg_color: str = "#000000",
    size_scale: float = 1.0
) -> bytes:
    word = word.upper().strip()
    if not word or len(word) > 8:
        raise ValueError("Слово должно содержать 1-8 букв")
    if len(photos) != len(word):
        raise ValueError(f"Фото: {len(photos)}, букв: {len(word)} — должно совпадать")

    try:
        bg_rgb = tuple(int(bg_color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        bg_rgb = (0, 0, 0)

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*bg_rgb, 255))

    letter_w = CANVAS_W / len(word)
    config = FONTS_CONFIG.get(font_id, FONTS_CONFIG["impact"])
    font_size = int(CANVAS_H * 0.96 * size_scale * config["size_mult"])
    font = get_font(font_id, font_size)

    for i, (letter, photo_bytes) in enumerate(zip(word, photos)):
        lx = i * letter_w
        temp = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

        if photo_bytes:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
                scale = max(letter_w / img.width, CANVAS_H / img.height)
                scaled_w = int(img.width * scale)
                scaled_h = int(img.height * scale)
                img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                offset_x = int(lx + (letter_w - scaled_w) / 2)
                offset_y = int((CANVAS_H - scaled_h) / 2)
                temp.paste(img, (offset_x, offset_y), img)
            except Exception as e:
                print(f"[WARN] Ошибка фото {i}: {e}")

        mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
        draw = ImageDraw.Draw(mask)
        draw.text(
            (int(lx + letter_w / 2), int(CANVAS_H / 2)),
            letter,
            fill=255,
            font=font,
            anchor="mm"
        )

        temp.putalpha(mask)
        canvas = Image.alpha_composite(canvas, temp)

    final = Image.new("RGB", (CANVAS_W, CANVAS_H), bg_rgb)
    final.paste(canvas, mask=canvas.split()[3])

    output = io.BytesIO()
    final.save(output, format="PNG")
    output.seek(0)
    return output.getvalue()

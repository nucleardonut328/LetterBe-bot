"""
PhotoLetters Image Processor
"""

from PIL import Image, ImageDraw, ImageFont
import io
import os
import urllib.request
import urllib.error
from typing import List

# A4 формат в пикселях при 300 DPI (стандарт для печати)
CANVAS_W = 3508  # ~A4 ширина
CANVAS_H = 2480  # ~A4 высота

FONTS_CONFIG = {
    "impact": {"name": "Impact", "size_mult": 1.0},
    "arial_black": {"name": "Arial Black", "size_mult": 0.95},
    "bebas": {"name": "Bebas Neue", "size_mult": 1.05},
    "teko": {"name": "Teko", "size_mult": 1.1},
}

# Локальный кэш шрифта (рядом со скриптом)
_FALLBACK_FONT_PATH = os.path.join(os.path.dirname(__file__), "fallback_font.ttf")

# URL надёжного жирного шрифта с GitHub
_FALLBACK_FONT_URL = (
    "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/"
    "ttf/DejaVuSans-Bold.ttf"
)


def _find_system_font() -> str | None:
    """
    Ищет подходящий TTF-шрифт в системе.
    Если ничего не найдено — скачивает DejaVuSans-Bold и кэширует рядом со скриптом.
    Возвращает путь к файлу шрифта или None если всё провалилось.
    """
    candidates = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        # Windows
        "C:\\Windows\\Fonts\\impact.ttf",
        "C:\\Windows\\Fonts\\ariblk.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        # Локальный кэш
        _FALLBACK_FONT_PATH,
    ]

    for path in candidates:
        if os.path.exists(path):
            print(f"[INFO] Используется шрифт: {path}")
            return path

    # Ничего не нашли — скачиваем
    print("[INFO] Системный шрифт не найден. Скачиваю fallback-шрифт...")
    try:
        urllib.request.urlretrieve(_FALLBACK_FONT_URL, _FALLBACK_FONT_PATH)
        print(f"[INFO] Шрифт успешно загружен: {_FALLBACK_FONT_PATH}")
        return _FALLBACK_FONT_PATH
    except Exception as e:
        print(f"[ERROR] Не удалось скачать шрифт: {e}")
        return None


def get_font(font_id: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Возвращает TrueType-шрифт нужного размера.
    Если шрифт не найден и не удалось скачать — возвращает default (маска не сработает!).
    """
    font_path = _find_system_font()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            print(f"[WARN] Не удалось загрузить шрифт {font_path}: {e}")

    print("[WARN] Используется default font — буквы могут не отображаться корректно!")
    return ImageFont.load_default()


def _draw_letter_on_mask(
    draw: ImageDraw.ImageDraw,
    letter: str,
    font: ImageFont.FreeTypeFont,
    cx: int,
    cy: int,
) -> None:
    """
    Рисует букву по центру (cx, cy) на маске.
    Пробует anchor='mm' (только TrueType), при ошибке — ручное центрирование.
    """
    try:
        draw.text((cx, cy), letter, fill=255, font=font, anchor="mm")
    except Exception as e:
        print(f"[WARN] anchor='mm' не поддерживается ({e}), считаю bbox вручную")
        try:
            bbox = font.getbbox(letter)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            draw.text((cx - tw // 2, cy - th // 2), letter, fill=255, font=font)
        except Exception as e2:
            print(f"[ERROR] Не удалось нарисовать букву '{letter}': {e2}")
            # Аварийный вариант — рисуем в центр без поправки
            draw.text((cx, cy), letter, fill=255, font=font)


def compress_image(image_bytes: bytes, max_width: int = 2400) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    scale = min(1.0, max_width / img.width)
    if scale < 1.0:
        new_size = (int(img.width * scale), int(img.height * scale))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85)
    output.seek(0)
    return output.getvalue()


def create_collage(
    photos: List[bytes],
    word: str,
    font_id: str = "impact",
    bg_color: str = "#000000",
    size_scale: float = 1.0,
) -> bytes:
    word = word.upper().strip()
    if not word or len(word) > 8:
        raise ValueError("Слово должно содержать 1-8 букв")
    if len(photos) != len(word):
        raise ValueError(
            f"Фото: {len(photos)}, букв: {len(word)} — должно совпадать"
        )

    # Парсим цвет фона
    try:
        bg_rgb = tuple(int(bg_color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        bg_rgb = (0, 0, 0)

    # Основной холст
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg_rgb)

    letter_w = CANVAS_W / len(word)
    config = FONTS_CONFIG.get(font_id, FONTS_CONFIG["impact"])

    # Шрифт на 90% высоты холста с учётом масштаба и конфига шрифта
    font_size = int(CANVAS_H * 0.90 * size_scale * config["size_mult"])
    font = get_font(font_id, font_size)

    print(f"[INFO] Создаю коллаж: слово='{word}', шрифт={font_id}, "
          f"font_size={font_size}, bg={bg_color}")

    for i, (letter, photo_bytes) in enumerate(zip(word, photos)):
        lx = int(i * letter_w)

        # ── Слой с фотографией ──────────────────────────────────────────────
        photo_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

        if photo_bytes:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")

                # Масштабируем чтобы фото заполнило ширину колонки буквы
                scale = max(letter_w / img.width, CANVAS_H / img.height)
                scaled_w = int(img.width * scale)
                scaled_h = int(img.height * scale)
                img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

                offset_x = int(lx + (letter_w - scaled_w) / 2)
                offset_y = int((CANVAS_H - scaled_h) / 2)
                photo_layer.paste(img, (offset_x, offset_y), img)

            except Exception as e:
                print(f"[WARN] Ошибка при загрузке фото #{i} ('{letter}'): {e}")

        # ── Маска в форме буквы ─────────────────────────────────────────────
        mask = Image.new("L", (CANVAS_W, CANVAS_H), 0)
        draw = ImageDraw.Draw(mask)

        cx = int(lx + letter_w / 2)
        cy = int(CANVAS_H / 2)
        _draw_letter_on_mask(draw, letter, font, cx, cy)

        # ── Применяем маску и вставляем на холст ────────────────────────────
        photo_layer.putalpha(mask)
        canvas.paste(photo_layer, (0, 0), photo_layer)

    # Сохраняем результат
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    output.seek(0)
    print("[INFO] Коллаж готов ✓")
    return output.getvalue()

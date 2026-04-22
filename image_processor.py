"""
PhotoLetters Image Processor
"""

from PIL import Image, ImageDraw, ImageFont
import io
import os
import urllib.request
from typing import List, Optional

# A4 формат в пикселях при 300 DPI
CANVAS_W = 3508
CANVAS_H = 2480

FONTS_CONFIG = {
    "impact":      {"name": "Impact",      "size_mult": 1.0},
    "arial_black": {"name": "Arial Black", "size_mult": 0.95},
    "bebas":       {"name": "Bebas Neue",  "size_mult": 1.05},
    "teko":        {"name": "Teko",        "size_mult": 1.1},
}

# Куда кэшируем скачанный шрифт
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FALLBACK_FONT_PATH = os.path.join(_SCRIPT_DIR, "fallback_font.ttf")

# Несколько источников на случай если один недоступен
_FONT_URLS = [
    "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf",
    "https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/ttf/DejaVuSans-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ufl/ubuntu/Ubuntu-Bold.ttf",
]

# Системные пути к шрифтам
_SYSTEM_FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    # Windows
    "C:\\Windows\\Fonts\\impact.ttf",
    "C:\\Windows\\Fonts\\ariblk.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    # Кэш рядом со скриптом
    _FALLBACK_FONT_PATH,
]

# Глобальный кэш найденного пути — чтобы не искать каждый раз
_resolved_font_path: Optional[str] = None


def _verify_font(font_path: str, test_size: int = 200) -> bool:
    """
    Проверяем что шрифт реально работает:
    загружаем и рисуем букву, затем проверяем что на маске есть белые пиксели.
    """
    try:
        font = ImageFont.truetype(font_path, test_size)
        test_img = Image.new("L", (400, 400), 0)
        draw = ImageDraw.Draw(test_img)
        try:
            draw.text((200, 200), "A", fill=255, font=font, anchor="mm")
        except Exception:
            bbox = font.getbbox("A")
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((200 - tw // 2, 200 - th // 2), "A", fill=255, font=font)
        result = test_img.getbbox() is not None
        print(f"[INFO] Верификация шрифта {font_path}: {'OK' if result else 'FAIL (пустая маска)'}")
        return result
    except Exception as e:
        print(f"[WARN] Верификация шрифта {font_path} провалилась: {e}")
        return False


def _download_font() -> Optional[str]:
    """Скачивает шрифт из списка URL, возвращает путь или None."""
    for url in _FONT_URLS:
        try:
            print(f"[INFO] Скачиваю шрифт: {url}")
            urllib.request.urlretrieve(url, _FALLBACK_FONT_PATH)
            if _verify_font(_FALLBACK_FONT_PATH):
                print(f"[INFO] Шрифт успешно загружен: {_FALLBACK_FONT_PATH}")
                return _FALLBACK_FONT_PATH
            else:
                print(f"[WARN] Скачанный файл не прошёл верификацию, пробую следующий URL")
                try:
                    os.remove(_FALLBACK_FONT_PATH)
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Не удалось скачать с {url}: {e}")
    return None


def _find_font() -> Optional[str]:
    """
    Ищет рабочий TTF шрифт:
    1. Проверяет глобальный кэш
    2. Проверяет системные пути (с верификацией)
    3. Скачивает если не нашёл
    """
    global _resolved_font_path

    # Используем кэш
    if _resolved_font_path and os.path.exists(_resolved_font_path):
        return _resolved_font_path

    # Ищем среди системных путей
    for path in _SYSTEM_FONT_CANDIDATES:
        if os.path.exists(path):
            if _verify_font(path):
                print(f"[INFO] Найден рабочий шрифт: {path}")
                _resolved_font_path = path
                return path
            else:
                print(f"[WARN] Шрифт найден но не работает: {path}")

    # Скачиваем
    print("[INFO] Системный шрифт не найден — скачиваю...")
    path = _download_font()
    if path:
        _resolved_font_path = path
        return path

    print("[ERROR] Не удалось найти или скачать шрифт!")
    return None


def get_font(font_id: str, size: int) -> Optional[ImageFont.FreeTypeFont]:
    """Возвращает TrueType-шрифт нужного размера или None."""
    font_path = _find_font()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            print(f"[ERROR] Не удалось загрузить шрифт {font_path} size={size}: {e}")
    return None


def _draw_letter_mask(
    canvas_size: tuple,
    letter: str,
    font: ImageFont.FreeTypeFont,
    lx: float,
    letter_w: float,
) -> Image.Image:
    """
    Рисует маску в форме буквы, центрируя её внутри колонки [lx, lx+letter_w].
    Пробует три метода по убыванию надёжности.
    """
    cx = int(lx + letter_w / 2)
    cy = canvas_size[1] // 2

    # Метод 1: anchor="mm" (Pillow 8+, только TrueType)
    try:
        mask = Image.new("L", canvas_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.text((cx, cy), letter, fill=255, font=font, anchor="mm")
        if mask.getbbox() is not None:
            return mask
        print(f"[WARN] anchor='mm' ничего не нарисовал для '{letter}'")
    except Exception as e:
        print(f"[WARN] anchor='mm' упал ({e}), пробую getbbox")

    # Метод 2: ручное центрирование через getbbox
    try:
        mask = Image.new("L", canvas_size, 0)
        draw = ImageDraw.Draw(mask)
        bbox = font.getbbox(letter)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), letter, fill=255, font=font)
        if mask.getbbox() is not None:
            return mask
        print(f"[WARN] getbbox-центрирование ничего не нарисовало для '{letter}'")
    except Exception as e:
        print(f"[WARN] getbbox упал ({e}), пробую getlength")

    # Метод 3: getlength (Pillow 9.2+)
    try:
        mask = Image.new("L", canvas_size, 0)
        draw = ImageDraw.Draw(mask)
        tw = int(font.getlength(letter))
        th = int(font.size * 0.75) if hasattr(font, "size") else int(canvas_size[1] * 0.5)
        draw.text((cx - tw // 2, cy - th // 2), letter, fill=255, font=font)
        return mask
    except Exception as e:
        print(f"[ERROR] Все методы рисования буквы '{letter}' провалились: {e}")
        return Image.new("L", canvas_size, 0)


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
        raise ValueError(f"Фото: {len(photos)}, букв: {len(word)} — должно совпадать")

    # Парсим цвет фона
    try:
        hex_color = bg_color.lstrip("#")
        bg_rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        bg_rgb = (0, 0, 0)

    # Загружаем шрифт
    config = FONTS_CONFIG.get(font_id, FONTS_CONFIG["impact"])
    font_size = int(CANVAS_H * 0.90 * size_scale * config["size_mult"])
    font = get_font(font_id, font_size)

    if font is None:
        raise RuntimeError(
            "Не удалось загрузить шрифт.\n"
            "Решение 1 (Docker/Linux): apt-get install -y fonts-dejavu-core\n"
            "Решение 2: положи файл DejaVuSans-Bold.ttf рядом со скриптом "
            "и переименуй в fallback_font.ttf"
        )

    print(
        f"[INFO] Создаю коллаж: слово='{word}', шрифт={font_id}, "
        f"font_size={font_size}, bg={bg_color}"
    )

    # Основной холст
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), bg_rgb)
    letter_w = CANVAS_W / len(word)

    for i, (letter, photo_bytes) in enumerate(zip(word, photos)):
        lx = i * letter_w

        # ── Слой с фотографией ──────────────────────────────────────────────
        photo_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))

        if photo_bytes:
            try:
                img = Image.open(io.BytesIO(photo_bytes)).convert("RGBA")
                scale = max(letter_w / img.width, CANVAS_H / img.height)
                scaled_w = int(img.width * scale)
                scaled_h = int(img.height * scale)
                img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                offset_x = int(lx + (letter_w - scaled_w) / 2)
                offset_y = int((CANVAS_H - scaled_h) / 2)
                photo_layer.paste(img, (offset_x, offset_y), img)
                print(f"[INFO] Фото #{i} ('{letter}') загружено OK")
            except Exception as e:
                print(f"[ERROR] Ошибка при загрузке фото #{i} ('{letter}'): {e}")

        # ── Маска в форме буквы ─────────────────────────────────────────────
        mask = _draw_letter_mask((CANVAS_W, CANVAS_H), letter, font, lx, letter_w)

        mask_bbox = mask.getbbox()
        if mask_bbox is None:
            print(f"[ERROR] Маска для '{letter}' пустая — буква не отобразится!")
        else:
            print(f"[INFO] Маска '{letter}' OK bbox={mask_bbox}")

        # ── Применяем маску и вставляем на холст ────────────────────────────
        photo_layer.putalpha(mask)
        canvas.paste(photo_layer, (0, 0), photo_layer)

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    output.seek(0)
    print("[INFO] Коллаж готов ✓")
    return output.getvalue()

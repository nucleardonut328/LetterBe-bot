"""
PhotoLetters Telegram Bot — Webhook через aiohttp для Render
"""

import logging
import os
import sys
import asyncio

from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from image_processor import create_collage, compress_image

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

if not TELEGRAM_TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
    sys.exit(1)

MAX_PHOTOS = 8

CHOOSE_ACTION, ENTER_WORD, UPLOAD_PHOTOS, CHOOSE_FONT, CHOOSE_COLOR = range(5)

user_sessions = {}

MAIN_KB = ReplyKeyboardMarkup(
    [["📸 Создать коллаж"], ["❌ Отмена"]],
    one_time_keyboard=True, resize_keyboard=True,
)

FONT_KB = ReplyKeyboardMarkup(
    [["Impact", "Arial Black"], ["Bebas Neue", "Teko"], ["❌ Отмена"]],
    one_time_keyboard=True, resize_keyboard=True,
)

COLOR_KB = ReplyKeyboardMarkup(
    [["⬛ Чёрный", "🟫 Тёмный"], ["🟦 Синий", "🟥 Красный"], ["❌ Отмена"]],
    one_time_keyboard=True, resize_keyboard=True,
)

FONT_MAP = {
    "Impact": "impact", "Arial Black": "arial_black",
    "Bebas Neue": "bebas", "Teko": "teko",
}

COLOR_MAP = {
    "⬛ Чёрный": "#000000", "🟫 Тёмный": "#0d1117",
    "🟦 Синий": "#0a0a1f", "🟥 Красный": "#1a0a00",
}

def _reset_user(user_id: int):
    user_sessions[user_id] = {
        "photos": [], "word": "", "font": "impact", "bg_color": "#000000",
    }

def _cleanup_user(user_id: int):
    user_sessions.pop(user_id, None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    _reset_user(user_id)
    await update.message.reply_text(
        "👋 Привет! Я бот *PhotoLetters*.\n\n"
        "Я создаю коллажи из твоих фотографий в форме букв слова.\n\n"
        "Например, отправишь слово *LOVE* + 4 фото — получишь красивый коллаж!",
        parse_mode="Markdown", reply_markup=MAIN_KB,
    )
    return CHOOSE_ACTION

async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    user_id = update.effective_user.id
    if text == "📸 Создать коллаж":
        await update.message.reply_text(
            "📝 Введи слово (только буквы, макс. 8 символов):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ENTER_WORD
    if text in ("❌ Отмена", "/cancel"):
        return await cancel(update, context)
    await update.message.reply_text("Используй кнопки ниже 👇", reply_markup=MAIN_KB)
    return CHOOSE_ACTION

async def enter_word(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    if not text.isalpha() or len(text) > MAX_PHOTOS:
        await update.message.reply_text("❌ Только буквы, 1–8 символов. Попробуй ещё раз:")
        return ENTER_WORD
    user_sessions[user_id]["word"] = text
    word_len = len(text)
    await update.message.reply_text(
        f'✅ Слово: *{text}*\n\n'
        f'📸 Отправь *{word_len}* фото (по одному).\n'
        f'Первое — для *{text[0]}*, второе — для *{text[1]}* и т.д.',
        parse_mode="Markdown",
    )
    return UPLOAD_PHOTOS

async def upload_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text("Сессия устарела. Начни с /start")
        return ConversationHandler.END
    word = session["word"]
    word_len = len(word)
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправь фото (не файл).")
        return UPLOAD_PHOTOS
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    if file.file_size and file.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("❌ Фото слишком большое (> 10MB).")
        return UPLOAD_PHOTOS
    photo_bytes = await file.download_as_bytearray()
    try:
        compressed = compress_image(bytes(photo_bytes))
        session["photos"].append(compressed)
    except Exception as e:
        logger.warning(f"Ошибка сжатия: {e}")
        session["photos"].append(bytes(photo_bytes))
    received = len(session["photos"])
    remaining = word_len - received
    if remaining > 0:
        await update.message.reply_text(
            f'✅ Принято *{received}/{word_len}*\n'
            f'📸 Отправь ещё *{remaining}* (следующая: *{word[received]}*)',
            parse_mode="Markdown",
        )
        return UPLOAD_PHOTOS
    await update.message.reply_text(
        "✅ Все фото получены!\n\n🔤 Выбери шрифт:", reply_markup=FONT_KB,
    )
    return CHOOSE_FONT

async def choose_font(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    if text == "❌ Отмена":
        return await cancel(update, context)
    font_id = FONT_MAP.get(text)
    if not font_id:
        await update.message.reply_text("❌ Выбери шрифт из списка 👇", reply_markup=FONT_KB)
        return CHOOSE_FONT
    user_sessions[user_id]["font"] = font_id
    await update.message.reply_text(
        f'✅ Шрифт: *{text}*\n\n🎨 Выбери цвет фона:',
        parse_mode="Markdown", reply_markup=COLOR_KB,
    )
    return CHOOSE_COLOR

async def choose_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    if text == "❌ Отмена":
        return await cancel(update, context)
    color_hex = COLOR_MAP.get(text)
    if not color_hex:
        await update.message.reply_text("❌ Выбери цвет из списка 👇", reply_markup=COLOR_KB)
        return CHOOSE_COLOR
    user_sessions[user_id]["bg_color"] = color_hex
    await update.message.reply_text(
        "⏳ Создаю коллаж...", reply_markup=ReplyKeyboardRemove(),
    )
    return await process_collage(update, context)

async def process_collage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text("Сессия устарела. Начни с /start")
        return ConversationHandler.END
    try:
        collage_bytes = create_collage(
            photos=session["photos"], word=session["word"],
            font_id=session["font"], bg_color=session["bg_color"],
        )
        await update.message.reply_photo(
            photo=collage_bytes,
            caption=f'✅ Коллаж *{session["word"]}* готов!',
            parse_mode="Markdown",
        )
        logger.info(f"Коллаж user={user_id}, word={session['word']}")
    except Exception as e:
        logger.exception(f"Ошибка: {e}")
        await update.message.reply_text(f'❌ Ошибка: `{str(e)}`', parse_mode="Markdown")
    _cleanup_user(user_id)
    await update.message.reply_text("Хочешь ещё?", reply_markup=MAIN_KB)
    return CHOOSE_ACTION

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _cleanup_user(update.effective_user.id)
    await update.message.reply_text(
        "До свидания! Чтобы начать заново, отправь /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("⚠️ Ошибка. Попробуй /start")

# ─── aiohttp + Webhook ───────────────────────────────────────────
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL = f"https://letterbe-bot.onrender.com{WEBHOOK_PATH}"

# Создаём Application БЕЗ updater (чтобы не запускался polling)
application = Application.builder().token(TELEGRAM_TOKEN).updater(None).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CHOOSE_ACTION: [MessageHandler(filters.TEXT, choose_action)],
        ENTER_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_word)],
        UPLOAD_PHOTOS: [MessageHandler(filters.PHOTO, upload_photos)],
        CHOOSE_FONT: [MessageHandler(filters.TEXT, choose_font)],
        CHOOSE_COLOR: [MessageHandler(filters.TEXT, choose_color)],
    },
    fallbacks=[
        CommandHandler("cancel", cancel),
        CommandHandler("start", start),
    ],
    allow_reentry=True,
)

application.add_handler(conv_handler)
application.add_error_handler(error_handler)

async def health(request):
    return web.Response(text='{"status":"ok"}', content_type="application/json")

async def webhook_handler(request):
    """Получает обновления от Telegram"""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response(text="ok")

async def main():
    logger.info("🚀 Запуск PhotoLetters Bot (aiohttp webhook)...")
    
    # Инициализация без запуска polling
    await application.initialize()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
    
    # aiohttp сервер
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"🌐 Сервер слушает на порту {PORT}")
    
    # Держим сервер живым
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())

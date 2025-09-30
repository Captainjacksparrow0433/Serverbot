# modules/avr.py
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ESP_HOST


def send_code(code: str) -> str:
    try:
        r = requests.get(f"{ESP_HOST}/c?d={code}", timeout=3)
        return "✅ Command sent" if r.ok else "⚠️ ESP error"
    except Exception as e:
        return f"❌ Failed: {e}"


def volume(direction: str) -> str:
    try:
        r = requests.get(f"{ESP_HOST}/volume?dir={direction}", timeout=3)
        return "🔊 Volume sent" if r.ok else "⚠️ ESP error"
    except Exception as e:
        return f"❌ Failed: {e}"


# Command: /avr
async def avr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Power", callback_data="avr:cmd:7E8154AB"),
            InlineKeyboardButton("Mute", callback_data="avr:cmd:5EA138C7"),
        ],
        [
            InlineKeyboardButton("Vol ⬆", callback_data="avr:vol:up"),
            InlineKeyboardButton("Vol ⬇", callback_data="avr:vol:down"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎛️ AVR Control:", reply_markup=reply_markup)


# Handle button presses
async def avr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split(":")
    resp = "⚠️ Unknown"

    if data[1] == "cmd":
        resp = send_code(data[2])
    elif data[1] == "vol":
        resp = volume(data[2])

    await query.answer()
    await query.edit_message_text(resp)

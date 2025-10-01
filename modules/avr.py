import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from config import ESP_HOST
from .auth import is_allowed

# Function to define the inline keyboard for AVR control
def get_avr_keyboard() -> InlineKeyboardMarkup:
    """Returns the InlineKeyboardMarkup for AVR control."""
    keyboard = [
        [
            InlineKeyboardButton("Power", callback_data="avr:cmd:7E8154AB"),
            InlineKeyboardButton("Mute", callback_data="avr:cmd:5EA138C7"),
        ],
        [
            InlineKeyboardButton("Vol ↑", callback_data="avr:vol:up"),
            InlineKeyboardButton("Vol ↓", callback_data="avr:vol:down"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

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
@is_allowed
async def avr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_avr_keyboard()
    await update.message.reply_text("🎧 AVR Control:", reply_markup=reply_markup)

# Handle button presses
@is_allowed
async def avr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.split(":")

    resp = "⚠️ Unknown command"
    
    # Correctly check the command type from the split data list
    if data[1] == "cmd":
        # Pass the code from the third element of the list
        resp = send_code(data[2])
    elif data[1] == "vol":
        # Pass the direction from the third element of the list
        resp = volume(data[2])

    await query.answer()

    # Re-create the keyboard to send it back with the edited message
    new_reply_markup = get_avr_keyboard()
    
    # Edit the message with the new response and the same inline keyboard
    # Add a timestamp or a generic message to prevent Telegram from blocking the update
    edited_text = f"🎧 AVR Control: {resp}"
    
    await query.edit_message_text(edited_text, reply_markup=new_reply_markup)

           

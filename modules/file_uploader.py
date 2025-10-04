import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .auth import is_allowed

logger = logging.getLogger(__name__)

# --- Personalized Configuration ---
# Define your NAS paths here. The key is the "friendly name" for the button.
# The value is the full, absolute path to the directory on your server.
SAVE_PATHS = {
    "Drive1️⃣": "/mnt/storage/Drive_1",
    "Drive2️⃣": "/mnt/storage/Drive_2",
}

@is_allowed
async def file_upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 1: Catches an incoming file and ASKS the user where to save it.
    """
    attachment = update.message.document or update.message.video
    if not attachment:
        return

    # Store the file's information in the bot's context, keyed by the message ID.
    # This allows the callback handler to know which file to download later.
    context.user_data[update.message.message_id] = {
        'file_id': attachment.file_id,
        'file_name': attachment.file_name,
        'file_size': attachment.file_size
    }

    # Create the keyboard with buttons for each of your save paths
    keyboard = []
    for key in SAVE_PATHS.keys():
        # The callback data contains an identifier, the message ID, and the chosen path key
        callback_data = f"upload:{update.message.message_id}:{key}"
        button = InlineKeyboardButton(key, callback_data=callback_data)
        keyboard.append([button])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Reply to the file message, asking the user to choose a destination
    await update.message.reply_text("Where should I save this file?", reply_markup=reply_markup)

@is_allowed
async def file_upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 2: Handles the button press, retrieves the file info, and performs the download.
    """
    query = update.callback_query
    await query.answer()

    # Parse the data from the button press: "upload:message_id:path_key"
    data_parts = query.data.split(":")
    message_id = int(data_parts[1])
    path_key = data_parts[2]

    # Retrieve the file info we stored earlier
    file_info = context.user_data.pop(message_id, None)

    if not file_info:
        await query.edit_message_text("❌ Error: Could not find the original file information. It might be too old. Please send the file again.")
        return

    save_path = SAVE_PATHS.get(path_key)
    if not save_path:
        await query.edit_message_text("❌ Error: The selected path is not configured correctly.")
        return

    file_name = file_info['file_name']
    file_size_mb = round(file_info['file_size'] / (1024 * 1024), 2)
    destination_path = os.path.join(save_path, file_name)
    
    # Let the user know the download is starting
    await query.edit_message_text(f"⬇️ Saving '{file_name}' ({file_size_mb} MB) to '{path_key}'...")

    try:
        # Get the file object using the stored file_id and download it
        file_object = await context.bot.get_file(file_info['file_id'])
        await file_object.download_to_drive(destination_path)
        
        await query.edit_message_text(f"✅ Successfully saved '{file_name}' to the '{path_key}' directory.")
        logger.info(f"Successfully downloaded and saved '{file_name}' to {destination_path}")

    except Exception as e:
        await query.edit_message_text(f"❌ An error occurred while downloading '{file_name}':\n\n`{e}`")
        logger.error(f"Failed to download '{file_name}'. Error: {e}")


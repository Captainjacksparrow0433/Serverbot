import functools
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("tg-shell-bot")

# The decorator needs access to the allowed user ID.
# It's best to read this from the same central config source.
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

def is_allowed(func):
    """
    Decorator to check if a user is authorized.
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id if update.effective_user else None
        if uid != ALLOWED_USER_ID:
            logger.warning("Denied access for user %s", uid)
            if update.effective_message:
                await update.effective_message.reply_text("Unauthorized.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


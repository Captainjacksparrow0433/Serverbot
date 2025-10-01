#!/usr/bin/env python3
import os
import sys
import asyncio
from telegram import Bot

async def main():
    """Main async entry point for the script."""
    # Check if a command-line argument was provided
    if len(sys.argv) < 2:
        print("Usage: notify.py [boot|shutdown]", file=sys.stderr)
        return

    mode = sys.argv[1]

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("ALLOWED_USER_ID")

    if not token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or ALLOWED_USER_ID", file=sys.stderr)
        return

    # Use the async context manager for the bot
    async with Bot(token=token) as bot:
        if mode == "boot":
            text = "✅ Server booted"
        elif mode == "shutdown":
            text = "⚠️ Server shutting down"
        else:
            text = f"ℹ️ Unknown mode: {mode}"

        try:
            await bot.send_message(chat_id=int(chat_id), text=text)
            print(f"Notification sent successfully for mode: {mode}")
        except Exception as e:
            print(f"Error sending message: {e}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())

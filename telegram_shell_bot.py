#!/usr/bin/env python3
# telegram_shell_bot.py
# Requirements: python-telegram-bot, requests, apscheduler
# Install: pip3 install python-telegram-bot==20.5 requests APScheduler

import os
import sys
import time
import shlex
import logging
import threading
import subprocess
import select
import fcntl
import termios
import errno
import json
from queue import Queue, Empty
from modules import avr, file_uploader
from modules.auth import is_allowed
from modules.weather import weather_report_job

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.constants import ParseMode
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# -------------------------
# Config from environment
# -------------------------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))  # your numeric telegram id
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
OPENWEATHER_CITY = os.environ.get("LAT")
WEATHER_REPORT_INTERVAL_MINUTES = int(os.environ.get("WEATHER_POLL_MINUTES", "15"))
CHAT_ID = ALLOWED_USER_ID  # sending notifications to that user

if not BOT_TOKEN or not ALLOWED_USER_ID:
    print("TELEGRAM_BOT_TOKEN and ALLOWED_USER_ID must be set in environment", file=sys.stderr)
    sys.exit(2)

# -------------------------
# Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("tg-shell-bot")

# -------------------------
# Simple auth decorator
# -------------------------
# -------------------------
# Single-command execution
# -------------------------
@is_allowed
async def cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /cmd ls -la /etc"""
    text = update.message.text or ""
    parts = text.split(" ", 1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text("Usage: /cmd <command>")
        return
    command = parts[1]
    logger.info("Running command: %s", command)
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        out = proc.stdout + ("\nERR:\n" + proc.stderr if proc.stderr else "")
        if not out:
            out = f"(exit {proc.returncode})"
        # Telegram message size limit ~4096; chunk if necessary
        for chunk in [out[i:i+3800] for i in range(0, len(out), 3800)]:
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="MarkdownV2")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("Command timed out.")

# -------------------------
# PTY-backed interactive-ish shell
# -------------------------
# We'll manage a single session per bot instance (you can expand to multiple).
pty_proc = None
pty_master_fd = None
pty_lock = threading.Lock()
read_thread = None
read_stop = threading.Event()
output_queue = Queue()
session_open = False

def spawn_pty_shell(shell="/bin/bash"):
    global pty_proc, pty_master_fd, read_thread, read_stop, session_open
    if session_open:
        return False, "session already open"
    import pty, os
    master, slave = pty.openpty()
    # start shell
    p = subprocess.Popen([shell], stdin=slave, stdout=slave, stderr=slave, close_fds=True, preexec_fn=os.setsid)
    os.close(slave)
    pty_proc = p
    pty_master_fd = master
    # set master non-blocking
    fl = fcntl.fcntl(pty_master_fd, fcntl.F_GETFL)
    fcntl.fcntl(pty_master_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    read_stop.clear()
    read_thread = threading.Thread(target=_pty_reader)
    read_thread.daemon = True
    read_thread.start()
    session_open = True
    return True, "spawned"

def _pty_reader():
    global pty_master_fd, read_stop
    try:
        while not read_stop.is_set():
            try:
                data = os.read(pty_master_fd, 4096)
                if not data:
                    time.sleep(0.1)
                    continue
                output_queue.put(data.decode(errors="ignore"))
            except OSError as e:
                if e.errno in (errno.EIO, errno.EBADF):
                    break
                time.sleep(0.1)
    except Exception as ex:
        logger.exception("pty reader error: %s", ex)

def write_to_pty(s):
    global pty_master_fd, pty_proc
    if not session_open or not pty_master_fd:
        return False, "no session"
    try:
        os.write(pty_master_fd, s.encode())
        return True, ""
    except Exception as ex:
        return False, str(ex)

def stop_pty():
    global pty_proc, pty_master_fd, read_stop, session_open
    read_stop.set()
    try:
        if pty_proc:
            pty_proc.terminate()
            time.sleep(0.5)
            if pty_proc.poll() is None:
                pty_proc.kill()
    except Exception:
        pass
    try:
        if pty_master_fd:
            os.close(pty_master_fd)
    except Exception:
        pass
    pty_proc = None
    pty_master_fd = None
    session_open = False

# background task: flush output_queue -> send DM
async def flush_output(bot: Bot):
    text_parts = []
    while True:
        try:
            s = output_queue.get_nowait()
            text_parts.append(s)
        except Empty:
            break
    if not text_parts:
        return
    combined = "".join(text_parts)
    # chunk
    for chunk in [combined[i:i+3800] for i in range(0, len(combined), 3800)]:
        try:
            await bot.send_message(chat_id=CHAT_ID, text=f"```\n{chunk}\n```", parse_mode="MarkdownV2")
        except Exception as ex:
            logger.exception("failed to send chunk: %s", ex)

# command handlers for starting/stopping shell
@is_allowed
async def shell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = spawn_pty_shell()
    if not ok:
        await update.message.reply_text(f"Failed: {msg}")
        return
    await update.message.reply_text("Shell session started. Send messages and they will be written to the shell STDIN. Use /sp to close. Prefix lines with `\\n` to send newline if needed.")

@is_allowed
async def shell_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stop_pty()
    await update.message.reply_text("Shell session stopped.")

# messages while session open are forwarded to PTY stdin
@is_allowed
async def relay_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global session_open
    if not session_open:
        # not a shell message; ignore or echo
        return
    text = update.message.text or ""
    # by default send the message followed by newline
    # if user wants to send raw without newline, support prefix "RAW:" for example
    if text.startswith("RAW:"):
        payload = text[len("RAW:"):]
    else:
        payload = text + "\n"
    ok, err = write_to_pty(payload)
    if not ok:
        await update.message.reply_text(f"write failed: {err}")
    # flush any immediate output
    await flush_output(context.bot)

# manual flush command (in case you want to pull pending output)
@is_allowed
async def flush_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await flush_output(context.bot)
# -------------------------
# AVR command wrappers
# -------------------------
@is_allowed
async def avr_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await avr.menu(update, context)

@is_allowed
async def avr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await avr.callback(update, context)
# -------------------------
# Boot/shutdown notification helpers
# -------------------------
def send_startup_message(text):
    # This is synchronous helper to be used by systemd scripts that call the bot script with an arg, or we can use the live bot to send message.
    try:
        b = Bot(BOT_TOKEN)
        b.send_message(chat_id=CHAT_ID, text=text)
        return True
    except Exception as ex:
        logger.exception("failed startup notify: %s", ex)
        return False

# -------------------------
# Weather check function
# -------------------------
# -------------------------
# Main
# -------------------------
def main():
    application = (
         ApplicationBuilder()
        .token(BOT_TOKEN)
        .base_url("http://127.0.0.1:8081/bot")
        .base_file_url("http://127.0.0.1:8081/file/bot")
        .build()
    )
    #testing
    #application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("avr", avr.avr_command))
    application.add_handler(CallbackQueryHandler(avr.avr_callback, pattern="^avr:"))
    application.add_handler(CommandHandler("cmd", cmd_handler))
    application.add_handler(CommandHandler("st", shell_start))
    application.add_handler(CommandHandler("sp", shell_stop))
    application.add_handler(CommandHandler("flush", flush_cmd))
    # any text message goes to relay (only when session open)
    application.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO, file_uploader.file_upload_handler))
    # This new CallbackQueryHandler listens for the button press and does the SAVING
    application.add_handler(CallbackQueryHandler(file_uploader.file_upload_callback, pattern="^upload:"))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), relay_messages))
    if OPENWEATHER_API_KEY and OPENWEATHER_CITY:
                                                 application.job_queue.run_repeating(
                                                 weather_report_job,  # <-- Use the new function name
                                                 interval=WEATHER_REPORT_INTERVAL_MINUTES * 60,
                                                 first=10,  # Run the first job after 10 seconds, which is a good idea
                                                 name="weather_report" # <-- Renamed for clarity
    )
    logger.info(f"Weather reporting scheduled for every {WEATHER_REPORT_INTERVAL_MINUTES} minutes.")
    # Scheduler for weather
#    scheduler = AsyncIOScheduler()
#    scheduler.add_job(weather_poll_job, "interval", minutes=WEATHER_POLL_MINUTES, args=[application])
#    scheduler.start()
#    application.job_queue.run_repeating(weather_poll_job, interval=60, first=10)
    # Start bot
    logger.info("Starting Telegram bot")
    application.run_polling()

if __name__ == "__main__":
    main()

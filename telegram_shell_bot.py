import os, subprocess, logging, requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.background import BackgroundScheduler
from modules import avr

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])
OPENWEATHER_API_KEY = os.environ["OPENWEATHER_API_KEY"]
LAT = os.environ["LAT"]
LON = os.environ["LON"]
POLL_MIN = int(os.environ["WEATHER_POLL_MINUTES"])

# Auth check
def allowed(user_id: int) -> bool:
    return user_id == ALLOWED_USER_ID

# --- Shell Command Handler ---
async def shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return await update.message.reply_text("⛔ Unauthorized")

    cmd = " ".join(context.args)
    if not cmd:
        return await update.message.reply_text("Usage: /sh <command>")

    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, timeout=15)
        await update.message.reply_text(f"```{out.decode()}```", parse_mode="Markdown")
    except subprocess.CalledProcessError as e:
        await update.message.reply_text(f"❌ Error:\n{e.output.decode()}")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed: {e}")

# --- Weather Alert ---
async def weather_job(app):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OPENWEATHER_API_KEY}&units=metric"
        r = requests.get(url, timeout=5)
        data = r.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        await app.bot.send_message(ALLOWED_USER_ID, f"🌤️ Weather: {desc}, {temp}°C")
    except Exception as e:
        logging.error(f"Weather fetch failed: {e}")

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id):
        return await update.message.reply_text("⛔ Unauthorized")
    await update.message.reply_text("🤖 Bot ready. Use /sh, /avr")

# --- Main ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sh", shell))
    app.add_handler(CommandHandler("avr", avr.menu))
    app.add_handler(CallbackQueryHandler(avr.callback, pattern="^avr:"))

    # Weather scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: weather_job(app), "interval", minutes=POLL_MIN)
    scheduler.start()

    app.run_polling()

if __name__ == "__main__":
    main()

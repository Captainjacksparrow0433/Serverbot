import os
import logging
import requests
from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger("tg-shell-bot")

# Fetch config from environment variables. This avoids passing globals.
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
LAT = os.environ.get("LAT")
LON = os.environ.get("LON")
CHAT_ID = int(os.environ.get("ALLOWED_USER_ID", "0")) # Get from the same source as auth module

def fetch_weather_alerts():
    """Fetches weather alerts from the OpenWeatherMap API."""
    if not OPENWEATHER_API_KEY or not LAT or not LON:
        logger.info("Weather not configured (missing key/lat/lon)")
        return None
    
    url = f"https://api.openweathermap.org/data/2.5/onecall?lat={LAT}&lon={LON}&appid={OPENWEATHER_API_KEY}&exclude=minutely,hourly"
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        alerts = data.get("alerts", [])
        return alerts
    except Exception as ex:
        logger.exception("weather fetch failed: %s", ex)
        return None

async def weather_poll_job(application):
    """
    Periodic job to fetch and send weather alerts.
    Takes the application instance to access the bot.
    """
    alerts = fetch_weather_alerts()
    if not alerts:
        return
    
    for alert in alerts:
        sender = alert.get("sender_name", "")
        event = alert.get("event", "")
        desc = alert.get("description", "")
        start = alert.get("start")
        end = alert.get("end")
        
        msg = (
            f"Weather alert: *{event}* from _{sender}_\n"
            f"Start: {start} End: {end}\n\n"
            f"{desc}"
        )
        
        try:
            await application.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
        except Exception as ex:
            logger.exception("failed to send weather alert: %s", ex)


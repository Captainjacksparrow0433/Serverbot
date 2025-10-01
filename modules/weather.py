import os
import logging
import requests
from telegram import Bot
from telegram.constants import ParseMode
import datetime

logger = logging.getLogger("tg-weather-bot")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- CONFIGURATION ---
# Fetch config from environment variables
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
OPENWEATHER_CITY = os.environ.get("LAT") # e.g., "Alappuzha"
CHAT_ID = os.environ.get("ALLOWED_USER_ID") # Your Telegram User/Chat ID

def fetch_current_weather():
    """Fetches current weather from the OpenWeatherMap API."""
    if not OPENWEATHER_API_KEY or not OPENWEATHER_CITY:
        logger.info("Weather not configured (missing OPENWEATHER_API_KEY or OPENWEATHER_CITY)")
        return None
    
    # Using the /weather endpoint from your link, added '&units=metric' for Celsius
    url = f"https://api.openweathermap.org/data/2.5/weather?q={OPENWEATHER_CITY}&appid={OPENWEATHER_API_KEY}&units=metric"
    
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()  # This will raise an exception for HTTP errors (like 401, 404)
        data = r.json()
        
        # --- PARSE THE NEW DATA STRUCTURE ---
        city_name = data.get("name")
        weather_desc = data["weather"][0]["description"].title()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        humidity = data["main"]["humidity"]
        wind_speed = data["wind"]["speed"]
        
        # Return a dictionary with the parsed weather info
        return {
            "city": city_name,
            "description": weather_desc,
            "temp": temp,
            "feels_like": feels_like,
            "humidity": humidity,
            "wind_speed": wind_speed
        }
        
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error fetching weather: {http_err} - Check your API key and city name.")
        return None
    except Exception as ex:
        logger.exception("Weather fetch failed: %s", ex)
        return None

async def weather_report_job(application):
    """
    Periodic job to fetch and send a current weather report.
    Takes the application instance to access the bot.
    """
    if not CHAT_ID:
        logger.warning("ALLOWED_USER_ID is not set. Cannot send weather report.")
        return
        
    weather_data = fetch_current_weather()
    
    # If fetch failed or there's no data, do nothing.
    if not weather_data:
        return
    
    # --- FORMAT THE NEW MESSAGE ---
    city = weather_data['city']
    desc = weather_data['description']
    temp = weather_data['temp']
    feels = weather_data['feels_like']
    humidity = weather_data['humidity']
    wind = weather_data['wind_speed']

    # Using Markdown for nice formatting in Telegram
    msg = (
        f"📍 *Weather Report for {city}*\n\n"
        f"*{desc}*\n\n"
        f"🌡️ Temperature: *{temp}°C*\n"
        f"🤔 Feels Like: *{feels}°C*\n"
        f"💧 Humidity: *{humidity}%*\n"
        f"💨 Wind Speed: *{wind} m/s*"
    )
        
    try:
        await application.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Successfully sent weather report to chat ID {CHAT_ID}")
    except Exception as ex:
        logger.exception("Failed to send weather report: %s", ex)


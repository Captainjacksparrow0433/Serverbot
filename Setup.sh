#!/usr/bin/env bash
set -e

echo "=== Telegram Bot Setup ==="

# Ask for inputs
read -rp "Enter Telegram Bot Token: " BOT_TOKEN
read -rp "Enter your Telegram User ID (numeric): " USER_ID
read -rp "Enter OpenWeather API Key: " WEATHER_KEY
read -rp "Enter Latitude: " LAT
read -rp "Enter Longitude: " LON
read -rp "Weather polling interval in minutes [15]: " POLL
POLL=${POLL:-15}
read -rp "Enter ESP32 Host (e.g. http://192.168.1.50): " ESP_HOST   # 🔹

# Create system user if not exists
if ! id "telegrambot" &>/dev/null; then
    echo "[*] Creating system user telegrambot"
    useradd -r -s /bin/false telegrambot
fi

# Directories
mkdir -p /opt/telegram-bot/modules
mkdir -p /etc/telegram-bot

# Copy bot script (assuming files in same dir as setup.sh)
cp telegram_shell_bot.py /opt/telegram-bot/
cp -r modules/* /opt/telegram-bot/modules/ || true

# 🔹 Create config.py with ESP host
cat >/opt/telegram-bot/config.py <<EOF
ESP_HOST = "${ESP_HOST}"
EOF

chown -R telegrambot:telegrambot /opt/telegram-bot

# Write env file
cat >/etc/telegram-bot/env <<EOF
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USER_ID=${USER_ID}
OPENWEATHER_API_KEY=${WEATHER_KEY}
LAT=${LAT}
LON=${LON}
WEATHER_POLL_MINUTES=${POLL}
EOF

chmod 600 /etc/telegram-bot/env

# Install dependencies in a venv
echo "[*] Installing dependencies"
apt-get update -y
apt-get install -y python3-venv python3-pip

python3 -m venv /opt/telegram-bot/venv
source /opt/telegram-bot/venv/bin/activate
pip install --upgrade pip
pip install python-telegram-bot==20.5 requests APScheduler
deactivate

# systemd service
cat >/etc/systemd/system/telegram-bot.service <<'EOF'
[Unit]
Description=Telegram Shell Bot
After=network.target

[Service]
Type=simple
EnvironmentFile=/etc/telegram-bot/env
User=telegrambot
WorkingDirectory=/opt/telegram-bot
ExecStart=/opt/telegram-bot/venv/bin/python /opt/telegram-bot/telegram_shell_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# systemd notify service
cat >/etc/systemd/system/telegram-boot-notify.service <<'EOF'
[Unit]
Description=Notify Telegram on boot/shutdown
DefaultDependencies=no
After=network.target

[Service]
Type=oneshot
EnvironmentFile=/etc/telegram-bot/env
ExecStart=/opt/telegram-bot/venv/bin/python -c "import os; from telegram import Bot; Bot(os.environ['TELEGRAM_BOT_TOKEN']).send_message(chat_id=int(os.environ['ALLOWED_USER_ID']), text='✅ Server booted')"
ExecStop=/opt/telegram-bot/venv/bin/python -c "import os; from telegram import Bot; Bot(os.environ['TELEGRAM_BOT_TOKEN']).send_message(chat_id=int(os.environ['ALLOWED_USER_ID']), text='⚠️ Server shutting down')"
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable services
systemctl daemon-reload
systemctl enable telegram-bot.service telegram-boot-notify.service
systemctl start telegram-bot.service telegram-boot-notify.service

echo "=== Setup complete ==="
echo "Bot should now be running. Check logs with: journalctl -u telegram-bot.service -f"

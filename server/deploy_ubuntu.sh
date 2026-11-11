#!/usr/bin/env bash
set -e

echo "=== Установка Crypto Bot v2.50 Server на Ubuntu ==="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

APP_DIR="/opt/crypto-bot-v250"
sudo mkdir -p "$APP_DIR"
sudo cp -r "$(dirname "$0")"/* "$APP_DIR"/

cd "$APP_DIR"
sudo python3 -m venv venv
sudo "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/venv/bin/pip" install -r requirements.txt

cat << 'EOF' | sudo tee /etc/systemd/system/crypto-bot.service
[Unit]
Description=Crypto Bot v2.50 Trading Engine & API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/crypto-bot-v250
ExecStart=/opt/crypto-bot-v250/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable crypto-bot.service
sudo systemctl restart crypto-bot.service

echo "=== Готово! Сервер Crypto Bot v2.50 запущен на порту 8000 ==="
sudo systemctl status crypto-bot.service --no-pager

#!/bin/bash
SERVICE_NAME="username_checker"
APP_FILE="main.py"
PYTHON_BIN="/usr/bin/python3"

sudo apt update
sudo apt install -y python3 curl

curl -LsSf https://astral.sh/uv/install.sh | less
uv sync

SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Username Checker API (UV)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/uv run $APP_FILE
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

sudo systemctl status $SERVICE_NAME --no-pager

echo "=========================================="
echo "Setup complete. Service '$SERVICE_NAME' is running."
echo "Access API at http://<your-server-ip>:8000"
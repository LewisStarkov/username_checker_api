#!/bin/bash

SERVICE_NAME="username_checker"
REPO_URL="git@github.com:LewisStarkov/username_checker_api.git"
APP_FILE="main.py"
PYTHON_BIN="/usr/bin/python3"
INSTALL_DIR="/opt/$SERVICE_NAME"
VENV_DIR="$INSTALL_DIR/venv"

sudo apt update
sudo apt install -y git python3 python3-venv curl

if [ ! -d "$INSTALL_DIR" ]; then
    sudo git clone "$REPO_URL" "$INSTALL_DIR"
else
    cd "$INSTALL_DIR"
    sudo git pull
fi

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_BIN -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
deactivate

SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Username Checker API (UV)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/uv run $APP_FILE
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

sudo systemctl status $SERVICE_NAME --no-pager

PUBLIC_IP=$(curl -s ipinfo.io/ip)
echo "=========================================="
echo "Setup complete. Service '$SERVICE_NAME' is running."
echo "Access API at http://$PUBLIC_IP:8000"

#!/bin/bash
set -e

SERVICE_NAME="username_checker"
REPO_URL="https://github.com/LewisStarkov/username_checker_api.git"
INSTALL_DIR="/opt/$SERVICE_NAME"
VENV_DIR="$INSTALL_DIR/.venv"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

GRAY="\033[90m"
GREEN="\033[32m"
BLUE="\033[34m"
RESET="\033[0m"
BOLD="\033[1m"

STEPS=(
    "Stopping old service"
    "Cleaning up directories"
    "Installing uv & dependencies"
    "Cloning repository"
    "Syncing environment"
    "Configuring systemd"
    "Launching service"
)

NUM_STEPS=${#STEPS[@]}
declare -a STEP_STATUS
declare -a STEP_TIMES

for i in "${!STEPS[@]}"; do
    STEP_STATUS[$i]=0
    STEP_TIMES[$i]="00:00"
done

draw_ui() {
    printf "\033[${NUM_STEPS}A"
    for i in "${!STEPS[@]}"; do
        local index=$((i+1))
        local color=$GRAY
        local symbol=" "
        
        if [ "${STEP_STATUS[$i]}" -eq 1 ]; then
            color=$BLUE
            symbol="${SPINNER:-|}"
        elif [ "${STEP_STATUS[$i]}" -eq 2 ]; then
            color=$GREEN
            symbol="✔"
        fi
        
        printf "\r${color}%b [%d / %d] %-50s [%s]${RESET}\033[K\n" "$symbol" "$index" "$NUM_STEPS" "${STEPS[$i]}" "${STEP_TIMES[$i]}"
    done
}

run_step() {
    local step_idx=$1
    shift
    
    STEP_STATUS[$step_idx]=1
    local start_time=$(date +%s)
    
    tput civis
    "$@" >/dev/null 2>&1 &
    local pid=$!
    
    local chars="/-\|"
    local j=0
    while kill -0 $pid 2>/dev/null; do
        local now=$(date +%s)
        local elapsed=$((now-start_time))
        STEP_TIMES[$step_idx]=$(printf "%02d:%02d" $((elapsed/60)) $((elapsed%60)))
        SPINNER="${chars:j++%4:1}"
        draw_ui
        sleep 0.1
    done
    wait $pid
    
    STEP_STATUS[$step_idx]=2
    local end_now=$(date +%s)
    STEP_TIMES[$step_idx]=$(printf "%02d:%02d" $(((end_now-start_time)/60)) $(((end_now-start_time)%60)))
    draw_ui
    tput cnorm
}

echo -e "${BOLD}Deploying $SERVICE_NAME...${RESET}\n"
for _ in "${STEPS[@]}"; do echo ""; done

run_step 0 bash -c "sudo systemctl stop $SERVICE_NAME || true; sudo systemctl disable $SERVICE_NAME || true"
run_step 1 sudo rm -rf "$INSTALL_DIR"
run_step 2 bash -c "sudo apt update -qq && sudo apt install -y -qq curl git && curl -LsSf https://astral.sh/uv/install.sh | sh"
run_step 3 bash -c "sudo mkdir -p $INSTALL_DIR && sudo chown $USER:$USER $INSTALL_DIR && git clone $REPO_URL $INSTALL_DIR"
run_step 4 bash -c "export PATH=\"\$HOME/.local/bin:\$PATH\" && cd $INSTALL_DIR && uv venv && uv pip install -r requirements.txt"

run_step 5 sudo bash -c "cat > $SERVICE_FILE <<EOF
[Unit]
Description=Username Checker API
After=network.target

[Service]
User=$USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/main.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF"

run_step 6 bash -c "sudo systemctl daemon-reload && sudo systemctl enable $SERVICE_NAME && sudo systemctl start $SERVICE_NAME"

EXT_IP=$(curl -s ifconfig.me || echo "your_ip")

echo -e "\n${GREEN}${BOLD}Successfully deployed!${RESET}"
echo -e "=========================================="
echo -e "${BOLD}Check Status:${RESET}   systemctl status $SERVICE_NAME"
echo -e "${BOLD}View Logs:${RESET}      journalctl -u $SERVICE_NAME -n 50 -f"
echo -e "${BOLD}Test:${RESET}           curl -i http://$EXT_IP:8000/status"
echo -e "=========================================="
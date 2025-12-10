#!/bin/bash
# CO2 Monitor - Service Installation Script
# Installs bootstrap.py as a systemd service with venv

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="co2-monitor"
SERVICE_USER="${SUDO_USER:-$(whoami)}"
INSTALL_DIR="$SCRIPT_DIR"
VENV_DIR="$INSTALL_DIR/venv"

echo "=================================================="
echo "CO2 Monitor - Service Installation"
echo "=================================================="
echo "Install dir: $INSTALL_DIR"
echo "Venv dir: $VENV_DIR"
echo "Service user: $SERVICE_USER"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run with sudo: sudo bash $0"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv "$VENV_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"

# Install Python dependencies in venv
echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || {
        echo "Warning: Failed to install some dependencies"
    }
fi

# Create systemd service file
echo "Creating systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=CO2 Monitor Device Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/bootstrap.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Environment
Environment="PYTHONUNBUFFERED=1"
Environment="VIRTUAL_ENV=${VENV_DIR}"
Environment="PATH=${VENV_DIR}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable and start service
echo "Enabling service..."
systemctl enable ${SERVICE_NAME}

echo "Starting service..."
systemctl restart ${SERVICE_NAME}

# Wait and check status
sleep 2
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo ""
    echo "=================================================="
    echo "Service installed and running!"
    echo "=================================================="
else
    echo ""
    echo "Warning: Service may not have started correctly"
    systemctl status ${SERVICE_NAME} --no-pager || true
fi

echo ""
echo "Useful commands:"
echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
echo "  Logs:    journalctl -u ${SERVICE_NAME} -f"
echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
echo ""

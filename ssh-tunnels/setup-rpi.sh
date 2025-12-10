#!/bin/bash
# Reverse SSH tunnel setup for Raspberry Pi
# Based on: https://github.com/junzis/guide-autossh-reverse-tunnel

set -e

SERVER="31.59.170.64"
SERVER_USER="tunneld"
TUNNEL_PORT="2222"
KEY_FILE="$HOME/.ssh/tunnel_key"

echo "=== SSH Tunnel Setup ==="

# 1. Install autossh (better than plain ssh for tunnels)
if ! command -v autossh &>/dev/null; then
    echo "Installing autossh..."
    sudo apt-get update -qq && sudo apt-get install -y -qq autossh
fi

# 2. Generate SSH key
mkdir -p "$HOME/.ssh"
if [ ! -f "$KEY_FILE" ]; then
    echo "Generating SSH key..."
    ssh-keygen -t ed25519 -f "$KEY_FILE" -N "" -q
fi

# 3. Show public key
echo ""
echo "========== PUBLIC KEY =========="
cat "${KEY_FILE}.pub"
echo "================================"
echo ""

# 4. Create systemd service with autossh
echo "Creating systemd service..."
sudo tee /etc/systemd/system/ssh-tunnel.service > /dev/null << EOF
[Unit]
Description=Reverse SSH Tunnel (autossh)
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
Environment="AUTOSSH_GATETIME=0"
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i $KEY_FILE -R $TUNNEL_PORT:localhost:22 $SERVER_USER@$SERVER
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ssh-tunnel

echo ""
echo "=== Done ==="
echo ""
echo "1. Send the PUBLIC KEY above to admin"
echo "2. After key is added: sudo systemctl start ssh-tunnel"
echo "3. Connect from anywhere: ssh -p $TUNNEL_PORT pi@$SERVER"

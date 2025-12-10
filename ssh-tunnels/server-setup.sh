#!/bin/bash
# =============================================================================
# SSH Tunnels - Server Setup Script
# Создаёт изолированного пользователя для reverse SSH туннелей
# =============================================================================

set -e

echo "=== SSH Tunnels Server Setup ==="

# Конфигурация
TUNNEL_USER="tunneld"
TUNNEL_HOME="/opt/apps/ssh-tunnels"
TUNNEL_PORTS="2222:2230"  # Диапазон портов для туннелей

# 1. Создать пользователя без shell (только для туннелей)
if ! id "$TUNNEL_USER" &>/dev/null; then
    echo "Creating user: $TUNNEL_USER"
    useradd -r -s /usr/sbin/nologin -d "$TUNNEL_HOME" -M "$TUNNEL_USER"
else
    echo "User $TUNNEL_USER already exists"
fi

# 2. Создать структуру директорий
echo "Creating directory structure..."
mkdir -p "$TUNNEL_HOME"/{authorized_keys,scripts,logs}
mkdir -p "$TUNNEL_HOME/.ssh"

# 3. Создать authorized_keys с ограничениями
touch "$TUNNEL_HOME/.ssh/authorized_keys"

# 4. Настроить права
chown -R "$TUNNEL_USER:$TUNNEL_USER" "$TUNNEL_HOME"
chmod 700 "$TUNNEL_HOME/.ssh"
chmod 600 "$TUNNEL_HOME/.ssh/authorized_keys"

# 5. Добавить конфигурацию в sshd_config если её нет
SSHD_CONFIG="/etc/ssh/sshd_config"
TUNNEL_CONFIG="# SSH Tunnels - Remote device access
Match User $TUNNEL_USER
    AllowTcpForwarding remote
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    GatewayPorts yes
    ForceCommand /bin/false"

if ! grep -q "Match User $TUNNEL_USER" "$SSHD_CONFIG"; then
    echo "Adding tunnel config to sshd_config..."
    echo "" >> "$SSHD_CONFIG"
    echo "$TUNNEL_CONFIG" >> "$SSHD_CONFIG"

    # Проверить конфигурацию
    if sshd -t; then
        echo "SSHD config OK, reloading..."
        systemctl reload sshd
    else
        echo "ERROR: Invalid sshd config!"
        exit 1
    fi
else
    echo "Tunnel config already in sshd_config"
fi

# 6. Открыть порты в firewall (если используется ufw)
if command -v ufw &>/dev/null && ufw status | grep -q "active"; then
    echo "Configuring UFW firewall..."
    ufw allow 2222:2230/tcp comment "SSH Tunnels"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To add a new device:"
echo "  1. Generate key on RPi: ssh-keygen -t ed25519 -f ~/.ssh/tunnel_key -N ''"
echo "  2. Add public key to: $TUNNEL_HOME/.ssh/authorized_keys"
echo "  3. Format: restrict,port-forwarding,permitopen=\"localhost:22\",command=\"/bin/false\" ssh-ed25519 AAAA... device_name"
echo ""
echo "Assigned ports:"
echo "  2222 - rpi_2ccf6786b7a7 (CO2 Monitor)"
echo "  2223-2230 - Reserved for future devices"

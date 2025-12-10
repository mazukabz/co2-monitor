# SSH Tunnels

Reverse SSH туннели для удалённого доступа к Raspberry Pi из любого места.

## Архитектура

```
[MacBook] --> [Server:2222] <-- [RPi tunnel] <-- [RPi SSH:22]
     ^                              ^
     |                              |
  id_rpi key                   tunnel_key
```

- RPi держит постоянный туннель к серверу через autossh
- Сервер слушает порт 2222 и проксирует на RPi:22
- MacBook подключается к серверу:2222

## Быстрый старт

### Подключение к RPi
```bash
ssh -p 2222 mazukabz@31.59.170.64
# или через alias:
ssh co2-rpi
```

## Ключи

### 1. Ключ туннеля (RPi -> Server)
- **Расположение на RPi**: ~/.ssh/tunnel_key
- **Публичный ключ на сервере**: /opt/apps/ssh-tunnels/.ssh/authorized_keys
- **Назначение**: RPi использует этот ключ для подключения к серверу и создания туннеля
- **Пользователь**: tunneld (ограниченный, только port-forwarding)

### 2. Ключ доступа (MacBook -> RPi)
- **Расположение на MacBook**: ~/.ssh/id_rpi
- **Публичный ключ на RPi**: ~/.ssh/authorized_keys
- **Назначение**: MacBook использует для подключения к RPi через туннель

## Конфигурация

### MacBook (~/.ssh/config)
```
Host co2-rpi
  HostName 31.59.170.64
  Port 2222
  User mazukabz
  IdentityFile ~/.ssh/id_rpi
```

### RPi (/etc/systemd/system/ssh-tunnel.service)
```ini
[Unit]
Description=Reverse SSH Tunnel (autossh)
After=network-online.target
Wants=network-online.target

[Service]
User=mazukabz
Environment="AUTOSSH_GATETIME=0"
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i /home/mazukabz/.ssh/tunnel_key -R 2222:localhost:22 tunneld@31.59.170.64
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Server (/etc/ssh/sshd_config)
```
Match User tunneld
    AllowTcpForwarding remote
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    GatewayPorts yes
    ForceCommand /bin/false
```

## Порты

| Порт | Назначение |
|------|------------|
| 2222 | CO2 Monitor RPi |
| 2223-2230 | Зарезервировано для будущих устройств |

## Команды

### Проверка статуса
```bash
# На RPi - статус туннеля
sudo systemctl status ssh-tunnel

# На сервере - слушается ли порт
ss -tlnp | grep 2222

# Логи туннеля
journalctl -u ssh-tunnel -f
```

### Управление туннелем
```bash
# Перезапуск
sudo systemctl restart ssh-tunnel

# Остановка
sudo systemctl stop ssh-tunnel

# Включить автозапуск
sudo systemctl enable ssh-tunnel
```

## Добавление нового устройства

### 1. На новом RPi
```bash
curl -sL http://31.59.170.64:10900/tunnel-setup.sh | bash
```

### 2. На сервере
Добавить публичный ключ устройства:
```bash
echo "ssh-ed25519 AAAA... device_name" >> /opt/apps/ssh-tunnels/.ssh/authorized_keys
```

### 3. На MacBook (для подключения)
Создать ключ без пароля:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_rpi -N "" -C "macbook-to-rpi"
```

Добавить публичный ключ на RPi:
```bash
# На RPi
echo "ssh-ed25519 AAAA... macbook-to-rpi" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Добавить в ~/.ssh/config:
```
Host co2-rpi
  HostName 31.59.170.64
  Port 2222
  User mazukabz
  IdentityFile ~/.ssh/id_rpi
```

## Решение проблем

### Permission denied (publickey)

1. **Проверить права на RPi**:
```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

2. **Проверить, что ключ добавлен**:
```bash
cat ~/.ssh/authorized_keys
ssh-keygen -lf ~/.ssh/authorized_keys  # показать fingerprint
```

3. **Проверить fingerprint на MacBook**:
```bash
ssh-keygen -lf ~/.ssh/id_rpi.pub
```
Fingerprints должны совпадать!

4. **SSH использует другой ключ** (из-за ~/.ssh/config):
```bash
# Проверить какой ключ предлагается
ssh -v co2-rpi 2>&1 | grep "Offering public key"
```
Убедиться, что IdentityFile указан правильно.

5. **Ключ с паролем**:
Если ключ защищён паролем, либо:
- Добавить в ssh-agent: `ssh-add ~/.ssh/id_rpi`
- Создать новый ключ без пароля: `ssh-keygen -t ed25519 -f ~/.ssh/id_rpi -N ""`

### Туннель не работает

1. **Проверить статус на RPi**:
```bash
sudo systemctl status ssh-tunnel
journalctl -u ssh-tunnel -n 50
```

2. **Проверить порт на сервере**:
```bash
ssh root@31.59.170.64 "ss -tlnp | grep 2222"
```

3. **Перезапустить туннель**:
```bash
sudo systemctl restart ssh-tunnel
```

### Connection refused

Туннель не установлен. Проверить:
- RPi включён и подключён к интернету
- Сервис ssh-tunnel запущен
- Ключ tunnel_key добавлен на сервер

## Файлы

### Сервер (31.59.170.64)
- /opt/apps/ssh-tunnels/ - корневая директория проекта
- /opt/apps/ssh-tunnels/.ssh/authorized_keys - ключи устройств для туннелей
- /etc/ssh/sshd_config - конфиг sshd с Match User tunneld

### RPi
- ~/.ssh/tunnel_key - приватный ключ для туннеля
- ~/.ssh/authorized_keys - ключи для доступа (MacBook)
- /etc/systemd/system/ssh-tunnel.service - systemd сервис

### MacBook
- ~/.ssh/id_rpi - приватный ключ для доступа к RPi
- ~/.ssh/config - алиас co2-rpi

## Текущие устройства

| Устройство | Порт | Пользователь | Статус |
|------------|------|--------------|--------|
| CO2 Monitor (piserver) | 2222 | mazukabz | Активен |

## Безопасность

- Пользователь tunneld не имеет shell (nologin)
- Разрешён только remote port forwarding
- GatewayPorts=yes позволяет слушать на 0.0.0.0
- Порты 2222-2230 открыты в firewall

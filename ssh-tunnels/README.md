# SSH Tunnels

Reverse SSH туннели для удалённого доступа к Raspberry Pi.

## Как подключиться

```bash
ssh -p 2222 pi@31.59.170.64
```

Или добавь в `~/.ssh/config`:
```
Host co2-rpi
    HostName 31.59.170.64
    Port 2222
    User pi
```

## Порты

| Порт | Устройство |
|------|------------|
| 2222 | CO2 Monitor |

## Проверка

Сервер: `ss -tlnp | grep 2222`
RPi: `sudo systemctl status ssh-tunnel`

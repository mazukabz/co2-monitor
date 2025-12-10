# CO2 Monitor - Device Firmware v2.0.0

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Raspberry Pi                              │
├─────────────────────────────────────────────────────────────┤
│  systemd service (co2-monitor)                              │
│       │                                                      │
│       ▼                                                      │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │ bootstrap.py│────▶│   main.py   │────▶│   SCD41     │   │
│  │ (immutable) │     │ (updatable) │     │  (sensor)   │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│       │                    │                                 │
│       ▼                    ▼                                 │
│  ┌─────────────┐     ┌─────────────┐                        │
│  │   Server    │     │   SSD1306   │                        │
│  │ /api/device │     │  (display)  │                        │
│  └─────────────┘     └─────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## Установка

### Новая установка (одна команда)

```bash
curl -sL http://31.59.170.64:10900/install.py | python3
sudo bash ~/co2-monitor/install_service.sh
```

### Что устанавливается

```
~/co2-monitor/
├── bootstrap.py       # OTA loader (не обновляется)
├── main.py           # Основной код (обновляется OTA)
├── config.json       # Настройки MQTT
├── version.json      # Версия прошивки
├── requirements.txt  # Python зависимости
├── venv/             # Virtual environment
├── backup/           # Предыдущая версия (для rollback)
└── .health_ok        # Маркер успешной инициализации
```

## OTA-обновления

### Автоматические обновления

Bootstrap проверяет сервер при каждом запуске:
1. Запрашивает `/api/device/manifest`
2. Сравнивает hash/date/version
3. При наличии обновления:
   - Создаёт backup
   - Скачивает новую версию
   - Проверяет hash
   - Запускает health check
   - При ошибке — откат на backup

### Принудительное обновление

Через Telegram бот: **Админ → ⚙️ Force Update**

Или на устройстве:
```bash
rm ~/co2-monitor/version.json
sudo systemctl restart co2-monitor
```

### Exit codes

| Код | Значение | Действие bootstrap |
|-----|----------|-------------------|
| 0 | Нормальный выход | Остановить сервис |
| 100 | Force update | Перезапустить и проверить обновления |
| другой | Ошибка | Подождать 30 сек и перезапустить |

## Оборудование

### Поддерживаемые датчики

| Датчик | Данные | Подключение |
|--------|--------|-------------|
| **SCD41** (рекомендуется) | CO2 + Temp + Humidity | I2C |
| MH-Z19 | CO2 | UART |
| DHT22 / AM2302 | Temp + Humidity | GPIO |
| BME280 | Temp + Humidity + Pressure | I2C |

### Подключение SCD41 (I2C)

```
SCD41       Raspberry Pi
-----       ------------
VCC    ->   3.3V (pin 1)
GND    ->   GND (pin 9)
SDA    ->   GPIO2/SDA (pin 3)
SCL    ->   GPIO3/SCL (pin 5)
```

Включить I2C:
```bash
sudo raspi-config
# Interface Options -> I2C -> Yes
sudo reboot
```

Проверить подключение:
```bash
i2cdetect -y 1
# Должен показать адрес 0x62
```

### Подключение SSD1306 дисплея (I2C)

```
SSD1306     Raspberry Pi
-------     ------------
VCC    ->   3.3V (pin 1)
GND    ->   GND (pin 9)
SDA    ->   GPIO2/SDA (pin 3)
SCL    ->   GPIO3/SCL (pin 5)
```

Адрес: 0x3C (обычно) или 0x3D

### Подключение MH-Z19 (UART)

```
MH-Z19      Raspberry Pi
------      ------------
VCC    ->   5V (pin 2)
GND    ->   GND (pin 6)
TX     ->   GPIO15/RXD (pin 10)
RX     ->   GPIO14/TXD (pin 8)
```

Включить UART:
```bash
sudo raspi-config
# Interface Options -> Serial Port -> No (login shell) -> Yes (hardware)
sudo reboot
```

## Конфигурация

### config.json

```json
{
  "mqtt_broker": "31.59.170.64",
  "mqtt_port": 10883,
  "send_interval": 60,
  "device_uid": "auto-generated",
  "device_name": ""
}
```

### Удалённая настройка через MQTT

Устройство подписано на `devices/{DEVICE_UID}/config`:

```json
{"send_interval": 30}
```

Команды через `devices/{DEVICE_UID}/command`:
- `{"command": "force_update"}` — перезапустить с проверкой обновлений
- `{"command": "restart"}` — просто перезапустить

## Управление сервисом

```bash
# Статус
sudo systemctl status co2-monitor

# Логи (realtime)
journalctl -u co2-monitor -f

# Логи (последние 50 строк)
journalctl -u co2-monitor -n 50

# Перезапуск
sudo systemctl restart co2-monitor

# Остановка
sudo systemctl stop co2-monitor
```

## Troubleshooting

### Устройство показывает старую версию

```bash
cat ~/co2-monitor/version.json
# Если версия старая:
rm ~/co2-monitor/version.json
sudo systemctl restart co2-monitor
```

### Health check failed

```bash
journalctl -u co2-monitor -n 50

# "No backup available" — нормально при первой установке
# При ошибках в коде — main.py не создаёт .health_ok
```

### Датчик не инициализируется

```bash
# Проверить I2C
i2cdetect -y 1

# Должны быть адреса:
# 0x62 — SCD41
# 0x3C — SSD1306
```

### MQTT не подключается

```bash
# Проверить конфиг
cat ~/co2-monitor/config.json

# Проверить соединение с сервером
curl http://31.59.170.64:10900/health
```

### Полная переустановка

```bash
sudo systemctl stop co2-monitor
rm -rf ~/co2-monitor
curl -sL http://31.59.170.64:10900/install.py | python3
sudo bash ~/co2-monitor/install_service.sh
```

## Файлы

| Файл | Описание | Обновляется OTA |
|------|----------|-----------------|
| `bootstrap.py` | OTA loader, health check, rollback | ❌ Никогда |
| `main.py` | Основная логика, датчики, MQTT | ✅ Да |
| `config.json` | Настройки MQTT | ✅ Да |
| `version.json` | Версия прошивки | ✅ Да |
| `install_service.sh` | Установка systemd | ❌ Только при переустановке |

## Зависимости

```
paho-mqtt>=2.0.0
adafruit-circuitpython-scd4x
adafruit-circuitpython-ssd1306
```

## Привязка к пользователю

1. После первой отправки данных устройство появляется в БД
2. Генерируется 8-символьный код активации
3. Пользователь вводит код в боте: `/bind XXXXXXXX`
4. Устройство привязывается к Telegram аккаунту

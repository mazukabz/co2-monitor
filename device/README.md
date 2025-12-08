# CO2 Monitor - Device Firmware

This folder contains the device firmware (`co2_sensor.py`) which is served to devices by the API server.

## Installation on Raspberry Pi

One command:
```bash
curl -sL http://31.59.170.64:10900/install.py | python3
```

This downloads and installs everything automatically.

## What Gets Installed

The server packages everything into a tar.gz:
- `main.py` - Main device script (this co2_sensor.py)
- `config.json` - MQTT broker settings
- `version.json` - Firmware version info
- `requirements.txt` - Python dependencies
- `update.py` - Check for updates
- `install_service.sh` - Systemd service installer

## Configuration

After installation, edit `~/co2-monitor/config.json` or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | 31.59.170.64 | Server IP address |
| `MQTT_PORT` | 10883 | MQTT port |
| `DEVICE_UID` | auto-generated | Unique device ID |
| `DEVICE_NAME` | empty | Friendly name for bot |
| `SEND_INTERVAL` | 60 | Seconds between readings |
| `DEMO_MODE` | false | Use fake sensor data |

### Remote Configuration via MQTT

The device subscribes to `devices/{DEVICE_UID}/config` topic and automatically applies settings:

```json
{"send_interval": 30}
```

Admin can change interval via Telegram bot: `/admin` → Управление устройствами → выбрать устройство → выбрать интервал.

Settings are pushed immediately via MQTT and also saved in database (applied on next connect if device was offline).

## Hardware Setup

### Supported Sensors

| Sensor | Type | Connection |
|--------|------|------------|
| MH-Z19 | CO2 | UART (GPIO 14/15) |
| DHT22 / AM2302 | Temp + Humidity | GPIO 4 |
| BME280 | Temp + Humidity + Pressure | I2C |

### Wiring MH-Z19 (CO2)

```
MH-Z19      Raspberry Pi
------      ------------
VCC    ->   5V (pin 2)
GND    ->   GND (pin 6)
TX     ->   GPIO15/RXD (pin 10)
RX     ->   GPIO14/TXD (pin 8)
```

Enable UART on Raspberry Pi:
```bash
sudo raspi-config
# Interface Options -> Serial Port -> No (login shell) -> Yes (hardware)
sudo reboot
```

### Wiring DHT22 (Temperature + Humidity)

```
DHT22       Raspberry Pi
-----       ------------
VCC    ->   3.3V (pin 1)
DATA   ->   GPIO4 (pin 7)
GND    ->   GND (pin 9)
```

Add 10K pull-up resistor between VCC and DATA.

## Auto-Start as Service

After installation:
```bash
cd ~/co2-monitor
sudo bash install_service.sh
```

Check status:
```bash
sudo systemctl status co2-monitor
journalctl -u co2-monitor -f
```

## Updates

Check for updates:
```bash
cd ~/co2-monitor
python3 update.py
```

If update available, re-run install:
```bash
curl -sL http://31.59.170.64:10900/install.py | python3
sudo systemctl restart co2-monitor
```

## Device Binding

After first telemetry is sent:
1. Device appears in database with activation code
2. Admin can view code in database or logs
3. User enters code in Telegram bot via `/bind` command

## Troubleshooting

### UART not working
```bash
# Check if serial is enabled
ls -la /dev/serial0

# Test MH-Z19
python3 -c "from co2_sensor import MHZ19Sensor; print(MHZ19Sensor().read())"
```

### DHT22 not working
```bash
# Install GPIO library
sudo apt-get install libgpiod2

# Test DHT22
python3 -c "from co2_sensor import DHT22Sensor; print(DHT22Sensor().read())"
```

### Connection issues
```bash
# Test MQTT connection
mosquitto_pub -h 31.59.170.64 -p 10883 -t test -m "hello"
```

#!/usr/bin/env python3
"""
CO2 Monitor - Raspberry Pi Device Client

This script runs on Raspberry Pi and:
1. Reads CO2, temperature, humidity from sensors
2. Sends telemetry to MQTT broker every N seconds
3. Auto-reconnects if connection lost
4. Auto-updates from server (OTA)

Requirements:
    pip install paho-mqtt

Sensor support:
    - MH-Z19 (CO2 via UART)
    - DHT22 / AM2302 (Temperature, Humidity)
    - BME280 (Temperature, Humidity, Pressure)

Configuration:
    Edit CONFIG section below or use environment variables
"""

import json
import os
import socket
import time
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt

# ==================== CONFIG ====================

def load_config() -> dict:
    """Load config from file or environment."""
    config = {
        "MQTT_BROKER": "31.59.170.64",
        "MQTT_PORT": 10883,
        "DEVICE_UID": "",
        "DEVICE_NAME": "",
        "FIRMWARE_VERSION": "1.0.0",
        "SEND_INTERVAL": 60,
        "DEMO_MODE": False,
    }

    # Load from config file if available (set by bootstrap.py)
    config_file = os.getenv("CO2_CONFIG_FILE", "")
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                file_config = json.load(f)
                config["MQTT_BROKER"] = file_config.get("mqtt_broker", config["MQTT_BROKER"])
                config["MQTT_PORT"] = int(file_config.get("mqtt_port", config["MQTT_PORT"]))
                config["DEVICE_UID"] = file_config.get("device_uid", config["DEVICE_UID"])
                config["DEVICE_NAME"] = file_config.get("device_name", config["DEVICE_NAME"])
                config["SEND_INTERVAL"] = int(file_config.get("send_interval", config["SEND_INTERVAL"]))
                print(f"Loaded config from {config_file}")
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")

    # Environment variables override file config
    config["MQTT_BROKER"] = os.getenv("MQTT_BROKER", config["MQTT_BROKER"])
    config["MQTT_PORT"] = int(os.getenv("MQTT_PORT", str(config["MQTT_PORT"])))
    config["DEVICE_UID"] = os.getenv("CO2_DEVICE_UID", os.getenv("DEVICE_UID", config["DEVICE_UID"]))
    config["DEVICE_NAME"] = os.getenv("DEVICE_NAME", config["DEVICE_NAME"])
    config["SEND_INTERVAL"] = int(os.getenv("SEND_INTERVAL", str(config["SEND_INTERVAL"])))
    config["DEMO_MODE"] = os.getenv("DEMO_MODE", "false").lower() == "true"

    return config


CONFIG = load_config()

# ==================== DEVICE UID ====================

def get_or_create_device_uid() -> str:
    """Get existing device UID or create new one."""
    if CONFIG["DEVICE_UID"]:
        return CONFIG["DEVICE_UID"]

    # Try to load from file
    uid_file = os.path.expanduser("~/.co2_device_uid")

    if os.path.exists(uid_file):
        with open(uid_file, "r") as f:
            return f.read().strip()

    # Generate new UID based on MAC address
    mac = uuid.getnode()
    device_uid = f"rpi_{mac:012x}"

    # Save for future runs
    with open(uid_file, "w") as f:
        f.write(device_uid)

    print(f"Generated new Device UID: {device_uid}")
    return device_uid


def get_local_ip() -> str:
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


# ==================== SENSORS ====================

class DemoSensor:
    """Fake sensor for testing (generates random data)."""

    def __init__(self):
        import random
        self.random = random

    def read(self) -> dict:
        """Generate random sensor data."""
        return {
            "co2": self.random.randint(400, 1200),
            "temperature": round(self.random.uniform(18, 28), 1),
            "humidity": round(self.random.uniform(30, 70), 1),
        }


class MHZ19Sensor:
    """MH-Z19 CO2 sensor via UART."""

    def __init__(self, serial_port: str = "/dev/serial0"):
        try:
            import serial
            self.serial = serial.Serial(
                serial_port,
                baudrate=9600,
                timeout=1
            )
        except ImportError:
            raise ImportError("Install pyserial: pip install pyserial")
        except Exception as e:
            raise Exception(f"Cannot open serial port {serial_port}: {e}")

    def read(self) -> dict:
        """Read CO2 value from MH-Z19."""
        # Send read command
        cmd = bytes([0xFF, 0x01, 0x86, 0x00, 0x00, 0x00, 0x00, 0x00, 0x79])
        self.serial.write(cmd)
        time.sleep(0.1)

        response = self.serial.read(9)
        if len(response) != 9 or response[0] != 0xFF or response[1] != 0x86:
            raise Exception("Invalid MH-Z19 response")

        co2 = response[2] * 256 + response[3]
        return {"co2": co2}


class DHT22Sensor:
    """DHT22 / AM2302 temperature and humidity sensor."""

    def __init__(self, gpio_pin: int = 4):
        try:
            import adafruit_dht
            import board
            # Get GPIO pin
            pin = getattr(board, f"D{gpio_pin}")
            self.dht = adafruit_dht.DHT22(pin)
        except ImportError:
            raise ImportError(
                "Install Adafruit DHT library:\n"
                "pip install adafruit-circuitpython-dht\n"
                "sudo apt-get install libgpiod2"
            )

    def read(self) -> dict:
        """Read temperature and humidity from DHT22."""
        for _ in range(3):  # Retry up to 3 times
            try:
                return {
                    "temperature": round(self.dht.temperature, 1),
                    "humidity": round(self.dht.humidity, 1),
                }
            except RuntimeError:
                time.sleep(2)
        raise Exception("Failed to read DHT22")


class CombinedSensor:
    """Combines multiple sensors into one reading."""

    def __init__(self, sensors: list):
        self.sensors = sensors

    def read(self) -> dict:
        """Read from all sensors and combine results."""
        result = {}
        for sensor in self.sensors:
            try:
                data = sensor.read()
                result.update(data)
            except Exception as e:
                print(f"Warning: Failed to read from {type(sensor).__name__}: {e}")
        return result


# ==================== MQTT CLIENT ====================

class CO2DeviceClient:
    """MQTT client for CO2 device."""

    def __init__(self, sensor):
        self.sensor = sensor
        self.device_uid = get_or_create_device_uid()
        self.local_ip = get_local_ip()

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"co2_device_{self.device_uid}"
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.connected = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Called when connected to broker."""
        if reason_code == 0:
            print(f"[{datetime.now():%H:%M:%S}] Connected to MQTT broker")
            self.connected = True
        else:
            print(f"[{datetime.now():%H:%M:%S}] Connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Called when disconnected."""
        print(f"[{datetime.now():%H:%M:%S}] Disconnected from broker")
        self.connected = False

    def connect(self):
        """Connect to MQTT broker."""
        print(f"Connecting to {CONFIG['MQTT_BROKER']}:{CONFIG['MQTT_PORT']}...")
        self.client.connect(
            CONFIG["MQTT_BROKER"],
            CONFIG["MQTT_PORT"],
            keepalive=60
        )
        self.client.loop_start()

    def send_telemetry(self):
        """Read sensors and send telemetry."""
        try:
            # Read sensor data
            data = self.sensor.read()

            # Build telemetry message
            payload = {
                **data,
                "device_uid": self.device_uid,
                "name": CONFIG["DEVICE_NAME"] or None,
                "firmware_version": CONFIG["FIRMWARE_VERSION"],
                "ip": self.local_ip,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Publish to MQTT
            topic = f"devices/{self.device_uid}/telemetry"
            self.client.publish(topic, json.dumps(payload), qos=1)

            print(
                f"[{datetime.now():%H:%M:%S}] Sent: "
                f"CO2={data.get('co2', '?')}ppm, "
                f"T={data.get('temperature', '?')}C, "
                f"H={data.get('humidity', '?')}%"
            )

        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] Error: {e}")

    def run(self):
        """Main loop - connect and send telemetry."""
        print("=" * 50)
        print("CO2 Monitor Device")
        print("=" * 50)
        print(f"Device UID: {self.device_uid}")
        print(f"Local IP: {self.local_ip}")
        print(f"Broker: {CONFIG['MQTT_BROKER']}:{CONFIG['MQTT_PORT']}")
        print(f"Send interval: {CONFIG['SEND_INTERVAL']}s")
        print("=" * 50)
        print()

        self.connect()

        # Wait for connection
        for i in range(10):
            if self.connected:
                break
            time.sleep(1)
            print(f"Waiting for connection... ({i+1}/10)")

        if not self.connected:
            print("Failed to connect after 10 seconds")
            return

        # Main loop
        print("\nStarting telemetry loop (Ctrl+C to stop)...\n")

        try:
            while True:
                if self.connected:
                    self.send_telemetry()
                else:
                    print("Not connected, attempting reconnect...")
                    try:
                        self.client.reconnect()
                    except Exception:
                        pass

                time.sleep(CONFIG["SEND_INTERVAL"])

        except KeyboardInterrupt:
            print("\nShutting down...")

        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("Goodbye!")


# ==================== MAIN ====================

def create_sensor():
    """Create sensor instance based on config."""
    if CONFIG["DEMO_MODE"]:
        print("Running in DEMO mode (fake sensor data)")
        return DemoSensor()

    sensors = []

    # Try to initialize MH-Z19 (CO2)
    try:
        mhz19 = MHZ19Sensor()
        sensors.append(mhz19)
        print("Initialized MH-Z19 CO2 sensor")
    except Exception as e:
        print(f"MH-Z19 not available: {e}")

    # Try to initialize DHT22 (Temperature, Humidity)
    try:
        dht22 = DHT22Sensor(gpio_pin=4)
        sensors.append(dht22)
        print("Initialized DHT22 sensor")
    except Exception as e:
        print(f"DHT22 not available: {e}")

    if not sensors:
        print("No sensors available! Running in demo mode.")
        return DemoSensor()

    return CombinedSensor(sensors)


def main():
    """Entry point."""
    sensor = create_sensor()
    client = CO2DeviceClient(sensor)
    client.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
CO2 Monitor - Main Device Script v2.0.0

This script is updated via OTA from server.
It reads SCD41 sensor data and sends to MQTT broker.

Features:
- Real SCD41 sensor support (CO2, temperature, humidity)
- Health check for bootstrap validation
- MQTT telemetry with auto-reconnect
- Remote configuration updates
- Force update command via MQTT
"""

import json
import os
import signal
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

# ==================== CONFIGURATION ====================

INSTALL_DIR = Path(__file__).parent
CONFIG_FILE = INSTALL_DIR / "config.json"
HEALTH_FILE = INSTALL_DIR / ".health_ok"
VERSION_FILE = INSTALL_DIR / "version.json"

# Default config (overridden by config.json)
DEFAULT_CONFIG = {
    "mqtt_broker": "31.59.170.64",
    "mqtt_port": 10883,
    "send_interval": 60,
    "device_uid": "",
    "device_name": "CO2 Monitor",
}


def load_config() -> dict:
    """Load configuration from file."""
    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"Warning: Could not load config: {e}")

    # Environment overrides
    config["mqtt_broker"] = os.getenv("MQTT_BROKER", config["mqtt_broker"])
    config["mqtt_port"] = int(os.getenv("MQTT_PORT", str(config["mqtt_port"])))
    config["send_interval"] = int(os.getenv("SEND_INTERVAL", str(config["send_interval"])))
    config["device_uid"] = os.getenv("DEVICE_UID", config["device_uid"])

    return config


def get_version() -> str:
    """Get current firmware version."""
    if VERSION_FILE.exists():
        try:
            with open(VERSION_FILE) as f:
                return json.load(f).get("version", "unknown")
        except Exception:
            pass
    return "unknown"


# ==================== DEVICE UID ====================

def get_device_uid(config: dict) -> str:
    """Get or generate device UID."""
    if config.get("device_uid"):
        return config["device_uid"]

    uid_file = INSTALL_DIR / ".device_uid"
    if uid_file.exists():
        return uid_file.read_text().strip()

    # Generate from MAC address
    import uuid
    mac = uuid.getnode()
    device_uid = f"rpi_{mac:012x}"
    uid_file.write_text(device_uid)

    return device_uid


def get_local_ip() -> str:
    """Get device IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def get_os_info() -> str:
    """Get OS version info (e.g., 'Debian 12 bookworm' or 'Raspbian 11 bullseye')."""
    try:
        # Try /etc/os-release first (most Linux distros)
        os_release = Path("/etc/os-release")
        if os_release.exists():
            info = {}
            for line in os_release.read_text().splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    info[key] = value.strip('"')
            # Format: "Debian 12 (bookworm)" or "Raspbian GNU/Linux 11 (bullseye)"
            name = info.get("PRETTY_NAME", "")
            if name:
                return name
            # Fallback to ID + VERSION_ID
            return f"{info.get('ID', 'Linux')} {info.get('VERSION_ID', '')}"
    except Exception:
        pass

    # Fallback to platform module
    try:
        import platform
        return f"{platform.system()} {platform.release()}"
    except Exception:
        return "unknown"


# ==================== SCD41 SENSOR ====================

class SCD41Sensor:
    """Sensirion SCD41 CO2/Temperature/Humidity sensor via I2C."""

    def __init__(self):
        self.scd4x = None
        self.initialized = False
        self._last_valid_reading = None
        self._readings_to_skip = 2  # Skip first readings after init

    def init(self) -> bool:
        """Initialize SCD41 sensor."""
        try:
            import board
            import adafruit_scd4x

            i2c = board.I2C()
            self.scd4x = adafruit_scd4x.SCD4X(i2c)

            # Stop any existing measurements
            self.scd4x.stop_periodic_measurement()
            time.sleep(0.5)

            # Start periodic measurement (every 5 seconds internally)
            self.scd4x.start_periodic_measurement()

            # Wait for first measurement
            print("Waiting for SCD41 to warm up...")
            time.sleep(5)

            self.initialized = True
            print("SCD41 sensor initialized")
            return True

        except ImportError as e:
            print(f"SCD41 library not installed: {e}")
            print("Install with: pip install adafruit-circuitpython-scd4x")
            return False
        except Exception as e:
            print(f"SCD41 init error: {e}")
            return False

    def read(self) -> dict | None:
        """Read sensor data with validation."""
        if not self.initialized or self.scd4x is None:
            # No demo mode in production - return None if sensor not working
            return None

        try:
            # Wait for data to be ready
            if not self.scd4x.data_ready:
                time.sleep(1)
                if not self.scd4x.data_ready:
                    print("SCD41: Data not ready")
                    return self._last_valid_reading

            co2 = self.scd4x.CO2
            temperature = self.scd4x.temperature
            humidity = self.scd4x.relative_humidity

            # Skip first readings (often garbage)
            if self._readings_to_skip > 0:
                self._readings_to_skip -= 1
                print(f"Skipping initial reading {2 - self._readings_to_skip}/2")
                return None

            # Validate readings
            if not self._validate_reading(co2, temperature, humidity):
                print(f"Invalid reading: CO2={co2}, T={temperature}, H={humidity}")
                return self._last_valid_reading

            reading = {
                "co2": int(co2),
                "temperature": round(temperature, 1),
                "humidity": round(humidity, 1),
            }

            self._last_valid_reading = reading
            return reading

        except Exception as e:
            print(f"SCD41 read error: {e}")
            return self._last_valid_reading

    def _validate_reading(self, co2: int, temp: float, humidity: float) -> bool:
        """Validate sensor readings are within reasonable bounds."""
        # CO2: 400-5000 ppm is normal range
        if not (300 <= co2 <= 10000):
            return False

        # Temperature: -10 to 50 C is reasonable indoor range
        if not (-10 <= temp <= 50):
            return False

        # Humidity: 0-100%
        if not (0 <= humidity <= 100):
            return False

        # Check for sudden jumps (if we have previous reading)
        if self._last_valid_reading:
            last_co2 = self._last_valid_reading["co2"]
            last_temp = self._last_valid_reading["temperature"]

            # CO2 shouldn't jump more than 500 ppm per reading
            if abs(co2 - last_co2) > 500:
                print(f"CO2 jump too large: {last_co2} -> {co2}")
                return False

            # Temperature shouldn't jump more than 3C per reading
            if abs(temp - last_temp) > 3:
                print(f"Temperature jump too large: {last_temp} -> {temp}")
                return False

        return True

    def stop(self):
        """Stop sensor measurements."""
        if self.scd4x:
            try:
                self.scd4x.stop_periodic_measurement()
            except Exception:
                pass


# ==================== DISPLAY (SSD1306 OLED) ====================

def ensure_font_file() -> bool:
    """
    Download font5x8.bin if not present.
    Required by adafruit_framebuf for text display.
    """
    font_file = INSTALL_DIR / "font5x8.bin"
    if font_file.exists():
        return True

    font_url = "https://github.com/adafruit/Adafruit_CircuitPython_framebuf/raw/main/examples/font5x8.bin"

    try:
        from urllib.request import urlopen
        print("Downloading font5x8.bin for display...")
        response = urlopen(font_url, timeout=30)
        content = response.read()

        with open(font_file, "wb") as f:
            f.write(content)

        print(f"Font file downloaded ({len(content)} bytes)")
        return True
    except Exception as e:
        print(f"Failed to download font file: {e}")
        return False


class Display:
    """SSD1306 OLED Display (128x64) via I2C."""

    def __init__(self):
        self.display = None
        self.initialized = False

    def init(self) -> bool:
        """Initialize SSD1306 OLED display."""
        try:
            # Ensure font file exists (required for text display)
            ensure_font_file()

            import board
            import adafruit_ssd1306

            i2c = board.I2C()
            self.display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
            self.display.fill(0)
            self.display.show()

            self.initialized = True
            print("Display initialized (SSD1306 128x64)")
            return True

        except ImportError as e:
            print(f"Display library not installed: {e}")
            print("Install with: pip install adafruit-circuitpython-ssd1306")
            return False
        except Exception as e:
            print(f"Display init error (continuing without display): {e}")
            return False

    def show(self, co2: int, temp: float, humidity: float):
        """Display sensor readings."""
        if not self.initialized or self.display is None:
            return

        try:
            self.display.fill(0)

            # CO2 level - large text at top
            co2_text = f"CO2: {co2} ppm"
            self.display.text(co2_text, 0, 0, 1)

            # Status indicator based on CO2 level
            if co2 < 800:
                status = "Good"
            elif co2 < 1000:
                status = "OK"
            elif co2 < 1500:
                status = "Ventilate!"
            else:
                status = "CRITICAL!"
            self.display.text(status, 0, 16, 1)

            # Temperature and humidity
            self.display.text(f"Temp: {temp:.1f} C", 0, 32, 1)
            self.display.text(f"Hum:  {humidity:.0f} %", 0, 48, 1)

            self.display.show()

        except Exception as e:
            print(f"Display error: {e}")

    def show_status(self, message: str):
        """Show status message on display."""
        if not self.initialized or self.display is None:
            return

        try:
            self.display.fill(0)
            self.display.text(message, 0, 28, 1)
            self.display.show()
        except Exception:
            pass

    def clear(self):
        """Clear the display."""
        if not self.initialized or self.display is None:
            return

        try:
            self.display.fill(0)
            self.display.show()
        except Exception:
            pass


# ==================== MQTT CLIENT ====================

class CO2MQTTClient:
    """MQTT client for telemetry and commands."""

    def __init__(self, config: dict, sensor: SCD41Sensor, display: Display = None):
        import paho.mqtt.client as mqtt

        self.config = config
        self.sensor = sensor
        self.display = display
        self.device_uid = get_device_uid(config)
        self.version = get_version()
        self.local_ip = get_local_ip()
        self.os_version = get_os_info()
        self.start_time = time.time()

        # MQTT topics
        self.topic_telemetry = f"devices/{self.device_uid}/telemetry"
        self.topic_config = f"devices/{self.device_uid}/config"
        self.topic_commands = f"devices/{self.device_uid}/commands"
        self.topic_status = f"devices/{self.device_uid}/status"

        # MQTT client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Set Last Will (offline when disconnected)
        self.client.will_set(self.topic_status, "offline", retain=True)

        self.connected = False
        self.running = False
        self._force_update_requested = False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT connection."""
        if reason_code == 0:
            print(f"[{datetime.now():%H:%M:%S}] Connected to MQTT broker")
            self.connected = True

            # Subscribe to config and commands
            client.subscribe(self.topic_config)
            client.subscribe(self.topic_commands)

            # Announce online
            client.publish(self.topic_status, "online", retain=True)
        else:
            print(f"[{datetime.now():%H:%M:%S}] Connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Handle MQTT disconnection."""
        print(f"[{datetime.now():%H:%M:%S}] Disconnected: {reason_code}")
        self.connected = False

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode())
            print(f"[{datetime.now():%H:%M:%S}] Received: {msg.topic} -> {payload}")

            if msg.topic == self.topic_config:
                self._apply_config(payload)
            elif msg.topic == self.topic_commands:
                self._execute_command(payload)

        except Exception as e:
            print(f"Error processing message: {e}")

    def _apply_config(self, new_config: dict):
        """Apply new configuration from server."""
        if "send_interval" in new_config:
            self.config["send_interval"] = new_config["send_interval"]
            print(f"Send interval updated to {self.config['send_interval']}s")

            # Save to config file
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self.config, f, indent=2)
            except Exception:
                pass

    def _execute_command(self, command: dict):
        """Execute command from server."""
        cmd = command.get("command", "")

        if cmd == "restart":
            print("Restart command received")
            self.running = False

        elif cmd == "force_update":
            print("Force update command received")
            self._force_update_requested = True
            self.running = False

        elif cmd == "status":
            # Send immediate status
            self._send_telemetry()

    def _send_telemetry(self) -> bool:
        """Send sensor data to server and update display."""
        data = self.sensor.read()
        if data is None:
            return False

        # Update display with current readings
        if self.display:
            self.display.show(data["co2"], data["temperature"], data["humidity"])

        payload = {
            "device_uid": self.device_uid,
            "co2": data["co2"],
            "temperature": data["temperature"],
            "humidity": data["humidity"],
            "timestamp": datetime.utcnow().isoformat(),
            "ip": self.local_ip,
            "firmware_version": self.version,
            "os_version": self.os_version,
            "uptime": int(time.time() - self.start_time),
        }

        try:
            self.client.publish(self.topic_telemetry, json.dumps(payload), qos=1)
            print(
                f"[{datetime.now():%H:%M:%S}] "
                f"CO2={data['co2']}ppm T={data['temperature']}C H={data['humidity']}%"
            )
            return True
        except Exception as e:
            print(f"Failed to send telemetry: {e}")
            return False

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            print(f"Connecting to {self.config['mqtt_broker']}:{self.config['mqtt_port']}...")
            self.client.connect(
                self.config["mqtt_broker"],
                self.config["mqtt_port"],
                keepalive=60,
            )
            self.client.loop_start()

            # Wait for connection
            for _ in range(10):
                if self.connected:
                    return True
                time.sleep(1)

            return self.connected
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def run(self):
        """Main telemetry loop."""
        if not self.connect():
            print("Failed to connect to MQTT broker")
            return

        self.running = True
        last_send = 0

        try:
            while self.running:
                now = time.time()

                # Send telemetry at interval
                if now - last_send >= self.config["send_interval"]:
                    if self.connected:
                        self._send_telemetry()
                    else:
                        print("Not connected, attempting reconnect...")
                        try:
                            self.client.reconnect()
                        except Exception:
                            pass

                    last_send = now

                time.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.client.publish(self.topic_status, "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()

        # Return whether force update was requested
        return self._force_update_requested

    def stop(self):
        """Stop the client."""
        self.running = False


# ==================== HEALTH CHECK ====================

def run_health_check(sensor: SCD41Sensor, config: dict) -> bool:
    """
    Run health check for bootstrap validation.
    Creates .health_ok file if everything works.
    """
    print("Running health check...")

    # 1. Check sensor initialization
    if not sensor.init():
        print("Health check FAILED: Sensor init failed")
        return False

    # 2. Try to read sensor (need multiple attempts because first 2 readings are skipped)
    reading = None
    for attempt in range(5):  # 5 attempts to account for 2 skipped readings
        time.sleep(5)  # Wait for sensor
        reading = sensor.read()
        if reading is not None:
            break
        print(f"Health check: Waiting for sensor (attempt {attempt + 1}/5)...")

    if reading is None:
        print("Health check FAILED: Cannot read sensor after 5 attempts")
        return False

    print(f"Health check: Sensor OK - CO2={reading['co2']}ppm")

    # 3. Check MQTT connectivity
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        connected = False

        def on_connect(c, u, f, rc, p):
            nonlocal connected
            connected = rc == 0

        client.on_connect = on_connect
        client.connect(config["mqtt_broker"], config["mqtt_port"], keepalive=10)
        client.loop_start()

        for _ in range(5):
            if connected:
                break
            time.sleep(1)

        client.loop_stop()
        client.disconnect()

        if not connected:
            print("Health check FAILED: Cannot connect to MQTT")
            return False

        print("Health check: MQTT OK")

    except Exception as e:
        print(f"Health check FAILED: MQTT error - {e}")
        return False

    # 4. All checks passed - create health file
    try:
        HEALTH_FILE.write_text(datetime.utcnow().isoformat())
        print("Health check PASSED")
        return True
    except Exception as e:
        print(f"Health check FAILED: Cannot write health file - {e}")
        return False


# ==================== MAIN ====================

def main():
    """Main entry point."""
    config = load_config()
    version = get_version()

    print("=" * 50)
    print(f"CO2 Monitor v{version}")
    print("=" * 50)
    print(f"Device UID: {get_device_uid(config)}")
    print(f"MQTT: {config['mqtt_broker']}:{config['mqtt_port']}")
    print(f"Interval: {config['send_interval']}s")
    print("=" * 50)

    # Check if running in health check mode
    if "--health-check" in sys.argv:
        sensor = SCD41Sensor()
        success = run_health_check(sensor, config)
        sensor.stop()
        sys.exit(0 if success else 1)

    # Initialize display (optional - continues without if not available)
    display = Display()
    display.init()
    display.show_status("Starting...")

    # Initialize sensor
    sensor = SCD41Sensor()
    if not sensor.init():
        print("ERROR: Sensor init failed! Check I2C connection.")
        print("Device will not send data until sensor is working.")
        display.show_status("Sensor ERROR!")

    display.show_status("Connecting...")

    # Create MQTT client with sensor and display
    client = CO2MQTTClient(config, sensor, display)

    # Handle signals for graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutdown signal received")
        client.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run main loop
    force_update = client.run()

    # Cleanup
    sensor.stop()
    display.clear()

    # If force update was requested, exit with special code
    if force_update:
        print("Force update requested, restarting bootstrap...")
        # Remove version file to force re-download
        VERSION_FILE.unlink(missing_ok=True)
        sys.exit(100)  # Special exit code for bootstrap

    print("Goodbye!")


if __name__ == "__main__":
    main()

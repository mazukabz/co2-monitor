#!/usr/bin/env python3
"""
CO2 Monitor - Main Device Script v2.3.0

This script is updated via OTA from server.
It reads SCD41 sensor data and sends to MQTT broker.

Features:
- Real SCD41 sensor support (CO2, temperature, humidity)
- No data filtering - real values always (SCD41 has built-in filtering)
- MQTT telemetry with auto-reconnect
- Remote configuration updates
- Smart polling: display every 5s, MQTT at send_interval
- Live mode: high-frequency telemetry (5s) for specified duration
- Display control: enable/disable OLED via MQTT command
- Smart display caching: avoids flickering when sensor temporarily not ready (15s cache)
- Manual CO2 calibration via MQTT command (force_calibration to 420 ppm)
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
        self._readings_to_skip = 2  # Skip first 2 readings (sensor warmup)

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
        """
        Read sensor data.

        Returns actual sensor reading or None if not available.
        Never returns cached/old values - we want real data always.
        """
        if not self.initialized or self.scd4x is None:
            return None

        try:
            # Wait for data to be ready
            if not self.scd4x.data_ready:
                time.sleep(1)
                if not self.scd4x.data_ready:
                    print("SCD41: Data not ready")
                    return None

            co2 = self.scd4x.CO2
            temperature = self.scd4x.temperature
            humidity = self.scd4x.relative_humidity

            # Skip first 2 readings (sensor warmup)
            if self._readings_to_skip > 0:
                self._readings_to_skip -= 1
                print(f"Skipping warmup reading {2 - self._readings_to_skip}/2")
                return None

            # Basic physical bounds check only
            # CO2: 0-40000 ppm (SCD41 range)
            # Temp: -10 to 60 C (SCD41 operating range)
            # Humidity: 0-100%
            if not (0 <= co2 <= 40000):
                print(f"CO2 out of range: {co2}")
                return None
            if not (-10 <= temperature <= 60):
                print(f"Temperature out of range: {temperature}")
                return None
            if not (0 <= humidity <= 100):
                print(f"Humidity out of range: {humidity}")
                return None

            return {
                "co2": int(co2),
                "temperature": round(temperature, 1),
                "humidity": round(humidity, 1),
            }

        except Exception as e:
            print(f"SCD41 read error: {e}")
            return None

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
    """SSD1306 OLED Display (128x64) via I2C with big digit support."""

    # Compact 5x7 digit font as bytes (each byte = 1 row, bits = pixels)
    # Bit order: b5 b4 b3 b2 b1 (5 pixels wide)
    FONT = {
        '0': (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
        '1': (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
        '2': (0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F),
        '3': (0x1F, 0x01, 0x02, 0x06, 0x01, 0x11, 0x0E),
        '4': (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
        '5': (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E),
        '6': (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E),
        '7': (0x1F, 0x01, 0x02, 0x04, 0x04, 0x04, 0x04),
        '8': (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
        '9': (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C),
    }

    def __init__(self):
        self.display = None
        self.initialized = False

    def init(self) -> bool:
        """Initialize SSD1306 OLED display."""
        try:
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
            return False
        except Exception as e:
            print(f"Display init error: {e}")
            return False

    def big_text(self, text: str, x: int, y: int, scale: int = 4):
        """Draw text with big scaled digits at (x, y)."""
        if not self.display:
            return
        for char in text:
            if char in self.FONT:
                for row_idx, row_byte in enumerate(self.FONT[char]):
                    for bit in range(5):
                        if row_byte & (0x10 >> bit):
                            for dy in range(scale):
                                for dx in range(scale):
                                    px, py = x + bit * scale + dx, y + row_idx * scale + dy
                                    if 0 <= px < 128 and 0 <= py < 64:
                                        self.display.pixel(px, py, 1)
                x += 6 * scale
            elif char == ' ':
                x += 3 * scale

    def big_number(self, num: int, x: int = -1, y: int = 0, scale: int = 4):
        """Draw number with big digits. x=-1 means center horizontally."""
        text = str(num)
        if x < 0:
            x = (128 - len(text) * 6 * scale) // 2
        self.big_text(text, x, y, scale)

    def show(self, co2: int, temp: float, humidity: float):
        """Display CO2 in huge adaptive digits centered on screen."""
        if not self.initialized or not self.display:
            return
        try:
            self.display.fill(0)
            # Adaptive scale: 3 digits (400-999) = scale 7, 4+ digits = scale 5
            scale = 7 if co2 < 1000 else 5
            digit_h = 7 * scale  # 49px for scale=7, 35px for scale=5
            y = (64 - digit_h) // 2  # Center vertically
            self.big_number(co2, y=y, scale=scale)
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

    # Constants
    DISPLAY_INTERVAL = 5  # SCD41 updates every 5 seconds
    LIVE_MODE_INTERVAL = 5  # Send telemetry every 5 seconds in live mode

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

        # Display and live mode state
        self._display_enabled = config.get("display_enabled", True)
        self._live_mode_until = 0  # Unix timestamp when live mode ends (0 = disabled)

        # Cache for display (to avoid flickering when sensor temporarily not ready)
        self._cached_reading = None  # Last successful sensor reading
        self._cached_reading_time = 0  # Timestamp of last successful reading
        self._cache_max_age = 15  # Cache valid for 15 seconds (3 sensor cycles)

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
        changed = False

        if "send_interval" in new_config:
            self.config["send_interval"] = new_config["send_interval"]
            print(f"Send interval updated to {self.config['send_interval']}s")
            changed = True

        if "display_enabled" in new_config:
            self._display_enabled = new_config["display_enabled"]
            self.config["display_enabled"] = new_config["display_enabled"]
            print(f"Display {'enabled' if self._display_enabled else 'disabled'}")
            changed = True

            # Clear display if disabled
            if not self._display_enabled and self.display:
                self.display.clear()

        # Save to config file
        if changed:
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

        elif cmd == "live_mode":
            # Enable live mode for specified duration (minutes)
            duration_minutes = command.get("duration", 5)
            self._live_mode_until = time.time() + (duration_minutes * 60)
            print(f"Live mode enabled for {duration_minutes} minutes")

        elif cmd == "live_mode_off":
            # Disable live mode
            self._live_mode_until = 0
            print("Live mode disabled")

        elif cmd == "display_on":
            self._display_enabled = True
            self.config["display_enabled"] = True
            print("Display enabled")
            # Save to config
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self.config, f, indent=2)
            except Exception:
                pass

        elif cmd == "display_off":
            self._display_enabled = False
            self.config["display_enabled"] = False
            print("Display disabled")
            if self.display:
                self.display.clear()
            # Save to config
            try:
                with open(CONFIG_FILE, "w") as f:
                    json.dump(self.config, f, indent=2)
            except Exception:
                pass

        elif cmd == "calibrate":
            # Force calibration to fresh air level (~420 ppm)
            target_co2 = command.get("target_co2", 420)
            self._perform_calibration(target_co2)

    def _perform_calibration(self, target_co2: int = 420):
        """
        Perform forced recalibration of SCD41 sensor.

        The sensor should be exposed to fresh outdoor air for at least
        3 minutes before calling this. Target CO2 is typically 420 ppm
        (current atmospheric CO2 level).
        """
        if not self.sensor.initialized or self.sensor.scd4x is None:
            print("Calibration failed: sensor not initialized")
            return

        try:
            scd = self.sensor.scd4x

            # Stop periodic measurement for calibration
            scd.stop_periodic_measurement()
            time.sleep(0.5)

            # Perform forced recalibration
            # Note: Sensor should have been measuring for >3 min in stable conditions
            correction = scd.force_calibration(target_co2)
            print(f"Calibration complete! Target: {target_co2} ppm, correction: {correction}")

            # Show on display
            if self.display and self._display_enabled:
                self.display.show_status(f"CAL OK: {correction}")
                time.sleep(2)

            # Restart periodic measurement
            scd.start_periodic_measurement()
            time.sleep(5)  # Wait for first measurement

            print("Sensor recalibrated and restarted")

        except Exception as e:
            print(f"Calibration error: {e}")
            # Try to restart measurement anyway
            try:
                self.sensor.scd4x.start_periodic_measurement()
            except Exception:
                pass

    def _get_display_data(self, fresh_reading: dict | None) -> dict | None:
        """
        Get data for display with smart caching.

        Logic:
        - If fresh_reading available: use it and update cache
        - If no fresh_reading but cache < 15s: use cache (avoid flickering)
        - If no fresh_reading and cache > 15s: return None (sensor error)

        Returns data dict or None if sensor is truly unavailable.
        """
        now = time.time()

        if fresh_reading is not None:
            # Update cache with fresh data
            self._cached_reading = fresh_reading
            self._cached_reading_time = now
            return fresh_reading

        # No fresh reading - check cache validity
        if self._cached_reading is not None:
            cache_age = now - self._cached_reading_time
            if cache_age <= self._cache_max_age:
                # Cache still valid - use it to avoid display flickering
                return self._cached_reading

        # Cache expired or no cache - sensor is truly unavailable
        return None

    def _update_display(self, data: dict):
        """Update display with sensor data."""
        if not self._display_enabled or not self.display:
            return
        self.display.show(data["co2"], data["temperature"], data["humidity"])

    def _send_telemetry(self, data: dict = None) -> bool:
        """Send sensor data to server."""
        # Use provided data or read from sensor
        if data is None:
            data = self.sensor.read()
        if data is None:
            return False

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

    def _is_live_mode_active(self) -> bool:
        """Check if live mode is currently active."""
        if self._live_mode_until == 0:
            return False
        if time.time() > self._live_mode_until:
            # Live mode expired
            self._live_mode_until = 0
            print("Live mode expired")
            return False
        return True

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
        """
        Main telemetry loop with smart polling.

        Polling logic:
        - If display ON: poll every 5 seconds for display, send MQTT at send_interval
        - If live mode ON: poll every 5 seconds, send MQTT every 5 seconds
        - If display OFF and live OFF: poll only at send_interval
        """
        if not self.connect():
            print("Failed to connect to MQTT broker")
            return

        self.running = True
        last_display_update = 0
        last_mqtt_send = 0

        try:
            while self.running:
                now = time.time()

                # Check if live mode is active
                live_mode = self._is_live_mode_active()

                # Determine effective MQTT interval
                mqtt_interval = self.LIVE_MODE_INTERVAL if live_mode else self.config["send_interval"]

                # Determine if we need to poll sensor
                need_display_update = (
                    self._display_enabled and
                    (now - last_display_update >= self.DISPLAY_INTERVAL)
                )
                need_mqtt_send = (now - last_mqtt_send >= mqtt_interval)

                # Read sensor only if needed (single read serves both display and MQTT)
                if need_display_update or need_mqtt_send:
                    if not self.connected:
                        print("Not connected, attempting reconnect...")
                        try:
                            self.client.reconnect()
                        except Exception:
                            pass
                        time.sleep(1)
                        continue

                    # Read sensor once
                    reading = self.sensor.read()

                    # Update display if needed (with smart caching)
                    if need_display_update:
                        display_data = self._get_display_data(reading)
                        if display_data:
                            self._update_display(display_data)
                        else:
                            # Cache expired and no fresh data - sensor truly unavailable
                            if self._display_enabled and self.display:
                                self.display.show_status("SENSOR ERROR")
                        last_display_update = now

                    # Send MQTT only with fresh data (never cached)
                    if need_mqtt_send and reading:
                        self._send_telemetry(reading)
                        last_mqtt_send = now

                # Sleep briefly to avoid busy loop
                time.sleep(0.5)

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

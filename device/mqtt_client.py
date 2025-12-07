#!/usr/bin/env python3
"""
CO2 Monitor Device - MQTT Client
Runs on Raspberry Pi / ESP32

This script:
1. Reads CO2/temperature/humidity from SCD41 sensor
2. Sends data to MQTT broker
3. Displays readings on LCD/OLED (optional, can be disabled)
4. Listens for configuration updates
"""

import json
import time
import socket
from datetime import datetime

import paho.mqtt.client as mqtt

# ==================== CONFIGURATION ====================
# These should be set via environment or config file on device

DEVICE_UID = "co2_001"  # Unique device identifier
MQTT_BROKER = "31.59.170.64"  # Server IP
MQTT_PORT = 10883  # External MQTT port

# Intervals (seconds)
REPORT_INTERVAL = 30  # How often to send data

# Display settings
DISPLAY_ENABLED = True  # Set to False to disable display output

# ==================== MQTT TOPICS ====================
TOPIC_TELEMETRY = f"devices/{DEVICE_UID}/telemetry"
TOPIC_CONFIG = f"devices/{DEVICE_UID}/config"
TOPIC_COMMANDS = f"devices/{DEVICE_UID}/commands"
TOPIC_STATUS = f"devices/{DEVICE_UID}/status"


# ==================== DISPLAY ====================

class Display:
    """LCD/OLED Display wrapper (e.g., SSD1306, LCD1602, etc.)"""

    def __init__(self):
        self.initialized = False
        self.display = None

    def init(self) -> bool:
        """Initialize display."""
        if not DISPLAY_ENABLED:
            print("📺 Display disabled")
            return True

        try:
            # TODO: Add real display initialization
            # For SSD1306 OLED:
            # import board
            # import adafruit_ssd1306
            # i2c = board.I2C()
            # self.display = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

            # For LCD1602 with I2C:
            # from RPLCD.i2c import CharLCD
            # self.display = CharLCD('PCF8574', 0x27)

            self.initialized = True
            print("📺 Display initialized")
            return True
        except Exception as e:
            print(f"⚠️ Display init error (continuing without display): {e}")
            return True  # Don't fail if display not available

    def show(self, co2: int, temp: float, humidity: float):
        """Display readings on screen."""
        if not DISPLAY_ENABLED or not self.initialized:
            return

        try:
            # TODO: Replace with real display code
            # For SSD1306 OLED:
            # self.display.fill(0)
            # self.display.text(f"CO2: {co2} ppm", 0, 0, 1)
            # self.display.text(f"Temp: {temp:.1f} C", 0, 20, 1)
            # self.display.text(f"Hum: {humidity:.0f}%", 0, 40, 1)
            # self.display.show()

            # For LCD1602:
            # self.display.clear()
            # self.display.write_string(f"CO2:{co2}ppm T:{temp:.0f}C")
            # self.display.cursor_pos = (1, 0)
            # self.display.write_string(f"Humidity: {humidity:.0f}%")

            # Console output for testing
            print(f"📺 Display: CO2={co2}ppm | T={temp:.1f}°C | H={humidity:.0f}%")

        except Exception as e:
            print(f"⚠️ Display error: {e}")

    def show_status(self, message: str):
        """Show status message."""
        if not DISPLAY_ENABLED or not self.initialized:
            return
        print(f"📺 Status: {message}")

    def clear(self):
        """Clear display."""
        if not DISPLAY_ENABLED or not self.initialized:
            return
        # TODO: self.display.fill(0) / self.display.clear()


# ==================== SENSOR (mock for now) ====================

class CO2Sensor:
    """SCD41 CO2 Sensor wrapper."""

    def __init__(self):
        self.initialized = False
        # In real implementation, initialize I2C and SCD41 here

    def init(self) -> bool:
        """Initialize sensor."""
        try:
            # TODO: Add real SCD41 initialization
            # import board
            # import adafruit_scd4x
            # i2c = board.I2C()
            # self.scd4x = adafruit_scd4x.SCD4X(i2c)
            # self.scd4x.start_periodic_measurement()
            self.initialized = True
            return True
        except Exception as e:
            print(f"❌ Sensor init error: {e}")
            return False

    def read(self) -> dict | None:
        """Read sensor data."""
        if not self.initialized:
            return None

        try:
            # TODO: Replace with real sensor reading
            # if self.scd4x.data_ready:
            #     return {
            #         "co2": self.scd4x.CO2,
            #         "temperature": self.scd4x.temperature,
            #         "humidity": self.scd4x.relative_humidity
            #     }

            # Mock data for testing
            import random
            return {
                "co2": random.randint(400, 1200),
                "temperature": 22.0 + random.random() * 5,
                "humidity": 40.0 + random.random() * 20
            }
        except Exception as e:
            print(f"❌ Sensor read error: {e}")
            return None


# ==================== DEVICE ====================

class CO2Device:
    """Main device class."""

    def __init__(self):
        self.sensor = CO2Sensor()
        self.display = Display()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        # Configuration (can be updated via MQTT)
        self.config = {
            "report_interval": REPORT_INTERVAL,
            "alerts_enabled": True,
            "co2_threshold": 1000,
            "display_enabled": DISPLAY_ENABLED
        }

        self.running = False
        self.start_time = time.time()

    def _get_ip(self) -> str:
        """Get device IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "unknown"

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Called when connected to MQTT broker."""
        print(f"✅ Connected to MQTT broker")

        # Subscribe to config and commands
        client.subscribe(TOPIC_CONFIG)
        client.subscribe(TOPIC_COMMANDS)
        print(f"📡 Subscribed to: {TOPIC_CONFIG}, {TOPIC_COMMANDS}")

        # Publish online status (Last Will and Testament will set offline)
        client.publish(TOPIC_STATUS, "online", retain=True)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Called when disconnected from MQTT broker."""
        print(f"⚠️ Disconnected from MQTT broker: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Called when a message is received."""
        try:
            payload = json.loads(msg.payload.decode())
            print(f"📩 Received on {msg.topic}: {payload}")

            if msg.topic == TOPIC_CONFIG:
                self._apply_config(payload)
            elif msg.topic == TOPIC_COMMANDS:
                self._execute_command(payload)

        except Exception as e:
            print(f"❌ Error processing message: {e}")

    def _apply_config(self, config: dict):
        """Apply new configuration."""
        if "report_interval" in config:
            self.config["report_interval"] = config["report_interval"]
            print(f"⚙️ Report interval set to {self.config['report_interval']}s")

        if "alerts_enabled" in config:
            self.config["alerts_enabled"] = config["alerts_enabled"]

        if "co2_threshold" in config:
            self.config["co2_threshold"] = config["co2_threshold"]

        if "display_enabled" in config:
            self.config["display_enabled"] = config["display_enabled"]
            global DISPLAY_ENABLED
            DISPLAY_ENABLED = config["display_enabled"]
            print(f"📺 Display {'enabled' if DISPLAY_ENABLED else 'disabled'}")

    def _execute_command(self, command: dict):
        """Execute a command from server."""
        cmd = command.get("command")

        if cmd == "restart":
            print("🔄 Restart requested...")
            self.running = False
            # In real implementation: os.system("sudo reboot")

        elif cmd == "status":
            # Send immediate status
            self._send_telemetry()

    def _send_telemetry(self):
        """Send current sensor data to server and update display."""
        data = self.sensor.read()
        if not data:
            return

        # Update display with current readings
        self.display.show(data["co2"], data["temperature"], data["humidity"])

        # Send to server
        payload = {
            "device_uid": DEVICE_UID,
            "timestamp": int(time.time()),
            "co2": data["co2"],
            "temperature": data["temperature"],
            "humidity": data["humidity"],
            "ip": self._get_ip(),
            "firmware_version": "1.2.0",
            "uptime": int(time.time() - self.start_time)
        }

        self.client.publish(TOPIC_TELEMETRY, json.dumps(payload))
        print(f"📤 Sent: CO2={data['co2']}ppm, T={data['temperature']:.1f}°C, H={data['humidity']:.0f}%")

    def run(self):
        """Main run loop."""
        print("🚀 CO2 Monitor Device Starting...")
        print(f"📱 Device UID: {DEVICE_UID}")
        print(f"📡 MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
        print(f"📺 Display: {'enabled' if DISPLAY_ENABLED else 'disabled'}")

        # Initialize display
        self.display.init()
        self.display.show_status("Starting...")

        # Initialize sensor
        if not self.sensor.init():
            print("❌ Failed to initialize sensor")
            self.display.show_status("Sensor ERROR!")
            return

        self.display.show_status("Connecting...")

        # Set Last Will and Testament (offline status when disconnected)
        self.client.will_set(TOPIC_STATUS, "offline", retain=True)

        # Connect to MQTT broker
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
        except Exception as e:
            print(f"❌ Failed to connect to MQTT: {e}")
            return

        self.client.loop_start()
        self.running = True
        last_report = 0

        try:
            while self.running:
                current_time = time.time()

                # Send telemetry at configured interval
                if current_time - last_report >= self.config["report_interval"]:
                    self._send_telemetry()
                    last_report = current_time

                time.sleep(1)

        except KeyboardInterrupt:
            print("\n⏹️ Stopping...")
        finally:
            self.client.publish(TOPIC_STATUS, "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            print("👋 Goodbye!")


if __name__ == "__main__":
    device = CO2Device()
    device.run()

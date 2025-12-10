"""
CO2 Monitor - MQTT Message Processor
Receives telemetry from devices and saves to database
"""

import asyncio
import json
import random
import signal
import string
from datetime import datetime

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry


def generate_activation_code() -> str:
    """Generate random 8-character activation code."""
    chars = string.ascii_uppercase + string.digits
    # Remove ambiguous characters: O, 0, I, 1, L
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("1", "").replace("L", "")
    return "".join(random.choices(chars, k=8))


# Global reference to MQTT client for config push
_mqtt_client: mqtt.Client | None = None


def get_mqtt_client() -> mqtt.Client | None:
    """Get the global MQTT client instance."""
    return _mqtt_client


def publish_device_config(device_uid: str, config: dict) -> bool:
    """
    Publish configuration to a device.
    Creates a temporary MQTT connection if no global client is available.

    Args:
        device_uid: Device unique identifier
        config: Configuration dict (e.g., {"send_interval": 60})

    Returns:
        True if published successfully
    """
    import time

    topic = f"devices/{device_uid}/config"
    payload = json.dumps(config)

    # Try global client first (for mqtt processor)
    client = get_mqtt_client()
    if client and client.is_connected():
        result = client.publish(topic, payload, qos=1, retain=True)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Config pushed to {device_uid}: {config}")
            return True
        else:
            print(f"❌ Failed to push config to {device_uid}: {result.rc}")
            return False

    # Create temporary connection (for bot/api which run in separate containers)
    try:
        temp_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        temp_client.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=10)
        temp_client.loop_start()

        # Wait for connection (max 1 second)
        for _ in range(10):
            if temp_client.is_connected():
                break
            time.sleep(0.1)

        if not temp_client.is_connected():
            print(f"⚠️ Could not connect to MQTT broker")
            temp_client.loop_stop()
            return False

        result = temp_client.publish(topic, payload, qos=1, retain=True)
        result.wait_for_publish(timeout=5)

        temp_client.loop_stop()
        temp_client.disconnect()

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Config pushed to {device_uid}: {config} (via temp connection)")
            return True
        else:
            print(f"❌ Failed to push config to {device_uid}: {result.rc}")
            return False

    except Exception as e:
        print(f"❌ MQTT error pushing config to {device_uid}: {e}")
        return False


def publish_device_command(device_uid: str, command: str) -> bool:
    """
    Publish command to a device.
    Creates a temporary MQTT connection if no global client is available.

    Args:
        device_uid: Device unique identifier
        command: Command name (e.g., "force_update", "restart", "status")

    Returns:
        True if published successfully
    """
    import time

    topic = f"devices/{device_uid}/commands"
    payload = json.dumps({"command": command})

    # Try global client first (for mqtt processor)
    client = get_mqtt_client()
    if client and client.is_connected():
        result = client.publish(topic, payload, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Command sent to {device_uid}: {command}")
            return True
        else:
            print(f"❌ Failed to send command to {device_uid}: {result.rc}")
            return False

    # Create temporary connection (for bot/api which run in separate containers)
    try:
        temp_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        temp_client.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=10)
        temp_client.loop_start()

        # Wait for connection (max 1 second)
        for _ in range(10):
            if temp_client.is_connected():
                break
            time.sleep(0.1)

        if not temp_client.is_connected():
            print(f"⚠️ Could not connect to MQTT broker")
            temp_client.loop_stop()
            return False

        result = temp_client.publish(topic, payload, qos=1)
        result.wait_for_publish(timeout=5)

        temp_client.loop_stop()
        temp_client.disconnect()

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"📤 Command sent to {device_uid}: {command} (via temp connection)")
            return True
        else:
            print(f"❌ Failed to send command to {device_uid}: {result.rc}")
            return False

    except Exception as e:
        print(f"❌ MQTT error sending command to {device_uid}: {e}")
        return False


class MQTTProcessor:
    """Processes MQTT messages from CO2 devices."""

    def __init__(self):
        global _mqtt_client
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect
        self.running = False
        self._loop = None
        _mqtt_client = self.client

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Called when connected to MQTT broker."""
        print(f"✅ Connected to MQTT broker: {settings.mqtt_broker}:{settings.mqtt_port}")

        # Subscribe to all device telemetry
        client.subscribe("devices/+/telemetry")
        print("📡 Subscribed to: devices/+/telemetry")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Called when disconnected from MQTT broker."""
        print(f"⚠️ Disconnected from MQTT broker: {reason_code}")

    def _on_message(self, client, userdata, msg):
        """Called when a message is received."""
        try:
            # Parse topic: devices/{device_uid}/telemetry
            parts = msg.topic.split("/")
            if len(parts) != 3:
                return

            device_uid = parts[1]
            payload = json.loads(msg.payload.decode())

            print(f"📩 Received from {device_uid}: CO2={payload.get('co2')}ppm")

            # Schedule async processing
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._process_telemetry(device_uid, payload),
                    self._loop
                )

        except Exception as e:
            print(f"❌ Error processing message: {e}")

    async def _process_telemetry(self, device_uid: str, payload: dict):
        """Process and save telemetry data."""
        async with async_session_maker() as session:
            try:
                # Get or create device
                device = await self._get_or_create_device(session, device_uid, payload)

                # Save telemetry
                telemetry = Telemetry(
                    device_id=device.id,
                    co2=payload.get("co2", 0),
                    temperature=payload.get("temperature", 0),
                    humidity=payload.get("humidity", 0),
                    timestamp=datetime.utcnow()
                )
                session.add(telemetry)

                # Update device status
                device.is_online = True
                device.last_seen = datetime.utcnow()
                device.last_ip = payload.get("ip")
                device.firmware_version = payload.get("firmware_version")

                await session.commit()
                print(f"💾 Saved telemetry for {device_uid}")

            except Exception as e:
                await session.rollback()
                print(f"❌ Database error: {e}")

    async def _get_or_create_device(
        self, session: AsyncSession, device_uid: str, payload: dict
    ) -> Device:
        """Get existing device or create new one."""
        result = await session.execute(
            select(Device).where(Device.device_uid == device_uid)
        )
        device = result.scalar_one_or_none()

        if not device:
            # Generate unique activation code
            activation_code = generate_activation_code()

            # Ensure code is unique
            for _ in range(10):  # Max 10 attempts
                existing = await session.execute(
                    select(Device).where(Device.activation_code == activation_code)
                )
                if not existing.scalar_one_or_none():
                    break
                activation_code = generate_activation_code()

            device = Device(
                device_uid=device_uid,
                name=payload.get("name"),
                firmware_version=payload.get("firmware_version"),
                last_ip=payload.get("ip"),
                activation_code=activation_code,
            )
            session.add(device)
            await session.flush()
            print(f"🆕 Created new device: {device_uid} (code: {activation_code})")

        return device

    async def run(self):
        """Main run loop."""
        self._loop = asyncio.get_event_loop()
        self.running = True

        print("🚀 Starting MQTT Processor...")
        print(f"📡 Connecting to {settings.mqtt_broker}:{settings.mqtt_port}")

        # Connect to MQTT broker
        self.client.connect(settings.mqtt_broker, settings.mqtt_port, 60)

        # Start MQTT loop in background thread
        self.client.loop_start()

        # Keep running until stopped
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("⏹️ MQTT Processor stopped")

    def stop(self):
        """Stop the processor."""
        self.running = False


async def main():
    """Entry point."""
    processor = MQTTProcessor()

    # Handle shutdown signals
    def signal_handler(sig, frame):
        print("\n⏹️ Shutting down...")
        processor.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await processor.run()


if __name__ == "__main__":
    asyncio.run(main())

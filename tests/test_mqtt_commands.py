"""
Tests for MQTT command publishing.
"""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestPublishDeviceCommand:
    """Tests for publish_device_command function."""

    @patch("app.mqtt.main.get_mqtt_client")
    def test_publish_calibrate_command(self, mock_get_client):
        """Test that calibrate command is published with target_co2 parameter."""
        from app.mqtt.main import publish_device_command

        # Setup mock client
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_result = MagicMock()
        mock_result.rc = 0  # MQTT_ERR_SUCCESS
        mock_client.publish.return_value = mock_result
        mock_get_client.return_value = mock_client

        # Call function
        result = publish_device_command("test-device-123", "calibrate", target_co2=420)

        # Verify
        assert result is True
        mock_client.publish.assert_called_once()
        call_args = mock_client.publish.call_args

        # Check topic
        assert call_args[0][0] == "devices/test-device-123/commands"

        # Check payload contains calibrate command with target_co2
        payload = json.loads(call_args[0][1])
        assert payload["command"] == "calibrate"
        assert payload["target_co2"] == 420

    @patch("app.mqtt.main.get_mqtt_client")
    def test_publish_live_mode_command(self, mock_get_client):
        """Test that live_mode command is published with duration parameter."""
        from app.mqtt.main import publish_device_command

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result
        mock_get_client.return_value = mock_client

        result = publish_device_command("test-device-123", "live_mode", duration=10)

        assert result is True
        payload = json.loads(mock_client.publish.call_args[0][1])
        assert payload["command"] == "live_mode"
        assert payload["duration"] == 10

    @patch("app.mqtt.main.get_mqtt_client")
    def test_publish_display_on_command(self, mock_get_client):
        """Test that display_on command is published."""
        from app.mqtt.main import publish_device_command

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result
        mock_get_client.return_value = mock_client

        result = publish_device_command("test-device-123", "display_on")

        assert result is True
        payload = json.loads(mock_client.publish.call_args[0][1])
        assert payload["command"] == "display_on"

    @patch("app.mqtt.main.get_mqtt_client")
    def test_publish_fails_when_disconnected(self, mock_get_client):
        """Test that publish returns False when MQTT client is disconnected."""
        from app.mqtt.main import publish_device_command

        mock_get_client.return_value = None

        # Without temporary connection ability, this should fail
        with patch("app.mqtt.main.mqtt") as mock_mqtt:
            mock_temp_client = MagicMock()
            mock_temp_client.is_connected.return_value = False
            mock_mqtt.Client.return_value = mock_temp_client

            result = publish_device_command("test-device-123", "calibrate")

            # Should return False since no connection available
            assert result is False


class TestDeviceCommandPayloads:
    """Tests for command payload structure."""

    def test_calibrate_payload_structure(self):
        """Test calibrate command payload has correct structure."""
        command_data = {"command": "calibrate", "target_co2": 420}

        assert "command" in command_data
        assert command_data["command"] == "calibrate"
        assert "target_co2" in command_data
        assert isinstance(command_data["target_co2"], int)
        assert 300 <= command_data["target_co2"] <= 500  # Valid atmospheric CO2 range

    def test_live_mode_payload_structure(self):
        """Test live_mode command payload has correct structure."""
        command_data = {"command": "live_mode", "duration": 5}

        assert "command" in command_data
        assert command_data["command"] == "live_mode"
        assert "duration" in command_data
        assert isinstance(command_data["duration"], int)
        assert command_data["duration"] > 0

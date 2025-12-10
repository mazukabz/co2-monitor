"""
Pytest configuration and fixtures for CO2 Monitor tests.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def mock_mqtt_client():
    """Create a mock MQTT client for testing."""
    from unittest.mock import MagicMock

    client = MagicMock()
    client.is_connected.return_value = True

    result = MagicMock()
    result.rc = 0  # MQTT_ERR_SUCCESS
    client.publish.return_value = result

    return client


@pytest.fixture
def sample_telemetry_data():
    """Sample telemetry data for testing."""
    return {
        "device_uid": "test-device-123",
        "co2": 750,
        "temperature": 22.5,
        "humidity": 45.0,
        "timestamp": "2025-12-11T12:00:00",
    }


@pytest.fixture
def sample_calibrate_command():
    """Sample calibrate command for testing."""
    return {
        "command": "calibrate",
        "target_co2": 420,
    }


@pytest.fixture
def sample_live_mode_command():
    """Sample live_mode command for testing."""
    return {
        "command": "live_mode",
        "duration": 10,
    }

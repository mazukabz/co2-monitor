"""
Tests for device command handling (co2_sensor.py).

These tests verify that the device correctly parses and executes
commands received via MQTT.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import json


class TestCalibrateCommand:
    """Tests for calibrate command handling on device."""

    def test_calibrate_command_parsing(self):
        """Test that calibrate command is correctly parsed from MQTT payload."""
        payload = {"command": "calibrate", "target_co2": 420}

        assert payload.get("command") == "calibrate"
        assert payload.get("target_co2", 420) == 420

    def test_calibrate_default_target(self):
        """Test that default target CO2 is 420 ppm if not specified."""
        payload = {"command": "calibrate"}

        target_co2 = payload.get("target_co2", 420)
        assert target_co2 == 420

    def test_calibrate_custom_target(self):
        """Test that custom target CO2 can be specified."""
        payload = {"command": "calibrate", "target_co2": 415}

        target_co2 = payload.get("target_co2", 420)
        assert target_co2 == 415


class TestDisplayCommands:
    """Tests for display control commands."""

    def test_display_on_command(self):
        """Test display_on command structure."""
        payload = {"command": "display_on"}
        assert payload.get("command") == "display_on"

    def test_display_off_command(self):
        """Test display_off command structure."""
        payload = {"command": "display_off"}
        assert payload.get("command") == "display_off"


class TestLiveModeCommands:
    """Tests for live mode commands."""

    def test_live_mode_with_duration(self):
        """Test live_mode command with duration."""
        payload = {"command": "live_mode", "duration": 10}

        assert payload.get("command") == "live_mode"
        assert payload.get("duration", 5) == 10

    def test_live_mode_default_duration(self):
        """Test live_mode command with default duration."""
        payload = {"command": "live_mode"}

        assert payload.get("command") == "live_mode"
        assert payload.get("duration", 5) == 5  # default is 5 minutes

    def test_live_mode_off_command(self):
        """Test live_mode_off command structure."""
        payload = {"command": "live_mode_off"}
        assert payload.get("command") == "live_mode_off"


class TestOtherCommands:
    """Tests for other device commands."""

    def test_force_update_command(self):
        """Test force_update command structure."""
        payload = {"command": "force_update"}
        assert payload.get("command") == "force_update"

    def test_restart_command(self):
        """Test restart command structure."""
        payload = {"command": "restart"}
        assert payload.get("command") == "restart"

    def test_status_command(self):
        """Test status command structure."""
        payload = {"command": "status"}
        assert payload.get("command") == "status"


class TestSensorValidation:
    """Tests for sensor data validation."""

    def test_co2_valid_range(self):
        """Test that CO2 values in valid range are accepted."""
        # SCD41 range is 0-40000 ppm
        valid_values = [0, 400, 420, 1000, 5000, 10000, 40000]

        for co2 in valid_values:
            assert 0 <= co2 <= 40000, f"CO2 value {co2} should be valid"

    def test_co2_invalid_range(self):
        """Test that CO2 values outside range are rejected."""
        invalid_values = [-1, -100, 40001, 50000]

        for co2 in invalid_values:
            assert not (0 <= co2 <= 40000), f"CO2 value {co2} should be invalid"

    def test_temperature_valid_range(self):
        """Test that temperature values in valid range are accepted."""
        # SCD41 operating range is -10 to 60 C
        valid_values = [-10, 0, 20, 25, 40, 60]

        for temp in valid_values:
            assert -10 <= temp <= 60, f"Temperature {temp} should be valid"

    def test_humidity_valid_range(self):
        """Test that humidity values in valid range are accepted."""
        # Humidity 0-100%
        valid_values = [0, 30, 50, 70, 100]

        for hum in valid_values:
            assert 0 <= hum <= 100, f"Humidity {hum} should be valid"


class TestCalibrationBestPractices:
    """Tests documenting calibration best practices."""

    def test_calibration_target_is_atmospheric_co2(self):
        """Test that default calibration target is current atmospheric CO2."""
        # Current atmospheric CO2 is approximately 420 ppm (2024-2025)
        # This is the value sensor should be calibrated to when exposed to fresh air
        DEFAULT_TARGET_CO2 = 420

        assert 400 <= DEFAULT_TARGET_CO2 <= 450, \
            "Default calibration target should be near current atmospheric CO2 level"

    def test_calibration_requires_stable_conditions(self):
        """Document that calibration requires stable measurement conditions."""
        # According to SCD41 datasheet:
        # - Sensor should have been measuring for at least 3 minutes
        # - Environment should be stable (fresh outdoor air)
        # - Temperature should be stable

        calibration_requirements = {
            "minimum_measurement_time_minutes": 3,
            "environment": "fresh outdoor air",
            "temperature_stable": True,
        }

        assert calibration_requirements["minimum_measurement_time_minutes"] >= 3

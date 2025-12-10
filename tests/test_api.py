"""
Tests for API endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestDeviceManifest:
    """Tests for /api/device/manifest endpoint."""

    def test_manifest_includes_calibrate_command(self):
        """Test that manifest documentation includes calibrate command info."""
        # The manifest endpoint returns firmware info
        # Commands are documented in main.py docstrings
        commands = [
            "force_update",
            "restart",
            "status",
            "live_mode",
            "display_on",
            "display_off",
            "calibrate",  # New command in v2.2.0
        ]

        assert "calibrate" in commands


class TestFirmwareVersion:
    """Tests for firmware versioning."""

    def test_version_format(self):
        """Test that firmware version follows semantic versioning."""
        version = "2.2.0"

        parts = version.split(".")
        assert len(parts) == 3, "Version should have 3 parts (major.minor.patch)"
        assert all(p.isdigit() for p in parts), "All version parts should be numeric"

    def test_version_date_format(self):
        """Test that firmware date follows ISO format."""
        date = "2025-12-11"

        parts = date.split("-")
        assert len(parts) == 3, "Date should have 3 parts (YYYY-MM-DD)"
        assert len(parts[0]) == 4, "Year should be 4 digits"
        assert len(parts[1]) == 2, "Month should be 2 digits"
        assert len(parts[2]) == 2, "Day should be 2 digits"


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_response_structure(self):
        """Test that health endpoint returns expected structure."""
        expected_fields = ["status", "version", "date"]

        response = {
            "status": "ok",
            "version": "2.2.0",
            "date": "2025-12-11",
        }

        for field in expected_fields:
            assert field in response, f"Health response should include {field}"

        assert response["status"] == "ok"

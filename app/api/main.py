"""
CO2 Monitor - API Server

Provides endpoints for:
- Device installation package (tar.gz with all files)
- Device OTA updates (firmware download with versioning)
- Device configuration
- Future: Web dashboard
"""

import hashlib
import io
import json
import os
import tarfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.core.config import settings

# ==================== FIRMWARE VERSIONING ====================
# Update these values when releasing new device firmware
# Device will compare dates and update if server version is newer

FIRMWARE_VERSION = "1.0.1"
FIRMWARE_DATE = "2025-12-08"  # YYYY-MM-DD format
FIRMWARE_CHANGELOG = "Fix: use venv for systemd service"

# Path to device scripts (mounted in Docker at /app/device)
DEVICE_DIR = Path("/app/device")
if not DEVICE_DIR.exists():
    # Fallback for local development
    DEVICE_DIR = Path(__file__).parent.parent.parent / "device"

# Server public address for device config
SERVER_HOST = os.getenv("MQTT_PUBLIC_HOST", "31.59.170.64")
MQTT_PORT = int(os.getenv("MQTT_PORT", "10883"))


def get_file_hash(filepath: Path) -> str:
    """Calculate MD5 hash of a file."""
    if not filepath.exists():
        return ""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ==================== APP ====================

app = FastAPI(
    title="CO2 Monitor API",
    description="API for CO2 monitoring devices",
    version=FIRMWARE_VERSION,
)


# ==================== DEVICE INSTALLATION ====================

@app.get("/install.py")
async def get_installer_script():
    """
    Return the minimal installer script.
    Device runs: curl -sL http://server/install.py | python3
    """
    script = f'''#!/usr/bin/env python3
"""CO2 Monitor - Device Installer. Run: curl -sL http://{SERVER_HOST}:10900/install.py | python3"""
import os, sys, tarfile, tempfile
from urllib.request import urlopen

SERVER = "http://{SERVER_HOST}:10900"
INSTALL_DIR = os.path.expanduser("~/co2-monitor")

print("=" * 50)
print("CO2 Monitor - Installing...")
print("=" * 50)

try:
    data = urlopen(f"{{SERVER}}/api/device/package", timeout=60).read()
except Exception as e:
    print(f"Error: {{e}}")
    sys.exit(1)

os.makedirs(INSTALL_DIR, exist_ok=True)

with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
    f.write(data)
    tmp = f.name

try:
    with tarfile.open(tmp, "r:gz") as tar:
        tar.extractall(INSTALL_DIR)
finally:
    os.unlink(tmp)

print(f"Installed to " + INSTALL_DIR)
print(f"\\nTo run: cd " + INSTALL_DIR + " && python3 main.py")
print(f"To install service: cd " + INSTALL_DIR + " && sudo bash install_service.sh")
'''
    return Response(content=script, media_type="text/x-python")


@app.get("/api/device/package")
async def get_device_package():
    """
    Return tar.gz package with all device files.
    Includes: main.py, config.json, requirements.txt, install_service.sh
    """
    # Create tar.gz in memory
    buffer = io.BytesIO()

    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        # 1. Main script (co2_sensor.py -> main.py)
        script_path = DEVICE_DIR / "co2_sensor.py"
        if script_path.exists():
            tar.add(script_path, arcname="main.py")

        # 2. Config file
        config = {
            "mqtt_broker": SERVER_HOST,
            "mqtt_port": MQTT_PORT,
            "send_interval": 60,
            "firmware_version": FIRMWARE_VERSION,
            "firmware_date": FIRMWARE_DATE,
        }
        config_data = json.dumps(config, indent=2).encode()
        config_info = tarfile.TarInfo(name="config.json")
        config_info.size = len(config_data)
        tar.addfile(config_info, io.BytesIO(config_data))

        # 3. Version file
        version = {
            "version": FIRMWARE_VERSION,
            "date": FIRMWARE_DATE,
            "installed_at": datetime.utcnow().isoformat(),
        }
        version_data = json.dumps(version, indent=2).encode()
        version_info = tarfile.TarInfo(name="version.json")
        version_info.size = len(version_data)
        tar.addfile(version_info, io.BytesIO(version_data))

        # 4. Requirements
        requirements = b"paho-mqtt>=2.0.0\\n"
        req_info = tarfile.TarInfo(name="requirements.txt")
        req_info.size = len(requirements)
        tar.addfile(req_info, io.BytesIO(requirements))

        # 5. Update script
        update_script = f'''#!/usr/bin/env python3
"""Check for updates and download if available."""
import json, os, sys
from urllib.request import urlopen
from datetime import datetime

SERVER = "http://{SERVER_HOST}:10900"
INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

# Load local version
try:
    with open(os.path.join(INSTALL_DIR, "version.json")) as f:
        local = json.load(f)
except:
    local = {{"date": "1970-01-01"}}

# Check server version
try:
    manifest = json.loads(urlopen(f"{{SERVER}}/api/device/manifest", timeout=30).read())
except Exception as e:
    print(f"Cannot check updates: {{e}}")
    sys.exit(1)

local_date = datetime.strptime(local.get("date", "1970-01-01"), "%Y-%m-%d")
server_date = datetime.strptime(manifest.get("date", "1970-01-01"), "%Y-%m-%d")

if server_date > local_date:
    print(f"Update available: {{manifest.get('version')}} ({{manifest.get('date')}})")
    print("Run: curl -sL http://{SERVER_HOST}:10900/install.py | python3")
else:
    print(f"Up to date: {{local.get('version')}} ({{local.get('date')}})")
'''.encode()
        update_info = tarfile.TarInfo(name="update.py")
        update_info.size = len(update_script)
        update_info.mode = 0o755
        tar.addfile(update_info, io.BytesIO(update_script))

        # 6. Systemd service installer
        service_script = f'''#!/bin/bash
# Install CO2 Monitor as systemd service

SERVICE_NAME="co2-monitor"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$INSTALL_DIR/venv"

# Get the user who ran sudo (or current user if not sudo)
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
else
    SERVICE_USER="$(whoami)"
fi

echo "Installing CO2 Monitor service..."
echo "Install dir: $INSTALL_DIR"
echo "Venv dir: $VENV_DIR"
echo "Service user: $SERVICE_USER"

# Create virtual environment if not exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"
fi

# Install dependencies in venv
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$INSTALL_DIR/requirements.txt"

# Create service file
cat > /tmp/$SERVICE_NAME.service << EOF
[Unit]
Description=CO2 Monitor Device
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="CO2_CONFIG_FILE=$INSTALL_DIR/config.json"
Environment="DEMO_MODE=true"
ExecStart=$VENV_DIR/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

mv /tmp/$SERVICE_NAME.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo ""
echo "Service installed and started!"
echo "Check status: sudo systemctl status $SERVICE_NAME"
echo "View logs: journalctl -u $SERVICE_NAME -f"
'''.encode()
        service_info = tarfile.TarInfo(name="install_service.sh")
        service_info.size = len(service_script)
        service_info.mode = 0o755
        tar.addfile(service_info, io.BytesIO(service_script))

        # 7. README
        readme = f'''# CO2 Monitor Device

## Quick Start
python3 main.py

## Install as Service
sudo bash install_service.sh

## Check for Updates
python3 update.py

## Configuration
Edit config.json or set environment variables:
- MQTT_BROKER: {SERVER_HOST}
- MQTT_PORT: {MQTT_PORT}
- DEMO_MODE: true/false

## Version
{FIRMWARE_VERSION} ({FIRMWARE_DATE})
'''.encode()
        readme_info = tarfile.TarInfo(name="README.md")
        readme_info.size = len(readme)
        tar.addfile(readme_info, io.BytesIO(readme))

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f"attachment; filename=co2-monitor-{FIRMWARE_VERSION}.tar.gz",
            "X-Firmware-Version": FIRMWARE_VERSION,
            "X-Firmware-Date": FIRMWARE_DATE,
        }
    )


# ==================== DEVICE OTA ENDPOINTS ====================

@app.get("/api/device/manifest")
async def get_device_manifest(device_uid: str = Query(None)):
    """
    Get device firmware manifest with version info.
    Device calls this to check for updates.
    """
    script_path = DEVICE_DIR / "co2_sensor.py"

    return {
        "version": FIRMWARE_VERSION,
        "date": FIRMWARE_DATE,
        "hash": get_file_hash(script_path),
        "changelog": FIRMWARE_CHANGELOG,
        "package_url": "/api/device/package",
        "server_time": datetime.utcnow().isoformat(),
    }


@app.get("/api/device/script")
async def get_device_script():
    """Download main device script."""
    script_path = DEVICE_DIR / "co2_sensor.py"

    if not script_path.exists():
        return JSONResponse({"error": "Script not found"}, status_code=404)

    return FileResponse(
        script_path,
        media_type="text/x-python",
        filename="co2_sensor.py",
        headers={
            "X-Firmware-Version": FIRMWARE_VERSION,
            "X-Firmware-Date": FIRMWARE_DATE,
        }
    )


@app.get("/api/device/config")
async def get_device_config(device_uid: str = Query(None)):
    """Get device configuration."""
    return {
        "mqtt_broker": SERVER_HOST,
        "mqtt_port": MQTT_PORT,
        "send_interval": 60,
        "device_uid": device_uid,
        "device_name": "",
        "config_version": FIRMWARE_DATE,
    }


# ==================== HEALTH CHECK ====================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": FIRMWARE_VERSION,
        "date": FIRMWARE_DATE,
    }


@app.get("/")
async def root():
    """Root endpoint with installation instructions."""
    return {
        "service": "CO2 Monitor API",
        "version": FIRMWARE_VERSION,
        "date": FIRMWARE_DATE,
        "install": f"curl -sL http://{SERVER_HOST}:10900/install.py | python3",
        "endpoints": {
            "install_script": "/install.py",
            "package": "/api/device/package",
            "manifest": "/api/device/manifest",
            "health": "/health",
        }
    }


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

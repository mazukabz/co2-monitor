#!/usr/bin/env python3
"""
CO2 Monitor - Bootstrap Loader (IMMUTABLE)

This file should NEVER be updated OTA - it's the recovery mechanism.
It runs on device startup and:
1. Checks server for updates
2. Downloads new code if available
3. Validates the download (hash check)
4. Runs health check after update
5. Rolls back to last working version if health check fails

Usage:
    python3 bootstrap.py

Install as service:
    sudo cp co2-monitor.service /etc/systemd/system/
    sudo systemctl enable co2-monitor
    sudo systemctl start co2-monitor
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

# ==================== CONFIGURATION ====================

SERVER_URL = "http://31.59.170.64:10900"
INSTALL_DIR = Path.home() / "co2-monitor"
BACKUP_DIR = INSTALL_DIR / "backup"
LOG_FILE = INSTALL_DIR / "bootstrap.log"

# Files managed by OTA
MAIN_SCRIPT = "main.py"
CONFIG_FILE = "config.json"
VERSION_FILE = "version.json"

# Health check settings
HEALTH_CHECK_TIMEOUT = 30  # seconds to wait for main.py to prove it's healthy
HEALTH_CHECK_FILE = INSTALL_DIR / ".health_ok"

# Retry settings
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY = 5  # seconds


# ==================== LOGGING ====================

def log(message: str, level: str = "INFO"):
    """Log message to file and console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)

    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ==================== VERSION MANAGEMENT ====================

def get_local_version() -> dict:
    """Get locally installed version info."""
    version_path = INSTALL_DIR / VERSION_FILE
    if version_path.exists():
        try:
            with open(version_path) as f:
                return json.load(f)
        except Exception as e:
            log(f"Error reading local version: {e}", "WARN")
    return {"version": "0.0.0", "date": "1970-01-01", "hash": ""}


def get_server_manifest() -> dict | None:
    """Fetch version manifest from server."""
    try:
        url = f"{SERVER_URL}/api/device/manifest"
        response = urlopen(url, timeout=30)
        return json.loads(response.read().decode())
    except URLError as e:
        log(f"Cannot reach server: {e}", "ERROR")
        return None
    except Exception as e:
        log(f"Error fetching manifest: {e}", "ERROR")
        return None


def needs_update(local: dict, server: dict) -> bool:
    """Check if update is needed based on version/date/hash."""
    # Compare by hash first (most reliable)
    if local.get("hash") and server.get("hash"):
        if local["hash"] != server["hash"]:
            log(f"Hash mismatch: local={local['hash'][:8]}... server={server['hash'][:8]}...")
            return True

    # Compare by date
    try:
        local_date = datetime.strptime(local.get("date", "1970-01-01"), "%Y-%m-%d")
        server_date = datetime.strptime(server.get("date", "1970-01-01"), "%Y-%m-%d")
        if server_date > local_date:
            log(f"Server has newer version: {server.get('version')} ({server.get('date')})")
            return True
    except Exception:
        pass

    return False


# ==================== BACKUP & ROLLBACK ====================

def create_backup():
    """Backup current working version."""
    if not (INSTALL_DIR / MAIN_SCRIPT).exists():
        return

    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Copy current files to backup
        for filename in [MAIN_SCRIPT, CONFIG_FILE, VERSION_FILE]:
            src = INSTALL_DIR / filename
            dst = BACKUP_DIR / filename
            if src.exists():
                shutil.copy2(src, dst)

        log("Backup created successfully")
    except Exception as e:
        log(f"Backup failed: {e}", "WARN")


def rollback():
    """Restore from backup."""
    if not BACKUP_DIR.exists():
        log("No backup available for rollback", "ERROR")
        return False

    try:
        for filename in [MAIN_SCRIPT, CONFIG_FILE, VERSION_FILE]:
            src = BACKUP_DIR / filename
            dst = INSTALL_DIR / filename
            if src.exists():
                shutil.copy2(src, dst)

        log("Rollback completed successfully")
        return True
    except Exception as e:
        log(f"Rollback failed: {e}", "ERROR")
        return False


# ==================== DOWNLOAD & UPDATE ====================

def download_file(url: str, dest: Path) -> bool:
    """Download file from URL with retries."""
    for attempt in range(MAX_DOWNLOAD_RETRIES):
        try:
            log(f"Downloading {url} (attempt {attempt + 1}/{MAX_DOWNLOAD_RETRIES})")
            response = urlopen(url, timeout=60)
            content = response.read()

            # Write to temp file first, then move (atomic)
            temp_path = dest.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                f.write(content)

            temp_path.rename(dest)
            log(f"Downloaded {len(content)} bytes to {dest.name}")
            return True

        except Exception as e:
            log(f"Download failed: {e}", "WARN")
            if attempt < MAX_DOWNLOAD_RETRIES - 1:
                time.sleep(RETRY_DELAY)

    return False


def verify_hash(filepath: Path, expected_hash: str) -> bool:
    """Verify file hash."""
    if not expected_hash:
        return True  # Skip if no hash provided

    try:
        with open(filepath, "rb") as f:
            actual_hash = hashlib.md5(f.read()).hexdigest()

        if actual_hash == expected_hash:
            log(f"Hash verified: {actual_hash[:8]}...")
            return True
        else:
            log(f"Hash mismatch! Expected {expected_hash[:8]}..., got {actual_hash[:8]}...", "ERROR")
            return False
    except Exception as e:
        log(f"Hash verification failed: {e}", "ERROR")
        return False


def download_update(manifest: dict) -> bool:
    """Download and verify update package."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Download main script
    script_url = f"{SERVER_URL}/api/device/script"
    script_path = INSTALL_DIR / MAIN_SCRIPT

    if not download_file(script_url, script_path):
        return False

    # Verify hash
    if not verify_hash(script_path, manifest.get("hash", "")):
        script_path.unlink(missing_ok=True)
        return False

    # Download config
    config_url = f"{SERVER_URL}/api/device/config"
    config_path = INSTALL_DIR / CONFIG_FILE
    download_file(config_url, config_path)  # Config is optional

    # Save version info
    version_info = {
        "version": manifest.get("version", "unknown"),
        "date": manifest.get("date", datetime.now().strftime("%Y-%m-%d")),
        "hash": manifest.get("hash", ""),
        "updated_at": datetime.utcnow().isoformat(),
        "changelog": manifest.get("changelog", ""),
    }

    with open(INSTALL_DIR / VERSION_FILE, "w") as f:
        json.dump(version_info, f, indent=2)

    log(f"Update downloaded: v{version_info['version']}")
    return True


# ==================== HEALTH CHECK ====================

def run_health_check() -> bool:
    """
    Run main.py and check if it's healthy.
    Main.py should create HEALTH_CHECK_FILE within HEALTH_CHECK_TIMEOUT seconds.
    """
    script_path = INSTALL_DIR / MAIN_SCRIPT

    if not script_path.exists():
        log("Main script not found", "ERROR")
        return False

    # Remove old health file
    HEALTH_CHECK_FILE.unlink(missing_ok=True)

    log("Starting health check...")

    try:
        # Start main.py in subprocess
        process = subprocess.Popen(
            [sys.executable, str(script_path), "--health-check"],
            cwd=str(INSTALL_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for health file to appear
        start_time = time.time()
        while time.time() - start_time < HEALTH_CHECK_TIMEOUT:
            if HEALTH_CHECK_FILE.exists():
                log("Health check PASSED")
                process.terminate()
                return True

            # Check if process crashed
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                log(f"Process exited with code {process.returncode}", "ERROR")
                if stderr:
                    log(f"Stderr: {stderr.decode()[:500]}", "ERROR")
                return False

            time.sleep(1)

        # Timeout
        log("Health check TIMEOUT", "ERROR")
        process.terminate()
        return False

    except Exception as e:
        log(f"Health check error: {e}", "ERROR")
        return False


# ==================== MAIN EXECUTION ====================

def install_dependencies():
    """Install Python dependencies if requirements.txt exists."""
    req_file = INSTALL_DIR / "requirements.txt"
    if not req_file.exists():
        # Create minimal requirements
        with open(req_file, "w") as f:
            f.write("paho-mqtt>=2.0.0\nadafruit-circuitpython-scd4x\nadafruit-circuitpython-ssd1306\n")

    try:
        log("Installing dependencies...")
        # Use pip from venv if available, otherwise system pip with --break-system-packages
        venv_pip = INSTALL_DIR / "venv" / "bin" / "pip"
        if venv_pip.exists():
            subprocess.run(
                [str(venv_pip), "install", "-q", "-r", str(req_file)],
                check=True,
                timeout=300,
            )
        else:
            # Fallback: try system pip with --break-system-packages for newer Debian/Ubuntu
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "-r", str(req_file)],
                check=True,
                timeout=300,
            )
        log("Dependencies installed")
    except Exception as e:
        log(f"Failed to install dependencies: {e}", "WARN")


def run_main_script() -> bool:
    """
    Run the main CO2 monitoring script.

    Returns:
        True if force_update was requested (should restart bootstrap)
        False if normal exit (should stop bootstrap)
    """
    script_path = INSTALL_DIR / MAIN_SCRIPT

    if not script_path.exists():
        log("Main script not found, cannot run", "ERROR")
        return False

    log(f"Starting {MAIN_SCRIPT}...")
    os.chdir(INSTALL_DIR)

    # Run as subprocess to catch exit codes (especially 100 for force_update)
    while True:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(INSTALL_DIR),
        )

        if result.returncode == 100:
            # Force update requested - restart bootstrap to check for updates
            log("Force update requested, restarting bootstrap...")
            return True  # Signal to main() to restart update check

        elif result.returncode == 0:
            # Normal exit (e.g., user stopped the service)
            log("Main script exited normally")
            return False  # Signal to main() to stop

        else:
            # Error - wait and restart
            log(f"Main script crashed with code {result.returncode}, restarting in 30s...", "WARN")
            time.sleep(30)


def main():
    """Main bootstrap logic."""
    log("=" * 50)
    log("CO2 Monitor Bootstrap Starting")
    log("=" * 50)

    # Ensure install directory exists
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # Main loop - allows restart after force_update
    while True:
        # Get local version
        local_version = get_local_version()
        log(f"Local version: {local_version.get('version', 'none')} ({local_version.get('date', 'unknown')})")

        # Check server for updates
        log("Checking server for updates...")
        manifest = get_server_manifest()

        if manifest is None:
            log("Cannot reach server, using local version")
        elif needs_update(local_version, manifest):
            log(f"Update available: {manifest.get('version')} ({manifest.get('date')})")
            log(f"Changelog: {manifest.get('changelog', 'N/A')}")

            # Create backup before update
            create_backup()

            # Download update
            if download_update(manifest):
                log("Update downloaded, running health check...")

                # Install dependencies for new version
                install_dependencies()

                # Run health check
                if run_health_check():
                    log("Update successful!")
                else:
                    log("Health check failed, rolling back...", "ERROR")
                    if rollback():
                        log("Rollback successful, using previous version")
                    else:
                        log("Rollback failed! Manual intervention required", "ERROR")
            else:
                log("Download failed, using local version", "ERROR")
        else:
            log("Already up to date")

        # Install dependencies if needed
        install_dependencies()

        # Run main script (blocks until exit or force_update)
        log("Starting main application...")
        should_restart = run_main_script()

        if not should_restart:
            # Normal exit - stop bootstrap
            log("Bootstrap stopping...")
            break

        # Force update was requested - loop will restart and check for updates
        log("Restarting bootstrap cycle...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Interrupted by user")
    except Exception as e:
        log(f"Bootstrap error: {e}", "ERROR")
        sys.exit(1)

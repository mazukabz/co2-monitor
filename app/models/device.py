"""
Device model - represents a physical CO2 monitor device
"""

from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, BigInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Device(Base):
    """Physical device (Raspberry Pi / ESP32)."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_uid: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Activation code for device binding (e.g., "AB12CD34")
    activation_code: Mapped[str | None] = mapped_column(String(8), unique=True, index=True, nullable=True)

    # Device info
    firmware_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # Device settings (can be pushed via MQTT)
    send_interval: Mapped[int] = mapped_column(Integer, default=60)  # seconds

    # Status
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Owner (Telegram user ID)
    owner_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Device {self.device_uid} ({self.name or 'unnamed'})>"

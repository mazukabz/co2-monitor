"""
Telemetry model - sensor readings from devices
"""

from datetime import datetime
from sqlalchemy import Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Telemetry(Base):
    """Sensor readings from device."""

    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), index=True)

    # Sensor data
    co2: Mapped[int] = mapped_column(Integer)  # ppm
    temperature: Mapped[float] = mapped_column(Float)  # Celsius
    humidity: Mapped[float] = mapped_column(Float)  # %

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        index=True
    )

    def __repr__(self) -> str:
        return f"<Telemetry device={self.device_id} co2={self.co2}ppm>"

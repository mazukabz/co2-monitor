"""
User model - represents a Telegram user
"""

from datetime import datetime, time
from sqlalchemy import String, Boolean, DateTime, BigInteger, Time, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """Telegram user who interacts with the bot."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # User's timezone (default Moscow)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")

    # Notification settings
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_threshold: Mapped[int] = mapped_column(Integer, default=1000)  # CO2 ppm

    # Morning report settings (night summary)
    morning_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    morning_report_time: Mapped[time] = mapped_column(Time, default=time(8, 0))

    # Evening report settings (day summary)
    evening_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    evening_report_time: Mapped[time] = mapped_column(Time, default=time(22, 0))

    # Hourly snapshots (every N hours, 0 = disabled)
    snapshot_interval_hours: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow
    )
    last_activity: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    def __repr__(self) -> str:
        return f"<User {self.telegram_id} (@{self.username or 'no_username'})>"

    @property
    def display_name(self) -> str:
        """Get user's display name."""
        if self.first_name:
            if self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.first_name
        return self.username or str(self.telegram_id)

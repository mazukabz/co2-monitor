"""
CO2 Monitor - Configuration
All settings loaded from environment variables (via Infisical)
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str
    postgres_user: str = "co2_user"
    postgres_password: str = ""
    postgres_db: str = "co2_db"

    # Telegram Bot (optional - only required for co2_bot service)
    bot_token: str = ""
    admin_user_ids: str = ""  # Comma-separated list of admin Telegram IDs

    # MQTT
    mqtt_broker: str = "co2_mqtt"
    mqtt_port: int = 1883

    # Timezone
    tz: str = "Europe/Moscow"

    @property
    def admin_ids_list(self) -> list[int]:
        """Parse admin IDs from comma-separated string."""
        if not self.admin_user_ids:
            return []
        return [int(id.strip()) for id in self.admin_user_ids.split(",") if id.strip()]

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in self.admin_ids_list

    class Config:
        env_file = ".env"  # Fallback for local development
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

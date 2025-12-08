"""
Scheduler Service - handles scheduled reports and notifications
Runs as a background task alongside the bot
"""

import asyncio
import logging
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import select, and_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services.charts import generate_morning_report, generate_evening_report

logger = logging.getLogger(__name__)


class ReportScheduler:
    """Scheduler for automated reports."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.running = False
        self._last_morning_check: dict[int, datetime] = {}
        self._last_evening_check: dict[int, datetime] = {}

    async def start(self):
        """Start the scheduler loop."""
        self.running = True
        logger.info("📅 Report scheduler started")

        while self.running:
            try:
                await self._check_and_send_reports()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            # Check every minute
            await asyncio.sleep(60)

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        logger.info("📅 Report scheduler stopped")

    async def _check_and_send_reports(self):
        """Check if any reports need to be sent."""
        async with async_session_maker() as session:
            # Get all users with enabled reports
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

            for user in users:
                try:
                    await self._check_user_reports(session, user)
                except Exception as e:
                    logger.error(f"Error checking reports for user {user.telegram_id}: {e}")

    async def _check_user_reports(self, session, user: User):
        """Check and send reports for a specific user."""
        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")

        now_local = datetime.now(tz)
        current_time = now_local.time()
        today = now_local.date()

        # Check morning report
        if user.morning_report_enabled:
            if self._should_send_report(
                user.telegram_id,
                user.morning_report_time,
                current_time,
                today,
                self._last_morning_check
            ):
                await self._send_morning_report(session, user)
                self._last_morning_check[user.telegram_id] = now_local

        # Check evening report
        if user.evening_report_enabled:
            if self._should_send_report(
                user.telegram_id,
                user.evening_report_time,
                current_time,
                today,
                self._last_evening_check
            ):
                await self._send_evening_report(session, user)
                self._last_evening_check[user.telegram_id] = now_local

    def _should_send_report(
        self,
        user_id: int,
        scheduled_time: time,
        current_time: time,
        today,
        last_check_dict: dict
    ) -> bool:
        """Check if report should be sent now."""
        # Check if we're within the time window (scheduled time to +5 minutes)
        scheduled_minutes = scheduled_time.hour * 60 + scheduled_time.minute
        current_minutes = current_time.hour * 60 + current_time.minute

        if not (scheduled_minutes <= current_minutes < scheduled_minutes + 5):
            return False

        # Check if we already sent today
        last_sent = last_check_dict.get(user_id)
        if last_sent and last_sent.date() == today:
            return False

        return True

    async def _send_morning_report(self, session, user: User):
        """Send morning report to user."""
        logger.info(f"Sending morning report to user {user.telegram_id}")

        # Get user's devices
        if settings.is_admin(user.telegram_id):
            result = await session.execute(select(Device))
        else:
            result = await session.execute(
                select(Device).where(Device.owner_telegram_id == user.telegram_id)
            )

        devices = result.scalars().all()

        if not devices:
            return

        since = datetime.utcnow() - timedelta(hours=24)

        for device in devices:
            telemetry_result = await session.execute(
                select(Telemetry)
                .where(and_(
                    Telemetry.device_id == device.id,
                    Telemetry.timestamp >= since
                ))
                .order_by(Telemetry.timestamp)
            )
            telemetry_list = telemetry_result.scalars().all()

            if not telemetry_list:
                continue

            data = [
                {
                    'timestamp': t.timestamp,
                    'co2': t.co2,
                    'temperature': t.temperature,
                    'humidity': t.humidity
                }
                for t in telemetry_list
            ]

            try:
                chart_buf = generate_morning_report(
                    data,
                    device.name or device.device_uid,
                    user.timezone
                )

                await self.bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=BufferedInputFile(chart_buf.read(), filename="morning_report.png"),
                    caption=f"🌅 Доброе утро! Вот ваш ночной отчёт\n\n"
                            f"📱 {device.name or device.device_uid}"
                )
            except Exception as e:
                logger.error(f"Failed to send morning report to {user.telegram_id}: {e}")

    async def _send_evening_report(self, session, user: User):
        """Send evening report to user."""
        logger.info(f"Sending evening report to user {user.telegram_id}")

        if settings.is_admin(user.telegram_id):
            result = await session.execute(select(Device))
        else:
            result = await session.execute(
                select(Device).where(Device.owner_telegram_id == user.telegram_id)
            )

        devices = result.scalars().all()

        if not devices:
            return

        since = datetime.utcnow() - timedelta(hours=24)

        for device in devices:
            telemetry_result = await session.execute(
                select(Telemetry)
                .where(and_(
                    Telemetry.device_id == device.id,
                    Telemetry.timestamp >= since
                ))
                .order_by(Telemetry.timestamp)
            )
            telemetry_list = telemetry_result.scalars().all()

            if not telemetry_list:
                continue

            data = [
                {
                    'timestamp': t.timestamp,
                    'co2': t.co2,
                    'temperature': t.temperature,
                    'humidity': t.humidity
                }
                for t in telemetry_list
            ]

            try:
                chart_buf = generate_evening_report(
                    data,
                    device.name or device.device_uid,
                    user.timezone
                )

                await self.bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=BufferedInputFile(chart_buf.read(), filename="evening_report.png"),
                    caption=f"🌆 Добрый вечер! Вот итоги дня\n\n"
                            f"📱 {device.name or device.device_uid}"
                )
            except Exception as e:
                logger.error(f"Failed to send evening report to {user.telegram_id}: {e}")


async def run_scheduler(bot: Bot):
    """Run the report scheduler."""
    scheduler = ReportScheduler(bot)
    await scheduler.start()

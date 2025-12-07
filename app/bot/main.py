"""
CO2 Monitor - Telegram Bot
Provides user interface for monitoring CO2 levels
"""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, desc

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router for handlers
router = Router()


# ==================== HELPERS ====================

def get_co2_emoji(co2: int) -> str:
    """Get emoji for CO2 level."""
    if co2 < 800:
        return "🟢"
    elif co2 < 1000:
        return "🟡"
    elif co2 < 1500:
        return "🟠"
    return "🔴"


def get_co2_status(co2: int) -> str:
    """Get status text for CO2 level."""
    if co2 < 800:
        return "Отлично"
    elif co2 < 1000:
        return "Хорошо"
    elif co2 < 1500:
        return "Проветрите"
    return "Критично"


# ==================== HANDLERS ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    user_id = message.from_user.id

    text = (
        f"👋 <b>Добро пожаловать в CO2 Monitor!</b>\n\n"
        f"Ваш ID: <code>{user_id}</code>\n\n"
        f"<b>Команды:</b>\n"
        f"/status - текущие показания\n"
        f"/devices - список устройств\n"
        f"/help - справка\n"
    )

    if settings.is_admin(user_id):
        text += f"\n/admin - админ-панель"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Handle /status command - show latest readings."""
    user_id = message.from_user.id

    async with async_session_maker() as session:
        # Get user's devices or all devices if admin
        if settings.is_admin(user_id):
            result = await session.execute(select(Device))
        else:
            result = await session.execute(
                select(Device).where(Device.owner_telegram_id == user_id)
            )

        devices = result.scalars().all()

        if not devices:
            await message.answer(
                "📭 У вас нет привязанных устройств.\n"
                "Используйте /add для добавления."
            )
            return

        text = "📊 <b>Текущие показания:</b>\n\n"

        for device in devices:
            # Get latest telemetry
            telemetry_result = await session.execute(
                select(Telemetry)
                .where(Telemetry.device_id == device.id)
                .order_by(desc(Telemetry.timestamp))
                .limit(1)
            )
            telemetry = telemetry_result.scalar_one_or_none()

            status_icon = "🟢" if device.is_online else "🔴"
            device_name = device.name or device.device_uid

            if telemetry:
                emoji = get_co2_emoji(telemetry.co2)
                text += (
                    f"{status_icon} <b>{device_name}</b>\n"
                    f"   {telemetry.co2} ppm {emoji} | "
                    f"{telemetry.temperature:.1f}°C | "
                    f"{telemetry.humidity:.0f}%\n\n"
                )
            else:
                text += f"{status_icon} <b>{device_name}</b>\n   Нет данных\n\n"

        await message.answer(text, parse_mode="HTML")


@router.message(Command("devices"))
async def cmd_devices(message: Message):
    """Handle /devices command - list devices."""
    user_id = message.from_user.id

    async with async_session_maker() as session:
        if settings.is_admin(user_id):
            result = await session.execute(select(Device))
        else:
            result = await session.execute(
                select(Device).where(Device.owner_telegram_id == user_id)
            )

        devices = result.scalars().all()

        if not devices:
            await message.answer("📭 Нет устройств.")
            return

        text = "📱 <b>Ваши устройства:</b>\n\n"

        for device in devices:
            status = "🟢 Online" if device.is_online else "🔴 Offline"
            name = device.name or "Без названия"
            location = device.location or "—"

            text += (
                f"<b>{name}</b> ({device.device_uid})\n"
                f"   Статус: {status}\n"
                f"   Расположение: {location}\n"
            )

            if device.last_seen:
                text += f"   Последняя связь: {device.last_seen.strftime('%d.%m %H:%M')}\n"

            text += "\n"

        await message.answer(text, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    text = (
        "📖 <b>Справка CO2 Monitor</b>\n\n"
        "<b>Команды:</b>\n"
        "/start - начало работы\n"
        "/status - текущие показания CO2\n"
        "/devices - список устройств\n"
        "/help - эта справка\n\n"
        "<b>Уровни CO2:</b>\n"
        "🟢 &lt; 800 ppm - Отлично\n"
        "🟡 800-1000 ppm - Хорошо\n"
        "🟠 1000-1500 ppm - Проветрите\n"
        "🔴 &gt; 1500 ppm - Критично\n"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Handle /admin command - admin panel."""
    user_id = message.from_user.id

    if not settings.is_admin(user_id):
        await message.answer("⛔ Доступ запрещён")
        return

    async with async_session_maker() as session:
        # Get stats
        devices_result = await session.execute(select(Device))
        devices = devices_result.scalars().all()

        online_count = sum(1 for d in devices if d.is_online)
        total_count = len(devices)

        text = (
            "🔧 <b>Админ-панель</b>\n\n"
            f"📱 Устройств: {total_count}\n"
            f"🟢 Online: {online_count}\n"
            f"🔴 Offline: {total_count - online_count}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📱 Все устройства", callback_data="admin:devices")],
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin:"))
async def handle_admin_callback(callback: CallbackQuery):
    """Handle admin panel callbacks."""
    user_id = callback.from_user.id

    if not settings.is_admin(user_id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    action = callback.data.split(":")[1]

    if action == "stats":
        # Show detailed stats
        async with async_session_maker() as session:
            telemetry_result = await session.execute(
                select(Telemetry).order_by(desc(Telemetry.timestamp)).limit(100)
            )
            telemetry_list = telemetry_result.scalars().all()

            if telemetry_list:
                avg_co2 = sum(t.co2 for t in telemetry_list) / len(telemetry_list)
                max_co2 = max(t.co2 for t in telemetry_list)
                min_co2 = min(t.co2 for t in telemetry_list)

                text = (
                    "📊 <b>Статистика (последние 100 записей)</b>\n\n"
                    f"Средний CO2: {avg_co2:.0f} ppm\n"
                    f"Максимум: {max_co2} ppm\n"
                    f"Минимум: {min_co2} ppm\n"
                )
            else:
                text = "📊 Нет данных для статистики"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back")]
            ])

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif action == "back":
        # Return to admin panel
        await cmd_admin(callback.message)


# ==================== MAIN ====================

async def main():
    """Entry point."""
    if not settings.bot_token:
        logger.error("❌ BOT_TOKEN is not set! Cannot start bot.")
        raise ValueError("BOT_TOKEN environment variable is required for bot service")

    logger.info("🚀 Starting CO2 Monitor Bot...")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    # Register handlers
    dp.include_router(router)

    logger.info("📡 Bot is running...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

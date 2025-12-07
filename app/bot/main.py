"""
CO2 Monitor - Telegram Bot
Provides user interface for monitoring CO2 levels
"""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, Router, F
from zoneinfo import ZoneInfo
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, desc

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router for handlers
router = Router()


# ==================== FSM STATES ====================

class BindDevice(StatesGroup):
    """States for device binding flow."""
    waiting_for_code = State()


# ==================== HELPERS ====================

async def get_or_create_user(telegram_user) -> User:
    """Get existing user or create new one."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update user info
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            user.last_activity = datetime.utcnow()
        else:
            # Create new user
            user = User(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                last_activity=datetime.utcnow()
            )
            session.add(user)

        await session.commit()
        return user


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


def format_datetime(dt: datetime, tz_name: str = "Europe/Moscow") -> str:
    """Format datetime in user's timezone."""
    if dt is None:
        return "—"

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    # If datetime is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Convert to user's timezone
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%d.%m %H:%M")


# ==================== HANDLERS ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    user_id = message.from_user.id

    # Create or update user in database
    await get_or_create_user(message.from_user)

    text = (
        f"👋 <b>Добро пожаловать в CO2 Monitor!</b>\n\n"
        f"Ваш ID: <code>{user_id}</code>\n\n"
        f"<b>Команды:</b>\n"
        f"/status - текущие показания\n"
        f"/devices - список устройств\n"
        f"/bind - привязать устройство\n"
        f"/help - справка\n"
    )

    if settings.is_admin(user_id):
        text += f"\n/admin - админ-панель"

    await message.answer(text, parse_mode="HTML")


@router.message(Command("bind"))
async def cmd_bind(message: Message, state: FSMContext):
    """Handle /bind command - start device binding flow."""
    await get_or_create_user(message.from_user)

    text = (
        "🔗 <b>Привязка устройства</b>\n\n"
        "Введите код активации устройства.\n"
        "Код указан на наклейке устройства (8 символов).\n\n"
        "Пример: <code>AB12CD34</code>\n\n"
        "Для отмены нажмите /cancel"
    )

    await state.set_state(BindDevice.waiting_for_code)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command - cancel current operation."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активной операции для отмены.")
        return

    await state.clear()
    await message.answer("❌ Операция отменена.", reply_markup=ReplyKeyboardRemove())


@router.message(BindDevice.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    """Process entered activation code."""
    code = message.text.strip().upper()
    user_id = message.from_user.id

    # Validate code format (8 alphanumeric characters)
    if len(code) != 8 or not code.isalnum():
        await message.answer(
            "⚠️ Неверный формат кода.\n"
            "Код должен содержать 8 букв и цифр.\n\n"
            "Попробуйте ещё раз или /cancel для отмены."
        )
        return

    async with async_session_maker() as session:
        # Find device by activation code
        result = await session.execute(
            select(Device).where(Device.activation_code == code)
        )
        device = result.scalar_one_or_none()

        if not device:
            await message.answer(
                "❌ Устройство с таким кодом не найдено.\n\n"
                "Проверьте код и попробуйте снова или /cancel для отмены."
            )
            return

        if device.owner_telegram_id:
            if device.owner_telegram_id == user_id:
                await message.answer(
                    f"ℹ️ Устройство <b>{device.name or device.device_uid}</b> "
                    f"уже привязано к вашему аккаунту.",
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    "⚠️ Это устройство уже привязано к другому пользователю.\n"
                    "Обратитесь к администратору."
                )
            await state.clear()
            return

        # Bind device to user
        device.owner_telegram_id = user_id
        await session.commit()

        await state.clear()
        await message.answer(
            f"✅ <b>Устройство успешно привязано!</b>\n\n"
            f"📱 {device.name or device.device_uid}\n"
            f"📍 {device.location or 'Расположение не указано'}\n\n"
            f"Теперь вы будете получать данные с этого устройства.\n"
            f"Используйте /status для просмотра показаний.",
            parse_mode="HTML"
        )


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
                "Используйте /bind для привязки устройства."
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
        # Get user's timezone
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        user_tz = user.timezone if user else "Europe/Moscow"

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
                text += f"   Последняя связь: {format_datetime(device.last_seen, user_tz)}\n"

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
        "/bind - привязать устройство\n"
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

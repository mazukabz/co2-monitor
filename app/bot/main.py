"""
CO2 Monitor - Telegram Bot
Provides user interface for monitoring CO2 levels
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta, time

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import BufferedInputFile
from zoneinfo import ZoneInfo
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from sqlalchemy import select, desc, and_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services.charts import generate_morning_report, generate_evening_report, generate_24h_report, generate_period_report


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router for handlers
router = Router()


# ==================== FSM STATES ====================

class BindDevice(StatesGroup):
    """States for device binding flow."""
    waiting_for_code = State()


class SettingsFlow(StatesGroup):
    """States for settings configuration."""
    waiting_for_threshold = State()
    waiting_for_morning_time = State()
    waiting_for_evening_time = State()
    waiting_for_interval = State()


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


@router.message(Command("morning"))
async def cmd_morning(message: Message):
    """Handle /morning command - generate night/morning report."""
    user_id = message.from_user.id

    # Show typing indicator while generating chart
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    async with async_session_maker() as session:
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
            await message.answer("📭 Нет привязанных устройств.")
            return

        # Get telemetry for last 24 hours (to cover night period)
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
                await message.answer(
                    f"📭 Нет ночных данных для <b>{device.name or device.device_uid}</b>",
                    parse_mode="HTML"
                )
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

            chart_buf = generate_morning_report(
                data,
                device.name or device.device_uid,
                user_tz
            )

            await message.answer_photo(
                BufferedInputFile(chart_buf.read(), filename="morning_report.png"),
                caption=f"🌙 Ночной отчёт — {device.name or device.device_uid}"
            )


@router.message(Command("evening"))
async def cmd_evening(message: Message):
    """Handle /evening command - generate day/evening report."""
    user_id = message.from_user.id

    # Show typing indicator while generating chart
    await message.bot.send_chat_action(message.chat.id, "upload_photo")

    async with async_session_maker() as session:
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
            await message.answer("📭 Нет привязанных устройств.")
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
                await message.answer(
                    f"📭 Нет дневных данных для <b>{device.name or device.device_uid}</b>",
                    parse_mode="HTML"
                )
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

            chart_buf = generate_evening_report(
                data,
                device.name or device.device_uid,
                user_tz
            )

            await message.answer_photo(
                BufferedInputFile(chart_buf.read(), filename="evening_report.png"),
                caption=f"☀️ Дневной отчёт — {device.name or device.device_uid}"
            )


@router.message(Command("report"))
async def cmd_report(message: Message):
    """Handle /report command - show period selection."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 час", callback_data="report:1"),
            InlineKeyboardButton(text="6 часов", callback_data="report:6"),
            InlineKeyboardButton(text="12 часов", callback_data="report:12"),
        ],
        [
            InlineKeyboardButton(text="24 часа", callback_data="report:24"),
            InlineKeyboardButton(text="7 дней", callback_data="report:168"),
            InlineKeyboardButton(text="30 дней", callback_data="report:720"),
        ],
    ])

    await message.answer(
        "📊 <b>Выберите период для отчёта:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# Fun loading messages for report generation
LOADING_MESSAGES = [
    "🎨 Рисую красивый график...",
    "📊 Анализирую данные о вашем воздухе...",
    "🔬 Исследую молекулы CO2...",
    "🌬️ Считаю каждую молекулу...",
    "📈 Строю инфографику...",
    "🎯 Вычисляю статистику...",
    "🖌️ Добавляю последние штрихи...",
    "🔮 Предсказываю качество воздуха...",
    "🌡️ Измеряю температуру данных...",
    "💨 Обрабатываю воздушные потоки...",
]


@router.callback_query(F.data.startswith("report:"))
async def callback_report_period(callback: CallbackQuery):
    """Handle report period selection."""
    period_hours = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Period labels
    period_labels = {
        1: "1 час",
        6: "6 часов",
        12: "12 часов",
        24: "24 часа",
        168: "7 дней",
        720: "30 дней",
    }
    period_label = period_labels.get(period_hours, f"{period_hours} ч")

    # Show fun loading message
    loading_msg = random.choice(LOADING_MESSAGES)
    await callback.answer(loading_msg, show_alert=False)

    # Edit message to show loading
    try:
        await callback.message.edit_text(
            f"⏳ <b>{loading_msg}</b>\n\nПериод: {period_label}",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Show typing indicator while generating chart
    await callback.bot.send_chat_action(callback.message.chat.id, "upload_photo")

    async with async_session_maker() as session:
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
            await callback.message.edit_text(
                "📭 У вас нет привязанных устройств.\n"
                "Используйте /bind для привязки."
            )
            return

        since = datetime.utcnow() - timedelta(hours=period_hours)

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
                await callback.message.answer(
                    f"📭 Нет данных за {period_label} для <b>{device.name or device.device_uid}</b>",
                    parse_mode="HTML"
                )
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

            chart_buf = generate_period_report(
                data,
                device.name or device.device_uid,
                user_tz,
                period_hours,
                period_label
            )

            await callback.message.answer_photo(
                BufferedInputFile(chart_buf.read(), filename=f"report_{period_hours}h.png"),
                caption=f"📊 Отчёт за {period_label} — {device.name or device.device_uid}"
            )

    # Delete the period selection message
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Handle /settings command - show and configure user settings."""
    user_id = message.from_user.id

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала используйте /start")
            return

        # Format current settings
        morning_status = "✅" if user.morning_report_enabled else "❌"
        evening_status = "✅" if user.evening_report_enabled else "❌"
        alerts_status = "✅" if user.alerts_enabled else "❌"

        text = (
            "⚙️ <b>Настройки уведомлений</b>\n\n"
            f"🔔 Оповещения: {alerts_status}\n"
            f"   Порог CO2: {user.alert_threshold} ppm\n\n"
            f"🌅 Утренний отчёт: {morning_status}\n"
            f"   Время: {user.morning_report_time.strftime('%H:%M')}\n\n"
            f"🌆 Вечерний отчёт: {evening_status}\n"
            f"   Время: {user.evening_report_time.strftime('%H:%M')}\n\n"
            f"🕐 Часовой пояс: {user.timezone}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔔 Оповещения: {'ВКЛ' if user.alerts_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_alerts"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Порог CO2",
                    callback_data="settings:threshold"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🌅 Утренний: {'ВКЛ' if user.morning_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_morning"
                ),
                InlineKeyboardButton(
                    text="⏰",
                    callback_data="settings:morning_time"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🌆 Вечерний: {'ВКЛ' if user.evening_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_evening"
                ),
                InlineKeyboardButton(
                    text="⏰",
                    callback_data="settings:evening_time"
                )
            ],
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("settings:"))
async def handle_settings_callback(callback: CallbackQuery, state: FSMContext):
    """Handle settings callbacks."""
    user_id = callback.from_user.id
    action = callback.data.split(":")[1]

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await callback.answer("Ошибка", show_alert=True)
            return

        if action == "toggle_alerts":
            user.alerts_enabled = not user.alerts_enabled
            await session.commit()
            await callback.answer(f"Оповещения {'включены' if user.alerts_enabled else 'выключены'}")

        elif action == "toggle_morning":
            user.morning_report_enabled = not user.morning_report_enabled
            await session.commit()
            await callback.answer(f"Утренний отчёт {'включён' if user.morning_report_enabled else 'выключён'}")

        elif action == "toggle_evening":
            user.evening_report_enabled = not user.evening_report_enabled
            await session.commit()
            await callback.answer(f"Вечерний отчёт {'включён' if user.evening_report_enabled else 'выключён'}")

        elif action == "threshold":
            await callback.answer()
            await callback.message.answer(
                "📊 Введите порог CO2 для оповещений (ppm):\n"
                "Например: <code>1000</code> или <code>800</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_threshold)
            return

        elif action == "morning_time":
            await callback.answer()
            await callback.message.answer(
                "🌅 Введите время утреннего отчёта (ЧЧ:ММ):\n"
                "Например: <code>08:00</code> или <code>07:30</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_morning_time)
            return

        elif action == "evening_time":
            await callback.answer()
            await callback.message.answer(
                "🌆 Введите время вечернего отчёта (ЧЧ:ММ):\n"
                "Например: <code>22:00</code> или <code>21:30</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_evening_time)
            return

    # Refresh settings view
    await cmd_settings(callback.message)


@router.message(SettingsFlow.waiting_for_threshold)
async def process_threshold(message: Message, state: FSMContext):
    """Process threshold input."""
    try:
        threshold = int(message.text.strip())
        if threshold < 400 or threshold > 5000:
            await message.answer("⚠️ Порог должен быть от 400 до 5000 ppm. Попробуйте снова.")
            return
    except ValueError:
        await message.answer("⚠️ Введите число. Попробуйте снова.")
        return

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.alert_threshold = threshold
            await session.commit()

    await state.clear()
    await message.answer(f"✅ Порог оповещений установлен: {threshold} ppm")


@router.message(SettingsFlow.waiting_for_morning_time)
async def process_morning_time(message: Message, state: FSMContext):
    """Process morning time input."""
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        new_time = time(hour, minute)
    except (ValueError, IndexError):
        await message.answer("⚠️ Неверный формат. Введите время как ЧЧ:ММ")
        return

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.morning_report_time = new_time
            await session.commit()

    await state.clear()
    await message.answer(f"✅ Время утреннего отчёта: {new_time.strftime('%H:%M')}")


@router.message(SettingsFlow.waiting_for_evening_time)
async def process_evening_time(message: Message, state: FSMContext):
    """Process evening time input."""
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        new_time = time(hour, minute)
    except (ValueError, IndexError):
        await message.answer("⚠️ Неверный формат. Введите время как ЧЧ:ММ")
        return

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.evening_report_time = new_time
            await session.commit()

    await state.clear()
    await message.answer(f"✅ Время вечернего отчёта: {new_time.strftime('%H:%M')}")


def get_menu_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard with all main commands."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Отчёт", callback_data="menu:report"),
            InlineKeyboardButton(text="📈 Статус", callback_data="menu:status"),
        ],
        [
            InlineKeyboardButton(text="🌙 Ночной", callback_data="menu:morning"),
            InlineKeyboardButton(text="☀️ Дневной", callback_data="menu:evening"),
        ],
        [
            InlineKeyboardButton(text="📱 Устройства", callback_data="menu:devices"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton(text="🔗 Привязать", callback_data="menu:bind"),
            InlineKeyboardButton(text="❓ Справка", callback_data="menu:help"),
        ],
    ])


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Handle /menu command - show main menu with buttons."""
    await message.answer(
        "📋 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=get_menu_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("menu:"))
async def callback_menu(callback: CallbackQuery):
    """Handle menu button clicks."""
    action = callback.data.split(":")[1]

    # Map actions to commands
    if action == "report":
        await callback.message.delete()
        # Show report period selection
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1 час", callback_data="report:1"),
                InlineKeyboardButton(text="6 часов", callback_data="report:6"),
                InlineKeyboardButton(text="12 часов", callback_data="report:12"),
            ],
            [
                InlineKeyboardButton(text="24 часа", callback_data="report:24"),
                InlineKeyboardButton(text="7 дней", callback_data="report:168"),
                InlineKeyboardButton(text="30 дней", callback_data="report:720"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
        ])
        await callback.message.answer(
            "📊 <b>Выберите период для отчёта:</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    elif action == "back":
        await callback.message.edit_text(
            "📋 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=get_menu_keyboard(),
            parse_mode="HTML"
        )
    elif action == "help":
        await callback.message.delete()
        text = (
            "📖 <b>Справка CO2 Monitor</b>\n\n"
            "<b>Основные команды:</b>\n"
            "/menu - главное меню\n"
            "/status - текущие показания CO2\n"
            "/devices - список устройств\n"
            "/bind - привязать устройство\n\n"
            "<b>Графики и отчёты:</b>\n"
            "/report - отчёт (выбор периода)\n"
            "/morning - ночной отчёт (качество сна)\n"
            "/evening - дневной отчёт\n\n"
            "<b>Настройки:</b>\n"
            "/settings - настройки уведомлений\n\n"
            "<b>Уровни CO2:</b>\n"
            "🟢 &lt; 800 ppm - Отлично\n"
            "🟡 800-1000 ppm - Хорошо\n"
            "🟠 1000-1500 ppm - Проветрите\n"
            "🔴 &gt; 1500 ppm - Критично\n"
        )
        await callback.message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📋 Меню", callback_data="menu:back_to_menu")]]
        ))
    elif action == "back_to_menu":
        await callback.message.delete()
        await callback.message.answer(
            "📋 <b>Главное меню</b>\n\nВыберите действие:",
            reply_markup=get_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        # For other actions, simulate command
        await callback.message.delete()
        # Create fake message to call command handlers
        if action == "status":
            await cmd_status(callback.message)
        elif action == "devices":
            await cmd_devices(callback.message)
        elif action == "morning":
            await cmd_morning(callback.message)
        elif action == "evening":
            await cmd_evening(callback.message)
        elif action == "settings":
            await cmd_settings(callback.message)
        elif action == "bind":
            await cmd_bind(callback.message)

    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    text = (
        "📖 <b>Справка CO2 Monitor</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/menu - главное меню с кнопками\n"
        "/status - текущие показания CO2\n"
        "/devices - список устройств\n"
        "/bind - привязать устройство\n\n"
        "<b>Графики и отчёты:</b>\n"
        "/report - отчёт (выбор периода)\n"
        "/morning - ночной отчёт (качество сна)\n"
        "/evening - дневной отчёт\n\n"
        "<b>Настройки:</b>\n"
        "/settings - настройки уведомлений\n\n"
        "<b>Уровни CO2:</b>\n"
        "🟢 &lt; 800 ppm - Отлично\n"
        "🟡 800-1000 ppm - Хорошо\n"
        "🟠 1000-1500 ppm - Проветрите\n"
        "🔴 &gt; 1500 ppm - Критично\n"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Открыть меню", callback_data="menu:back_to_menu")]]
    ))


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
            [InlineKeyboardButton(text="📱 Управление устройствами", callback_data="admin:devices")],
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin:"))
async def handle_admin_callback(callback: CallbackQuery, state: FSMContext):
    """Handle admin panel callbacks."""
    user_id = callback.from_user.id

    if not settings.is_admin(user_id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1]

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

    elif action == "devices":
        # Show device list with management options
        async with async_session_maker() as session:
            devices_result = await session.execute(select(Device))
            devices = devices_result.scalars().all()

            if not devices:
                await callback.message.edit_text("📭 Нет устройств")
                return

            text = "📱 <b>Управление устройствами</b>\n\n"

            buttons = []
            for device in devices:
                status = "🟢" if device.is_online else "🔴"
                name = device.name or device.device_uid
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{status} {name} ({device.send_interval}с)",
                        callback_data=f"admin:device:{device.id}"
                    )
                ])

            buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif action == "device":
        # Show single device management
        device_id = int(parts[2])

        async with async_session_maker() as session:
            device_result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = device_result.scalar_one_or_none()

            if not device:
                await callback.message.edit_text("❌ Устройство не найдено")
                return

            status = "🟢 Online" if device.is_online else "🔴 Offline"
            text = (
                f"📱 <b>{device.name or device.device_uid}</b>\n\n"
                f"UID: <code>{device.device_uid}</code>\n"
                f"Статус: {status}\n"
                f"Код активации: <code>{device.activation_code}</code>\n"
                f"Интервал отправки: {device.send_interval} сек\n"
                f"Прошивка: {device.firmware_version or '—'}\n"
                f"IP: {device.last_ip or '—'}\n"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⏱ 30 сек", callback_data=f"admin:interval:{device_id}:30"),
                    InlineKeyboardButton(text="⏱ 60 сек", callback_data=f"admin:interval:{device_id}:60"),
                ],
                [
                    InlineKeyboardButton(text="⏱ 120 сек", callback_data=f"admin:interval:{device_id}:120"),
                    InlineKeyboardButton(text="⏱ 300 сек", callback_data=f"admin:interval:{device_id}:300"),
                ],
                [InlineKeyboardButton(text="◀️ К списку", callback_data="admin:devices")],
            ])

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif action == "interval":
        # Set device send interval
        device_id = int(parts[2])
        interval = int(parts[3])

        async with async_session_maker() as session:
            device_result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = device_result.scalar_one_or_none()

            if not device:
                await callback.message.answer("❌ Устройство не найдено")
                return

            # Update in database
            device.send_interval = interval
            await session.commit()

            # Push config via MQTT
            from app.mqtt.main import publish_device_config
            success = publish_device_config(device.device_uid, {"send_interval": interval})

            if success:
                await callback.message.answer(
                    f"✅ Интервал для <b>{device.name or device.device_uid}</b> "
                    f"установлен: {interval} сек\n\n"
                    f"Конфигурация отправлена на устройство.",
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer(
                    f"⚠️ Интервал сохранён в БД ({interval} сек), "
                    f"но не удалось отправить на устройство.\n"
                    f"Устройство получит настройки при следующем подключении.",
                    parse_mode="HTML"
                )

    elif action == "back":
        # Return to admin panel - rebuild the panel inline
        async with async_session_maker() as session:
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
                [InlineKeyboardButton(text="📱 Управление устройствами", callback_data="admin:devices")],
            ])

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


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

    # Import scheduler here to avoid circular imports
    from app.services.scheduler import ReportScheduler

    # Start scheduler as background task
    scheduler = ReportScheduler(bot)
    scheduler_task = asyncio.create_task(scheduler.start())

    logger.info("📡 Bot is running...")
    logger.info("📅 Scheduler is running...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

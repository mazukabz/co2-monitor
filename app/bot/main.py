"""
CO2 Monitor - Telegram Bot
Provides user interface for monitoring CO2 levels
Refactored with persistent menu and clean command structure
"""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta, time

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    BufferedInputFile, Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat
)
from zoneinfo import ZoneInfo
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, desc, and_

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services.charts import generate_morning_report, generate_evening_report, generate_period_report


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Router for handlers
router = Router()


# ==================== CONSTANTS ====================

# Main menu button texts (used for both keyboard and text matching)
BTN_STATUS = "📊 Статус"
BTN_REPORT = "📈 Отчёт"
BTN_SETTINGS = "⚙️ Настройки"
BTN_HELP = "❓ Помощь"

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


# ==================== FSM STATES ====================

class BindDevice(StatesGroup):
    """States for device binding flow."""
    waiting_for_code = State()


class SettingsFlow(StatesGroup):
    """States for settings configuration."""
    waiting_for_threshold = State()
    waiting_for_morning_time = State()
    waiting_for_evening_time = State()


# ==================== KEYBOARDS ====================

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Get persistent reply keyboard that stays at bottom."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_REPORT)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие..."
    )


def get_report_period_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard for report period selection."""
    return InlineKeyboardMarkup(inline_keyboard=[
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
        [
            InlineKeyboardButton(text="🌙 Ночной", callback_data="report:morning"),
            InlineKeyboardButton(text="☀️ Дневной", callback_data="report:evening"),
        ],
    ])


# ==================== HELPERS ====================

async def get_or_create_user(telegram_user) -> User:
    """Get existing user or create new one."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.username = telegram_user.username
            user.first_name = telegram_user.first_name
            user.last_name = telegram_user.last_name
            user.last_activity = datetime.utcnow()
        else:
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

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%d.%m %H:%M")


async def setup_bot_commands(bot: Bot):
    """Setup bot commands menu for all users and admins."""
    # Default commands for all users
    default_commands = [
        BotCommand(command="start", description="🚀 Начать работу"),
        BotCommand(command="status", description="📊 Текущие показания"),
        BotCommand(command="report", description="📈 Отчёт за период"),
        BotCommand(command="devices", description="📱 Мои устройства"),
        BotCommand(command="bind", description="🔗 Привязать устройство"),
        BotCommand(command="settings", description="⚙️ Настройки"),
        BotCommand(command="help", description="❓ Справка"),
    ]

    await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())
    logger.info("✅ Bot commands registered")

    # Add admin command for admin users
    admin_commands = default_commands + [
        BotCommand(command="admin", description="🔧 Админ-панель"),
    ]

    for admin_id in settings.admin_user_ids:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
            logger.info(f"✅ Admin commands set for user {admin_id}")
        except Exception as e:
            logger.warning(f"⚠️ Could not set admin commands for {admin_id}: {e}")


# ==================== COMMAND HANDLERS ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command - welcome and show main menu."""
    user_id = message.from_user.id
    await get_or_create_user(message.from_user)

    text = (
        f"👋 <b>Добро пожаловать в CO2 Monitor!</b>\n\n"
        f"Этот бот поможет вам следить за качеством воздуха.\n\n"
        f"<b>Что я умею:</b>\n"
        f"📊 Показывать текущие данные CO2\n"
        f"📈 Строить красивые графики\n"
        f"🔔 Отправлять утренние/вечерние отчёты\n"
        f"⚠️ Предупреждать о плохом воздухе\n\n"
        f"Используйте кнопки меню внизу 👇"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message):
    """Handle /status command and 📊 Статус button."""
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
            await message.answer(
                "📭 <b>У вас нет привязанных устройств</b>\n\n"
                "Используйте /bind чтобы привязать устройство по коду активации.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return

        text = "📊 <b>Текущие показания:</b>\n\n"

        for device in devices:
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
                status_text = get_co2_status(telemetry.co2)
                text += (
                    f"{status_icon} <b>{device_name}</b>\n"
                    f"   CO2: <b>{telemetry.co2} ppm</b> {emoji} ({status_text})\n"
                    f"   🌡 {telemetry.temperature:.1f}°C  💧 {telemetry.humidity:.0f}%\n\n"
                )
            else:
                text += f"{status_icon} <b>{device_name}</b>\n   Нет данных\n\n"

        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())


@router.message(Command("report"))
@router.message(F.text == BTN_REPORT)
async def cmd_report(message: Message):
    """Handle /report command and 📈 Отчёт button."""
    await message.answer(
        "📊 <b>Выберите период для отчёта:</b>\n\n"
        "Для специальных отчётов:\n"
        "🌙 <b>Ночной</b> — анализ сна (22:00-08:00)\n"
        "☀️ <b>Дневной</b> — итоги дня (08:00-22:00)",
        reply_markup=get_report_period_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("devices"))
async def cmd_devices(message: Message):
    """Handle /devices command - list user's devices."""
    user_id = message.from_user.id

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
            await message.answer(
                "📭 <b>Нет устройств</b>\n\n"
                "Привяжите устройство: /bind",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return

        text = "📱 <b>Ваши устройства:</b>\n\n"

        for device in devices:
            status = "🟢 Online" if device.is_online else "🔴 Offline"
            name = device.name or "Без названия"
            location = device.location or "—"

            text += (
                f"<b>{name}</b>\n"
                f"   📍 {location}\n"
                f"   {status}\n"
            )

            if device.last_seen:
                text += f"   🕐 {format_datetime(device.last_seen, user_tz)}\n"

            text += "\n"

        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())


@router.message(Command("bind"))
async def cmd_bind(message: Message, state: FSMContext):
    """Handle /bind command - start device binding flow."""
    await get_or_create_user(message.from_user)

    text = (
        "🔗 <b>Привязка устройства</b>\n\n"
        "Введите 8-значный код активации.\n"
        "Код указан на наклейке устройства.\n\n"
        "Пример: <code>AB12CD34</code>\n\n"
        "Для отмены: /cancel"
    )

    await state.set_state(BindDevice.waiting_for_code)
    await message.answer(text, parse_mode="HTML")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command - cancel current operation."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "Нет активной операции.",
            reply_markup=get_main_keyboard()
        )
        return

    await state.clear()
    await message.answer(
        "❌ Операция отменена.",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message):
    """Handle /settings command and ⚙️ Настройки button."""
    user_id = message.from_user.id

    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            await get_or_create_user(message.from_user)
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

        morning_status = "✅" if user.morning_report_enabled else "❌"
        evening_status = "✅" if user.evening_report_enabled else "❌"
        alerts_status = "✅" if user.alerts_enabled else "❌"

        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"🔔 <b>Оповещения:</b> {alerts_status}\n"
            f"   Порог: {user.alert_threshold} ppm\n\n"
            f"🌅 <b>Утренний отчёт:</b> {morning_status}\n"
            f"   Время: {user.morning_report_time.strftime('%H:%M')}\n\n"
            f"🌆 <b>Вечерний отчёт:</b> {evening_status}\n"
            f"   Время: {user.evening_report_time.strftime('%H:%M')}\n\n"
            f"🕐 <b>Часовой пояс:</b> {user.timezone}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔔 Оповещения: {'ВКЛ' if user.alerts_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_alerts"
                )
            ],
            [
                InlineKeyboardButton(text="📊 Изменить порог", callback_data="settings:threshold")
            ],
            [
                InlineKeyboardButton(
                    text=f"🌅 Утренний: {'ВКЛ' if user.morning_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_morning"
                ),
                InlineKeyboardButton(text="⏰", callback_data="settings:morning_time")
            ],
            [
                InlineKeyboardButton(
                    text=f"🌆 Вечерний: {'ВКЛ' if user.evening_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_evening"
                ),
                InlineKeyboardButton(text="⏰", callback_data="settings:evening_time")
            ],
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message):
    """Handle /help command and ❓ Помощь button."""
    text = (
        "📖 <b>Справка CO2 Monitor</b>\n\n"
        "<b>🎛 Основные функции:</b>\n"
        "📊 <b>Статус</b> — текущие показания\n"
        "📈 <b>Отчёт</b> — график за период\n"
        "⚙️ <b>Настройки</b> — уведомления\n\n"
        "<b>📋 Команды:</b>\n"
        "/status — текущие показания\n"
        "/report — отчёт за период\n"
        "/devices — список устройств\n"
        "/bind — привязать устройство\n"
        "/settings — настройки\n\n"
        "<b>🚦 Уровни CO2:</b>\n"
        "🟢 &lt;800 ppm — Отлично\n"
        "🟡 800-1000 ppm — Хорошо\n"
        "🟠 1000-1500 ppm — Проветрите\n"
        "🔴 &gt;1500 ppm — Критично\n\n"
        "<b>💡 Советы:</b>\n"
        "• Проветривайте при CO2 &gt;1000\n"
        "• Для сна оптимально &lt;800\n"
        "• Настройте автоотчёты в ⚙️"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Handle /admin command - admin panel."""
    user_id = message.from_user.id

    if not settings.is_admin(user_id):
        await message.answer("⛔ Доступ запрещён")
        return

    async with async_session_maker() as session:
        devices_result = await session.execute(select(Device))
        devices = devices_result.scalars().all()

        online_count = sum(1 for d in devices if d.is_online)
        total_count = len(devices)

        users_result = await session.execute(select(User))
        users_count = len(users_result.scalars().all())

        text = (
            "🔧 <b>Админ-панель</b>\n\n"
            f"👥 Пользователей: {users_count}\n"
            f"📱 Устройств: {total_count}\n"
            f"   🟢 Online: {online_count}\n"
            f"   🔴 Offline: {total_count - online_count}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📱 Управление устройствами", callback_data="admin:devices")],
        ])

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ==================== FSM HANDLERS ====================

@router.message(BindDevice.waiting_for_code)
async def process_activation_code(message: Message, state: FSMContext):
    """Process entered activation code."""
    code = message.text.strip().upper()
    user_id = message.from_user.id

    if len(code) != 8 or not code.isalnum():
        await message.answer(
            "⚠️ Неверный формат.\n"
            "Код: 8 букв и цифр.\n\n"
            "Попробуйте снова или /cancel"
        )
        return

    async with async_session_maker() as session:
        result = await session.execute(
            select(Device).where(Device.activation_code == code)
        )
        device = result.scalar_one_or_none()

        if not device:
            await message.answer(
                "❌ Устройство не найдено.\n\n"
                "Проверьте код или /cancel"
            )
            return

        if device.owner_telegram_id:
            if device.owner_telegram_id == user_id:
                await message.answer(
                    f"ℹ️ <b>{device.name or device.device_uid}</b> уже привязано к вам.",
                    parse_mode="HTML"
                )
            else:
                await message.answer("⚠️ Устройство привязано к другому пользователю.")
            await state.clear()
            return

        device.owner_telegram_id = user_id
        await session.commit()

        await state.clear()
        await message.answer(
            f"✅ <b>Устройство привязано!</b>\n\n"
            f"📱 {device.name or device.device_uid}\n\n"
            f"Нажмите 📊 Статус для просмотра данных.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )


@router.message(SettingsFlow.waiting_for_threshold)
async def process_threshold(message: Message, state: FSMContext):
    """Process threshold input."""
    try:
        threshold = int(message.text.strip())
        if threshold < 400 or threshold > 5000:
            await message.answer("⚠️ Порог: 400-5000 ppm")
            return
    except ValueError:
        await message.answer("⚠️ Введите число")
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
    await message.answer(
        f"✅ Порог установлен: {threshold} ppm",
        reply_markup=get_main_keyboard()
    )


@router.message(SettingsFlow.waiting_for_morning_time)
async def process_morning_time(message: Message, state: FSMContext):
    """Process morning time input."""
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        new_time = time(hour, minute)
    except (ValueError, IndexError):
        await message.answer("⚠️ Формат: ЧЧ:ММ")
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
    await message.answer(
        f"✅ Утренний отчёт: {new_time.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )


@router.message(SettingsFlow.waiting_for_evening_time)
async def process_evening_time(message: Message, state: FSMContext):
    """Process evening time input."""
    try:
        parts = message.text.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        new_time = time(hour, minute)
    except (ValueError, IndexError):
        await message.answer("⚠️ Формат: ЧЧ:ММ")
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
    await message.answer(
        f"✅ Вечерний отчёт: {new_time.strftime('%H:%M')}",
        reply_markup=get_main_keyboard()
    )


# ==================== CALLBACK HANDLERS ====================

@router.callback_query(F.data.startswith("report:"))
async def callback_report(callback: CallbackQuery):
    """Handle report period selection."""
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id

    # Handle special reports
    if action == "morning":
        await callback.answer()
        await callback.message.delete()
        await generate_special_report(callback, "morning")
        return
    elif action == "evening":
        await callback.answer()
        await callback.message.delete()
        await generate_special_report(callback, "evening")
        return

    # Standard period reports
    period_hours = int(action)
    period_labels = {
        1: "1 час", 6: "6 часов", 12: "12 часов",
        24: "24 часа", 168: "7 дней", 720: "30 дней",
    }
    period_label = period_labels.get(period_hours, f"{period_hours} ч")

    loading_msg = random.choice(LOADING_MESSAGES)
    await callback.answer(loading_msg, show_alert=False)

    try:
        await callback.message.edit_text(
            f"⏳ <b>{loading_msg}</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

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
                "📭 Нет привязанных устройств.\n"
                "Используйте /bind"
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
                    f"📭 Нет данных за {period_label}",
                    reply_markup=get_main_keyboard()
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
                caption=f"📊 {period_label} — {device.name or device.device_uid}",
                reply_markup=get_main_keyboard()
            )

    try:
        await callback.message.delete()
    except Exception:
        pass


async def generate_special_report(callback: CallbackQuery, report_type: str):
    """Generate morning or evening special report."""
    user_id = callback.from_user.id

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
            await callback.message.answer(
                "📭 Нет привязанных устройств.",
                reply_markup=get_main_keyboard()
            )
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
                await callback.message.answer(
                    f"📭 Нет данных для отчёта",
                    reply_markup=get_main_keyboard()
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

            if report_type == "morning":
                chart_buf = generate_morning_report(data, device.name or device.device_uid, user_tz)
                caption = f"🌙 Ночной отчёт — {device.name or device.device_uid}"
            else:
                chart_buf = generate_evening_report(data, device.name or device.device_uid, user_tz)
                caption = f"☀️ Дневной отчёт — {device.name or device.device_uid}"

            await callback.message.answer_photo(
                BufferedInputFile(chart_buf.read(), filename=f"{report_type}_report.png"),
                caption=caption,
                reply_markup=get_main_keyboard()
            )


@router.callback_query(F.data.startswith("settings:"))
async def callback_settings(callback: CallbackQuery, state: FSMContext):
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
            await callback.answer(f"Оповещения {'ВКЛ' if user.alerts_enabled else 'ВЫКЛ'}")

        elif action == "toggle_morning":
            user.morning_report_enabled = not user.morning_report_enabled
            await session.commit()
            await callback.answer(f"Утренний отчёт {'ВКЛ' if user.morning_report_enabled else 'ВЫКЛ'}")

        elif action == "toggle_evening":
            user.evening_report_enabled = not user.evening_report_enabled
            await session.commit()
            await callback.answer(f"Вечерний отчёт {'ВКЛ' if user.evening_report_enabled else 'ВЫКЛ'}")

        elif action == "threshold":
            await callback.answer()
            await callback.message.answer(
                "📊 Введите порог CO2 (ppm):\n"
                "Например: <code>1000</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_threshold)
            return

        elif action == "morning_time":
            await callback.answer()
            await callback.message.answer(
                "🌅 Время утреннего отчёта (ЧЧ:ММ):\n"
                "Например: <code>08:00</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_morning_time)
            return

        elif action == "evening_time":
            await callback.answer()
            await callback.message.answer(
                "🌆 Время вечернего отчёта (ЧЧ:ММ):\n"
                "Например: <code>22:00</code>\n\n"
                "/cancel для отмены",
                parse_mode="HTML"
            )
            await state.set_state(SettingsFlow.waiting_for_evening_time)
            return

    # Refresh settings - get fresh user data
    async with async_session_maker() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()

        morning_status = "✅" if user.morning_report_enabled else "❌"
        evening_status = "✅" if user.evening_report_enabled else "❌"
        alerts_status = "✅" if user.alerts_enabled else "❌"

        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"🔔 <b>Оповещения:</b> {alerts_status}\n"
            f"   Порог: {user.alert_threshold} ppm\n\n"
            f"🌅 <b>Утренний отчёт:</b> {morning_status}\n"
            f"   Время: {user.morning_report_time.strftime('%H:%M')}\n\n"
            f"🌆 <b>Вечерний отчёт:</b> {evening_status}\n"
            f"   Время: {user.evening_report_time.strftime('%H:%M')}\n\n"
            f"🕐 <b>Часовой пояс:</b> {user.timezone}\n"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🔔 Оповещения: {'ВКЛ' if user.alerts_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_alerts"
                )
            ],
            [
                InlineKeyboardButton(text="📊 Изменить порог", callback_data="settings:threshold")
            ],
            [
                InlineKeyboardButton(
                    text=f"🌅 Утренний: {'ВКЛ' if user.morning_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_morning"
                ),
                InlineKeyboardButton(text="⏰", callback_data="settings:morning_time")
            ],
            [
                InlineKeyboardButton(
                    text=f"🌆 Вечерний: {'ВКЛ' if user.evening_report_enabled else 'ВЫКЛ'}",
                    callback_data="settings:toggle_evening"
                ),
                InlineKeyboardButton(text="⏰", callback_data="settings:evening_time")
            ],
        ])

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            pass


@router.callback_query(F.data.startswith("admin:"))
async def callback_admin(callback: CallbackQuery, state: FSMContext):
    """Handle admin panel callbacks."""
    user_id = callback.from_user.id

    if not settings.is_admin(user_id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1]

    if action == "stats":
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
                    "📊 <b>Статистика (100 записей)</b>\n\n"
                    f"Средний CO2: {avg_co2:.0f} ppm\n"
                    f"Максимум: {max_co2} ppm\n"
                    f"Минимум: {min_co2} ppm\n"
                )
            else:
                text = "📊 Нет данных"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="admin:back")]
            ])

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif action == "devices":
        async with async_session_maker() as session:
            devices_result = await session.execute(select(Device))
            devices = devices_result.scalars().all()

            if not devices:
                await callback.message.edit_text("📭 Нет устройств")
                return

            text = "📱 <b>Устройства:</b>\n"

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
        device_id = int(parts[2])

        async with async_session_maker() as session:
            device_result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = device_result.scalar_one_or_none()

            if not device:
                await callback.message.edit_text("❌ Не найдено")
                return

            status = "🟢 Online" if device.is_online else "🔴 Offline"
            text = (
                f"📱 <b>{device.name or device.device_uid}</b>\n\n"
                f"UID: <code>{device.device_uid}</code>\n"
                f"Статус: {status}\n"
                f"Код: <code>{device.activation_code}</code>\n"
                f"Интервал: {device.send_interval} сек\n"
                f"Прошивка: {device.firmware_version or '—'}\n"
                f"IP: {device.last_ip or '—'}\n"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="30с", callback_data=f"admin:interval:{device_id}:30"),
                    InlineKeyboardButton(text="60с", callback_data=f"admin:interval:{device_id}:60"),
                    InlineKeyboardButton(text="120с", callback_data=f"admin:interval:{device_id}:120"),
                    InlineKeyboardButton(text="300с", callback_data=f"admin:interval:{device_id}:300"),
                ],
                [InlineKeyboardButton(text="◀️ К списку", callback_data="admin:devices")],
            ])

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    elif action == "interval":
        device_id = int(parts[2])
        interval = int(parts[3])

        async with async_session_maker() as session:
            device_result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = device_result.scalar_one_or_none()

            if not device:
                await callback.message.answer("❌ Не найдено")
                return

            device.send_interval = interval
            await session.commit()

            from app.mqtt.main import publish_device_config
            success = publish_device_config(device.device_uid, {"send_interval": interval})

            if success:
                await callback.message.answer(
                    f"✅ Интервал {interval}с установлен и отправлен на устройство",
                    reply_markup=get_main_keyboard()
                )
            else:
                await callback.message.answer(
                    f"⚠️ Интервал сохранён, но устройство offline",
                    reply_markup=get_main_keyboard()
                )

    elif action == "back":
        async with async_session_maker() as session:
            devices_result = await session.execute(select(Device))
            devices = devices_result.scalars().all()

            online_count = sum(1 for d in devices if d.is_online)
            total_count = len(devices)

            users_result = await session.execute(select(User))
            users_count = len(users_result.scalars().all())

            text = (
                "🔧 <b>Админ-панель</b>\n\n"
                f"👥 Пользователей: {users_count}\n"
                f"📱 Устройств: {total_count}\n"
                f"   🟢 Online: {online_count}\n"
                f"   🔴 Offline: {total_count - online_count}\n"
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
        logger.error("❌ BOT_TOKEN is not set!")
        raise ValueError("BOT_TOKEN required")

    logger.info("🚀 Starting CO2 Monitor Bot...")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    # Register handlers
    dp.include_router(router)

    # Setup bot commands menu
    await setup_bot_commands(bot)

    # Import and start scheduler
    from app.services.scheduler import ReportScheduler
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

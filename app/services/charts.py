"""
Charts Service - generates infographics for CO2 monitoring
Uses matplotlib + seaborn for server-side PNG generation
"""

import matplotlib
matplotlib.use('Agg')  # Headless mode - must be before pyplot import

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional
from zoneinfo import ZoneInfo

# Set seaborn style
sns.set_theme(style="whitegrid", palette="husl")

# CO2 level thresholds and colors
CO2_LEVELS = {
    'excellent': {'max': 800, 'color': '#22c55e', 'label': 'Отлично'},
    'good': {'max': 1000, 'color': '#eab308', 'label': 'Хорошо'},
    'moderate': {'max': 1500, 'color': '#f97316', 'label': 'Проветрить'},
    'bad': {'max': float('inf'), 'color': '#ef4444', 'label': 'Критично'},
}


def get_co2_color(co2: int) -> str:
    """Get color for CO2 level."""
    if co2 < 800:
        return CO2_LEVELS['excellent']['color']
    elif co2 < 1000:
        return CO2_LEVELS['good']['color']
    elif co2 < 1500:
        return CO2_LEVELS['moderate']['color']
    return CO2_LEVELS['bad']['color']


def generate_daily_chart(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """
    Generate daily CO2 chart (24 hours).

    Args:
        data: List of dicts with 'timestamp', 'co2', 'temperature', 'humidity'
        device_name: Name of the device for title
        timezone: User's timezone for display

    Returns:
        BytesIO buffer with PNG image
    """
    if not data:
        return _generate_empty_chart("Нет данных за последние 24 часа")

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    # Parse data
    times = []
    co2_values = []
    temp_values = []
    humidity_values = []

    for d in data:
        dt = d['timestamp']
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local_dt = dt.astimezone(tz)

        times.append(local_dt)
        co2_values.append(d['co2'])
        temp_values.append(d.get('temperature', 0))
        humidity_values.append(d.get('humidity', 0))

    # Create figure with subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1])
    fig.suptitle(f'📊 {device_name} — последние 24 часа', fontsize=14, fontweight='bold')

    # CO2 Chart (main)
    ax1.set_ylabel('CO2 (ppm)', fontsize=11)

    # Fill areas by CO2 level
    ax1.axhspan(0, 800, alpha=0.1, color=CO2_LEVELS['excellent']['color'], label='Отлично')
    ax1.axhspan(800, 1000, alpha=0.1, color=CO2_LEVELS['good']['color'], label='Хорошо')
    ax1.axhspan(1000, 1500, alpha=0.1, color=CO2_LEVELS['moderate']['color'], label='Проветрить')
    ax1.axhspan(1500, max(co2_values) + 200 if co2_values else 2000, alpha=0.1, color=CO2_LEVELS['bad']['color'], label='Критично')

    # Plot CO2 line with gradient color
    colors = [get_co2_color(c) for c in co2_values]
    for i in range(len(times) - 1):
        ax1.plot(times[i:i+2], co2_values[i:i+2], color=colors[i], linewidth=2)

    # Add threshold lines
    ax1.axhline(y=800, color=CO2_LEVELS['good']['color'], linestyle='--', alpha=0.7, linewidth=1)
    ax1.axhline(y=1000, color=CO2_LEVELS['moderate']['color'], linestyle='--', alpha=0.7, linewidth=1)
    ax1.axhline(y=1500, color=CO2_LEVELS['bad']['color'], linestyle='--', alpha=0.7, linewidth=1)

    ax1.set_ylim(min(300, min(co2_values) - 50) if co2_values else 300,
                 max(1800, max(co2_values) + 100) if co2_values else 1800)
    ax1.legend(loc='upper right', fontsize=9)

    # Temperature & Humidity Chart
    ax2_temp = ax2
    ax2_hum = ax2.twinx()

    line1, = ax2_temp.plot(times, temp_values, color='#3b82f6', linewidth=2, label='Температура')
    ax2_temp.set_ylabel('Температура (°C)', color='#3b82f6', fontsize=10)
    ax2_temp.tick_params(axis='y', labelcolor='#3b82f6')

    line2, = ax2_hum.plot(times, humidity_values, color='#06b6d4', linewidth=2, linestyle='--', label='Влажность')
    ax2_hum.set_ylabel('Влажность (%)', color='#06b6d4', fontsize=10)
    ax2_hum.tick_params(axis='y', labelcolor='#06b6d4')

    ax2.legend([line1, line2], ['Температура', 'Влажность'], loc='upper right', fontsize=9)

    # Format x-axis
    for ax in [ax1, ax2]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Add stats box
    if co2_values:
        avg_co2 = sum(co2_values) / len(co2_values)
        max_co2 = max(co2_values)
        min_co2 = min(co2_values)

        stats_text = f'Средний: {avg_co2:.0f} ppm | Макс: {max_co2} ppm | Мин: {min_co2} ppm'
        fig.text(0.5, 0.01, stats_text, ha='center', fontsize=10,
                 bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])

    # Save to buffer
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_morning_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """
    Generate morning report chart (night data 22:00 - 08:00).
    Shows sleep quality based on CO2 levels.
    """
    if not data:
        return _generate_empty_chart("Нет ночных данных")

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    # Filter night hours (22:00 - 08:00)
    night_data = []
    for d in data:
        dt = d['timestamp']
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local_dt = dt.astimezone(tz)
        hour = local_dt.hour

        if hour >= 22 or hour < 8:
            night_data.append({**d, 'local_time': local_dt})

    if not night_data:
        return _generate_empty_chart("Нет данных за ночь (22:00-08:00)")

    times = [d['local_time'] for d in night_data]
    co2_values = [d['co2'] for d in night_data]

    # Calculate sleep quality
    avg_co2 = sum(co2_values) / len(co2_values)
    time_above_1000 = sum(1 for c in co2_values if c > 1000) / len(co2_values) * 100

    if avg_co2 < 800 and time_above_1000 < 10:
        quality = "Отлично 🌟"
        quality_color = CO2_LEVELS['excellent']['color']
    elif avg_co2 < 1000 and time_above_1000 < 30:
        quality = "Хорошо 😊"
        quality_color = CO2_LEVELS['good']['color']
    elif avg_co2 < 1200:
        quality = "Удовлетворительно 😐"
        quality_color = CO2_LEVELS['moderate']['color']
    else:
        quality = "Плохо 😟"
        quality_color = CO2_LEVELS['bad']['color']

    # Create chart
    fig, ax = plt.subplots(figsize=(10, 6))

    # Fill background zones
    ax.axhspan(0, 800, alpha=0.15, color=CO2_LEVELS['excellent']['color'])
    ax.axhspan(800, 1000, alpha=0.15, color=CO2_LEVELS['good']['color'])
    ax.axhspan(1000, 1500, alpha=0.15, color=CO2_LEVELS['moderate']['color'])
    ax.axhspan(1500, max(co2_values) + 200 if co2_values else 2000, alpha=0.15, color=CO2_LEVELS['bad']['color'])

    # Plot line
    colors = [get_co2_color(c) for c in co2_values]
    for i in range(len(times) - 1):
        ax.plot(times[i:i+2], co2_values[i:i+2], color=colors[i], linewidth=2.5)

    # Add fill under curve
    ax.fill_between(times, co2_values, alpha=0.2, color='#6366f1')

    # Threshold lines
    ax.axhline(y=800, color=CO2_LEVELS['good']['color'], linestyle='--', alpha=0.5)
    ax.axhline(y=1000, color=CO2_LEVELS['moderate']['color'], linestyle='--', alpha=0.5)

    ax.set_ylabel('CO2 (ppm)', fontsize=11)
    ax.set_title(f'🌙 Ночной отчёт — {device_name}', fontsize=14, fontweight='bold', pad=20)

    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    ax.set_ylim(min(350, min(co2_values) - 50), max(1600, max(co2_values) + 100))

    # Add quality box
    props = dict(boxstyle='round,pad=0.5', facecolor=quality_color, alpha=0.3, edgecolor=quality_color)
    textstr = f'Качество сна: {quality}\nСредний CO2: {avg_co2:.0f} ppm\nВремя >1000 ppm: {time_above_1000:.0f}%'
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props)

    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_evening_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """
    Generate evening report chart (daytime data 08:00 - 22:00).
    Shows daily air quality summary.
    """
    if not data:
        return _generate_empty_chart("Нет дневных данных")

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    # Filter day hours (08:00 - 22:00)
    day_data = []
    for d in data:
        dt = d['timestamp']
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local_dt = dt.astimezone(tz)
        hour = local_dt.hour

        if 8 <= hour < 22:
            day_data.append({**d, 'local_time': local_dt})

    if not day_data:
        return _generate_empty_chart("Нет данных за день (08:00-22:00)")

    times = [d['local_time'] for d in day_data]
    co2_values = [d['co2'] for d in day_data]
    temp_values = [d.get('temperature', 0) for d in day_data]
    humidity_values = [d.get('humidity', 0) for d in day_data]

    # Stats
    avg_co2 = sum(co2_values) / len(co2_values)
    max_co2 = max(co2_values)
    min_co2 = min(co2_values)
    avg_temp = sum(temp_values) / len(temp_values) if temp_values else 0
    avg_humidity = sum(humidity_values) / len(humidity_values) if humidity_values else 0

    # Create figure
    fig = plt.figure(figsize=(12, 8))
    gs = fig.add_gridspec(2, 2, height_ratios=[2, 1], hspace=0.3, wspace=0.3)

    # Main CO2 chart
    ax1 = fig.add_subplot(gs[0, :])

    ax1.axhspan(0, 800, alpha=0.1, color=CO2_LEVELS['excellent']['color'])
    ax1.axhspan(800, 1000, alpha=0.1, color=CO2_LEVELS['good']['color'])
    ax1.axhspan(1000, 1500, alpha=0.1, color=CO2_LEVELS['moderate']['color'])
    ax1.axhspan(1500, max(co2_values) + 200, alpha=0.1, color=CO2_LEVELS['bad']['color'])

    colors = [get_co2_color(c) for c in co2_values]
    for i in range(len(times) - 1):
        ax1.plot(times[i:i+2], co2_values[i:i+2], color=colors[i], linewidth=2)

    ax1.fill_between(times, co2_values, alpha=0.15, color='#8b5cf6')
    ax1.axhline(y=1000, color=CO2_LEVELS['moderate']['color'], linestyle='--', alpha=0.5)

    ax1.set_ylabel('CO2 (ppm)')
    ax1.set_title(f'☀️ Дневной отчёт — {device_name}', fontsize=14, fontweight='bold')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Temperature mini-chart
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(times, temp_values, color='#f59e0b', linewidth=2)
    ax2.fill_between(times, temp_values, alpha=0.2, color='#f59e0b')
    ax2.set_ylabel('°C')
    ax2.set_title(f'🌡️ Температура (ср. {avg_temp:.1f}°C)', fontsize=11)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

    # Humidity mini-chart
    ax3 = fig.add_subplot(gs[1, 1])
    ax3.plot(times, humidity_values, color='#0ea5e9', linewidth=2)
    ax3.fill_between(times, humidity_values, alpha=0.2, color='#0ea5e9')
    ax3.set_ylabel('%')
    ax3.set_title(f'💧 Влажность (ср. {avg_humidity:.0f}%)', fontsize=11)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

    # Stats summary
    stats = f'CO2: ср. {avg_co2:.0f} | макс {max_co2} | мин {min_co2} ppm'
    fig.text(0.5, 0.01, stats, ha='center', fontsize=10,
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_weekly_summary(
    daily_stats: list[dict],
    device_name: str
) -> BytesIO:
    """
    Generate weekly summary chart.

    Args:
        daily_stats: List of dicts with 'date', 'avg_co2', 'max_co2', 'min_co2'
    """
    if not daily_stats:
        return _generate_empty_chart("Нет данных за неделю")

    fig, ax = plt.subplots(figsize=(10, 6))

    dates = [d['date'] for d in daily_stats]
    avg_co2 = [d['avg_co2'] for d in daily_stats]
    max_co2 = [d['max_co2'] for d in daily_stats]
    min_co2 = [d['min_co2'] for d in daily_stats]

    x = range(len(dates))
    width = 0.25

    # Bars
    bars1 = ax.bar([i - width for i in x], min_co2, width, label='Минимум', color='#22c55e', alpha=0.8)
    bars2 = ax.bar(x, avg_co2, width, label='Среднее', color='#3b82f6', alpha=0.8)
    bars3 = ax.bar([i + width for i in x], max_co2, width, label='Максимум', color='#ef4444', alpha=0.8)

    # Threshold line
    ax.axhline(y=1000, color='#f97316', linestyle='--', label='Порог (1000 ppm)')

    ax.set_ylabel('CO2 (ppm)')
    ax.set_title(f'📅 Недельная статистика — {device_name}', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([d.strftime('%d.%m') if isinstance(d, datetime) else d for d in dates])
    ax.legend()

    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def _generate_empty_chart(message: str) -> BytesIO:
    """Generate a simple chart with 'no data' message."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, message, ha='center', va='center', fontsize=14, color='gray')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf

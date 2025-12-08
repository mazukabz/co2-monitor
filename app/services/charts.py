"""
Charts Service - generates infographics for CO2 monitoring
Uses matplotlib for server-side PNG generation
Apple-inspired design: clean, minimal, with subtle gradients
"""

import matplotlib
matplotlib.use('Agg')  # Headless mode - must be before pyplot import

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional
from zoneinfo import ZoneInfo

# Apple-inspired color palette
COLORS = {
    'bg_dark': '#1C1C1E',        # Dark background
    'bg_card': '#2C2C2E',        # Card background
    'text_primary': '#FFFFFF',   # Primary text
    'text_secondary': '#8E8E93', # Secondary text
    'accent_green': '#30D158',   # Excellent - Apple green
    'accent_yellow': '#FFD60A',  # Good - Apple yellow
    'accent_orange': '#FF9F0A',  # Moderate - Apple orange
    'accent_red': '#FF453A',     # Bad - Apple red
    'accent_blue': '#0A84FF',    # Info - Apple blue
    'accent_cyan': '#64D2FF',    # Secondary info
    'accent_purple': '#BF5AF2',  # Highlight
    'grid': '#3A3A3C',           # Grid lines
}

# CO2 level thresholds and colors (Apple style)
CO2_LEVELS = {
    'excellent': {'max': 800, 'color': COLORS['accent_green'], 'label': 'Отлично'},
    'good': {'max': 1000, 'color': COLORS['accent_yellow'], 'label': 'Хорошо'},
    'moderate': {'max': 1500, 'color': COLORS['accent_orange'], 'label': 'Проветрить'},
    'bad': {'max': float('inf'), 'color': COLORS['accent_red'], 'label': 'Критично'},
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
    Generate Apple-style morning report (night data 22:00 - 08:00).
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
    temp_values = [d.get('temperature', 0) for d in night_data]
    humidity_values = [d.get('humidity', 0) for d in night_data]

    # Calculate stats
    avg_co2 = sum(co2_values) / len(co2_values)
    max_co2 = max(co2_values)
    min_co2 = min(co2_values)
    avg_temp = sum(temp_values) / len(temp_values) if temp_values else 0
    avg_humidity = sum(humidity_values) / len(humidity_values) if humidity_values else 0
    time_above_1000 = sum(1 for c in co2_values if c > 1000) / len(co2_values) * 100

    # Sleep quality assessment
    if avg_co2 < 800 and time_above_1000 < 10:
        quality = "Отлично"
        quality_emoji = "🌟"
        quality_color = COLORS['accent_green']
    elif avg_co2 < 1000 and time_above_1000 < 30:
        quality = "Хорошо"
        quality_emoji = "😊"
        quality_color = COLORS['accent_yellow']
    elif avg_co2 < 1200:
        quality = "Удовлетворительно"
        quality_emoji = "😐"
        quality_color = COLORS['accent_orange']
    else:
        quality = "Плохо"
        quality_emoji = "😟"
        quality_color = COLORS['accent_red']

    # Smooth data for chart
    chart_times, chart_co2 = _resample_data(times, co2_values, 80)
    chart_co2 = _smooth_data(chart_co2, 5)

    # === CREATE FIGURE ===
    fig = plt.figure(figsize=(12, 12), facecolor=COLORS['bg_dark'])
    gs = fig.add_gridspec(4, 3, height_ratios=[1.0, 2.0, 0.8, 1.0],
                          hspace=0.2, wspace=0.2,
                          left=0.05, right=0.95, top=0.95, bottom=0.05)

    # === HEADER ===
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor(COLORS['bg_dark'])
    ax_header.axis('off')

    ax_header.text(0.0, 0.85, f"🌙 Ночной отчёт", fontsize=24, fontweight='bold',
                   color=COLORS['text_primary'], transform=ax_header.transAxes)
    ax_header.text(0.0, 0.55, device_name, fontsize=18,
                   color=COLORS['text_secondary'], transform=ax_header.transAxes)

    # Quality badge
    ax_header.text(0.0, 0.15, f"Качество сна: {quality} {quality_emoji}", fontsize=20, fontweight='bold',
                   color=quality_color, transform=ax_header.transAxes)

    ax_header.text(0.98, 0.5, times[-1].strftime('%d.%m.%Y'),
                   fontsize=16, color=COLORS['text_secondary'],
                   ha='right', va='center', transform=ax_header.transAxes)

    # === MAIN CHART ===
    ax_main = fig.add_subplot(gs[1, :])
    ax_main.set_facecolor(COLORS['bg_dark'])
    for spine in ax_main.spines.values():
        spine.set_visible(False)

    ax_main.yaxis.grid(True, color=COLORS['grid'], alpha=0.2, linewidth=0.5)
    ax_main.xaxis.grid(False)
    ax_main.tick_params(colors=COLORS['text_secondary'], labelsize=12)

    y_min = min(350, min_co2 - 30)
    y_max = max(1600, max_co2 + 50)
    ax_main.set_ylim(y_min, y_max)
    ax_main.set_xlim(chart_times[0], chart_times[-1])

    # Multi-color gradient fill
    segment_colors = [get_co2_color(int(c)) for c in chart_co2]
    n_strips = 40
    y_arr = np.array(chart_co2)

    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        seg_times = chart_times[seg_idx:seg_idx + 2]
        seg_y = y_arr[seg_idx:seg_idx + 2]

        for i in range(n_strips):
            frac = i / n_strips
            alpha = 0.45 * (1 - frac) ** 2.5
            strip_top = y_min + (seg_y - y_min) * (1 - frac)
            strip_bot = y_min + (seg_y - y_min) * (1 - (i + 1) / n_strips)
            ax_main.fill_between(seg_times, strip_bot, strip_top, color=seg_color,
                                 alpha=alpha, linewidth=0, zorder=1)

    # Main line
    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        ax_main.plot(chart_times[seg_idx:seg_idx + 2], chart_co2[seg_idx:seg_idx + 2],
                     color=seg_color, linewidth=3, zorder=2, solid_capstyle='round')

    # Threshold lines
    for thresh in [800, 1000]:
        if y_min < thresh < y_max:
            ax_main.axhline(y=thresh, color=COLORS['grid'], linestyle='--', alpha=0.4)

    ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax_main.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax_main.yaxis.tick_right()

    # === STATS CARDS ===
    stats_data = [
        ('Средний', f'{avg_co2:.0f}', 'ppm', get_co2_color(int(avg_co2))),
        ('Время >1000', f'{time_above_1000:.0f}', '%', COLORS['accent_orange'] if time_above_1000 > 20 else COLORS['text_primary']),
        ('Замеров', f'{len(co2_values)}', '', COLORS['text_primary']),
    ]

    for i, (label, value, unit, color) in enumerate(stats_data):
        ax = fig.add_subplot(gs[2, i])
        ax.set_facecolor(COLORS['bg_dark'])
        ax.axis('off')

        rect = mpatches.FancyBboxPatch((0.05, 0.1), 0.9, 0.8,
                                        boxstyle="round,pad=0.02,rounding_size=0.15",
                                        facecolor=COLORS['bg_card'],
                                        edgecolor=COLORS['grid'], linewidth=0.5,
                                        transform=ax.transAxes)
        ax.add_patch(rect)

        ax.text(0.5, 0.78, label, fontsize=13, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.42, value, fontsize=32, fontweight='bold', color=color,
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.15, unit, fontsize=13, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)

    # === BOTTOM STATS ===
    ax_bottom = fig.add_subplot(gs[3, :])
    ax_bottom.set_facecolor(COLORS['bg_dark'])
    ax_bottom.axis('off')
    ax_bottom.axhline(y=0.9, xmin=0.02, xmax=0.98, color=COLORS['grid'], linewidth=0.5)

    bottom_stats = [
        ('🌡️ Температура', f'{avg_temp:.1f}°C'),
        ('💧 Влажность', f'{avg_humidity:.0f}%'),
        ('🕐 Период', f'{times[0].strftime("%H:%M")} – {times[-1].strftime("%H:%M")}'),
    ]

    for i, (label, value) in enumerate(bottom_stats):
        x_pos = 0.02 + i * 0.33
        ax_bottom.text(x_pos, 0.5, label, fontsize=14, color=COLORS['text_secondary'],
                       ha='left', transform=ax_bottom.transAxes)
        ax_bottom.text(x_pos + 0.28, 0.5, value, fontsize=14, color=COLORS['text_primary'],
                       ha='right', transform=ax_bottom.transAxes, fontweight='bold')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS['bg_dark'], edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_evening_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """
    Generate Apple-style evening report (daytime data 08:00 - 22:00).
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
    temp_min, temp_max = min(temp_values), max(temp_values)
    hum_min, hum_max = min(humidity_values), max(humidity_values)

    # Time in zones
    n = len(co2_values)
    time_excellent = sum(1 for c in co2_values if c < 800) / n * 100
    time_good = sum(1 for c in co2_values if 800 <= c < 1000) / n * 100
    time_moderate = sum(1 for c in co2_values if 1000 <= c < 1500) / n * 100
    time_bad = sum(1 for c in co2_values if c >= 1500) / n * 100

    # Quality color
    if avg_co2 < 800:
        quality_color = COLORS['accent_green']
    elif avg_co2 < 1000:
        quality_color = COLORS['accent_yellow']
    elif avg_co2 < 1500:
        quality_color = COLORS['accent_orange']
    else:
        quality_color = COLORS['accent_red']

    # Smooth data
    chart_times, chart_co2 = _resample_data(times, co2_values, 100)
    chart_co2 = _smooth_data(chart_co2, 7)

    # === CREATE FIGURE ===
    fig = plt.figure(figsize=(12, 14), facecolor=COLORS['bg_dark'])
    gs = fig.add_gridspec(4, 3, height_ratios=[1.0, 2.5, 1.0, 1.2],
                          hspace=0.2, wspace=0.2,
                          left=0.05, right=0.95, top=0.95, bottom=0.05)

    # === HEADER ===
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor(COLORS['bg_dark'])
    ax_header.axis('off')

    ax_header.text(0.0, 0.8, f"☀️ Дневной отчёт", fontsize=24, fontweight='bold',
                   color=COLORS['text_primary'], transform=ax_header.transAxes)
    ax_header.text(0.0, 0.45, device_name, fontsize=18,
                   color=COLORS['text_secondary'], transform=ax_header.transAxes)
    ax_header.text(0.0, 0.1, f"Средний CO2: {avg_co2:.0f} ppm", fontsize=20, fontweight='bold',
                   color=quality_color, transform=ax_header.transAxes)
    ax_header.text(0.98, 0.5, times[-1].strftime('%d.%m.%Y'),
                   fontsize=16, color=COLORS['text_secondary'],
                   ha='right', va='center', transform=ax_header.transAxes)

    # === MAIN CHART ===
    ax_main = fig.add_subplot(gs[1, :])
    ax_main.set_facecolor(COLORS['bg_dark'])
    for spine in ax_main.spines.values():
        spine.set_visible(False)

    ax_main.yaxis.grid(True, color=COLORS['grid'], alpha=0.2, linewidth=0.5)
    ax_main.tick_params(colors=COLORS['text_secondary'], labelsize=12)

    y_min = min(350, min_co2 - 30)
    y_max = max(1600, max_co2 + 50)
    ax_main.set_ylim(y_min, y_max)
    ax_main.set_xlim(chart_times[0], chart_times[-1])

    # Multi-color gradient fill
    segment_colors = [get_co2_color(int(c)) for c in chart_co2]
    n_strips = 40
    y_arr = np.array(chart_co2)

    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        seg_times = chart_times[seg_idx:seg_idx + 2]
        seg_y = y_arr[seg_idx:seg_idx + 2]

        for i in range(n_strips):
            frac = i / n_strips
            alpha = 0.45 * (1 - frac) ** 2.5
            strip_top = y_min + (seg_y - y_min) * (1 - frac)
            strip_bot = y_min + (seg_y - y_min) * (1 - (i + 1) / n_strips)
            ax_main.fill_between(seg_times, strip_bot, strip_top, color=seg_color,
                                 alpha=alpha, linewidth=0, zorder=1)

    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        ax_main.plot(chart_times[seg_idx:seg_idx + 2], chart_co2[seg_idx:seg_idx + 2],
                     color=seg_color, linewidth=3, zorder=2, solid_capstyle='round')

    for thresh in [800, 1000, 1500]:
        if y_min < thresh < y_max:
            ax_main.axhline(y=thresh, color=COLORS['grid'], linestyle='--', alpha=0.4)

    ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax_main.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax_main.yaxis.tick_right()

    # === STATS CARDS ===
    stats_data = [
        ('Средний', f'{avg_co2:.0f}', 'ppm', get_co2_color(int(avg_co2))),
        ('Максимум', f'{max_co2}', 'ppm', COLORS['accent_red'] if max_co2 > 1000 else COLORS['text_primary']),
        ('Минимум', f'{min_co2}', 'ppm', COLORS['accent_green'] if min_co2 < 800 else COLORS['text_primary']),
    ]

    for i, (label, value, unit, color) in enumerate(stats_data):
        ax = fig.add_subplot(gs[2, i])
        ax.set_facecolor(COLORS['bg_dark'])
        ax.axis('off')

        rect = mpatches.FancyBboxPatch((0.05, 0.1), 0.9, 0.8,
                                        boxstyle="round,pad=0.02,rounding_size=0.15",
                                        facecolor=COLORS['bg_card'],
                                        edgecolor=COLORS['grid'], linewidth=0.5,
                                        transform=ax.transAxes)
        ax.add_patch(rect)

        ax.text(0.5, 0.78, label, fontsize=14, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.42, value, fontsize=36, fontweight='bold', color=color,
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.15, unit, fontsize=14, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)

    # === BOTTOM STATS ===
    ax_bottom = fig.add_subplot(gs[3, :])
    ax_bottom.set_facecolor(COLORS['bg_dark'])
    ax_bottom.axis('off')
    ax_bottom.axhline(y=0.95, xmin=0.02, xmax=0.98, color=COLORS['grid'], linewidth=0.5)

    left_stats = [
        ('🌡️ Температура', f'{avg_temp:.1f}°C ({temp_min:.1f}° – {temp_max:.1f}°)'),
        ('💧 Влажность', f'{avg_humidity:.0f}% ({hum_min:.0f}% – {hum_max:.0f}%)'),
    ]

    right_stats = [
        ('📊 Замеров', f'{n}'),
        ('🕐 Период', f'{times[0].strftime("%H:%M")} – {times[-1].strftime("%H:%M")}'),
    ]

    for i, (label, value) in enumerate(left_stats):
        y_pos = 0.72 - i * 0.35
        ax_bottom.text(0.02, y_pos, label, fontsize=15, color=COLORS['text_secondary'],
                       ha='left', transform=ax_bottom.transAxes)
        ax_bottom.text(0.45, y_pos, value, fontsize=15, color=COLORS['text_primary'],
                       ha='right', transform=ax_bottom.transAxes, fontweight='bold')

    for i, (label, value) in enumerate(right_stats):
        y_pos = 0.72 - i * 0.35
        ax_bottom.text(0.52, y_pos, label, fontsize=15, color=COLORS['text_secondary'],
                       ha='left', transform=ax_bottom.transAxes)
        ax_bottom.text(0.98, y_pos, value, fontsize=15, color=COLORS['text_primary'],
                       ha='right', transform=ax_bottom.transAxes, fontweight='bold')

    # Quality zones
    ax_bottom.axhline(y=0.12, xmin=0.02, xmax=0.98, color=COLORS['grid'], linewidth=0.5)

    zone_items = [
        (COLORS['accent_green'], f'<800: {time_excellent:.0f}%'),
        (COLORS['accent_yellow'], f'800-1000: {time_good:.0f}%'),
        (COLORS['accent_orange'], f'1000-1500: {time_moderate:.0f}%'),
        (COLORS['accent_red'], f'>1500: {time_bad:.0f}%'),
    ]

    for i, (color, text) in enumerate(zone_items):
        x_pos = 0.05 + i * 0.24
        ax_bottom.plot(x_pos, 0.02, 'o', color=color, markersize=12, transform=ax_bottom.transAxes)
        ax_bottom.text(x_pos + 0.025, 0.02, text, fontsize=13, color=COLORS['text_primary'],
                       va='center', transform=ax_bottom.transAxes, fontweight='bold')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS['bg_dark'], edgecolor='none')
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


def _setup_dark_style(ax, show_grid=True):
    """Apply Apple-style dark theme to axis."""
    ax.set_facecolor(COLORS['bg_card'])
    ax.tick_params(colors=COLORS['text_secondary'], labelsize=9)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color(COLORS['grid'])
    ax.spines['left'].set_color(COLORS['grid'])
    if show_grid:
        ax.grid(True, color=COLORS['grid'], alpha=0.3, linestyle='-', linewidth=0.5)
    ax.set_axisbelow(True)


def _draw_gradient_line(ax, x, y, colors_list, linewidth=2.5):
    """Draw a line with gradient colors based on values."""
    points = np.array([mdates.date2num(x), y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    lc = LineCollection(segments, colors=colors_list[:-1], linewidths=linewidth, capstyle='round')
    ax.add_collection(lc)
    return lc


def _create_ring_chart(ax, percentages, colors_list, labels):
    """Create Apple-style ring/donut chart."""
    ax.set_facecolor(COLORS['bg_card'])

    # Filter out zero values
    filtered = [(p, c, l) for p, c, l in zip(percentages, colors_list, labels) if p > 0]
    if not filtered:
        ax.text(0.5, 0.5, 'Нет данных', ha='center', va='center',
                color=COLORS['text_secondary'], fontsize=12)
        ax.axis('off')
        return

    sizes, cols, lbls = zip(*filtered)

    # Create donut chart
    wedges, texts, autotexts = ax.pie(
        sizes,
        colors=cols,
        autopct=lambda p: f'{p:.0f}%' if p > 5 else '',
        startangle=90,
        pctdistance=0.75,
        wedgeprops=dict(width=0.5, edgecolor=COLORS['bg_card'], linewidth=2)
    )

    for autotext in autotexts:
        autotext.set_color(COLORS['text_primary'])
        autotext.set_fontsize(10)
        autotext.set_fontweight('bold')

    ax.axis('equal')


def _create_gradient_fill(ax, times, values, color, alpha_top=0.4, alpha_bottom=0.0):
    """Create Apple Stocks-style gradient fill under the line."""
    # Convert to arrays
    x = mdates.date2num(times)
    y = np.array(values)

    # Create polygon vertices for fill
    verts = [(x[0], ax.get_ylim()[0])] + list(zip(x, y)) + [(x[-1], ax.get_ylim()[0])]

    from matplotlib.patches import Polygon
    from matplotlib.colors import LinearSegmentedColormap

    # Create vertical gradient
    poly = Polygon(verts, facecolor='none', edgecolor='none')
    ax.add_patch(poly)

    # Create gradient using imshow
    y_min, y_max = ax.get_ylim()
    gradient = np.linspace(0, 1, 256).reshape(-1, 1)

    # Custom colormap: color at top → transparent at bottom
    colors_rgba = []
    import matplotlib.colors as mcolors
    rgb = mcolors.to_rgb(color)
    for i in range(256):
        alpha = alpha_top * (1 - i / 255) ** 1.5  # Smooth gradient
        colors_rgba.append((*rgb, alpha))

    cmap = LinearSegmentedColormap.from_list('gradient', colors_rgba)

    # Fill area under curve
    ax.fill_between(times, values, y_min, color=color, alpha=0.0)  # Placeholder

    # Manual gradient fill using multiple fills
    n_strips = 50
    y_vals = np.array(values)
    for i in range(n_strips):
        alpha = alpha_top * (1 - i / n_strips) ** 2
        strip_height = (y_vals - y_min) * (n_strips - i) / n_strips + y_min
        strip_height_next = (y_vals - y_min) * (n_strips - i - 1) / n_strips + y_min
        ax.fill_between(times, strip_height_next, strip_height, color=color, alpha=alpha / n_strips * 3, linewidth=0)


def _smooth_data(values: list, window: int = 5) -> list:
    """Apply moving average smoothing to data."""
    if len(values) <= window:
        return values

    smoothed = []
    half_window = window // 2

    for i in range(len(values)):
        start = max(0, i - half_window)
        end = min(len(values), i + half_window + 1)
        smoothed.append(sum(values[start:end]) / (end - start))

    return smoothed


def _resample_data(times: list, values: list, target_points: int = 100) -> tuple:
    """Resample data to target number of points for smoother visualization."""
    if len(times) <= target_points:
        return times, values

    step = len(times) // target_points
    if step < 2:
        return times, values

    resampled_times = []
    resampled_values = []

    for i in range(0, len(times), step):
        chunk_end = min(i + step, len(times))
        chunk_values = values[i:chunk_end]

        # Use middle time point and average value
        mid_idx = i + len(chunk_values) // 2
        if mid_idx < len(times):
            resampled_times.append(times[mid_idx])
            resampled_values.append(sum(chunk_values) / len(chunk_values))

    return resampled_times, resampled_values


def generate_period_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow",
    period_hours: int = 24,
    period_label: str = "24 часа"
) -> BytesIO:
    """
    Generate Apple Stocks-style report for any period.
    Clean dark theme with gradient fills and smoothed data.

    Args:
        data: List of telemetry data points
        device_name: Name of the device
        timezone: User's timezone
        period_hours: Period in hours (1, 6, 12, 24, 168 for 7 days, 720 for 30 days)
        period_label: Human-readable period label
    """
    if not data:
        return _generate_empty_chart(f"Нет данных за {period_label}")

    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")

    # Parse all data
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

    # Calculate statistics from raw data
    avg_co2 = sum(co2_values) / len(co2_values)
    max_co2 = max(co2_values)
    min_co2 = min(co2_values)
    current_co2 = co2_values[-1]
    avg_temp = sum(temp_values) / len(temp_values) if temp_values else 0
    avg_humidity = sum(humidity_values) / len(humidity_values) if humidity_values else 0
    temp_min, temp_max = min(temp_values), max(temp_values)
    hum_min, hum_max = min(humidity_values), max(humidity_values)

    # Time in zones (from raw data)
    n = len(co2_values)
    time_excellent = sum(1 for c in co2_values if c < 800) / n * 100
    time_good = sum(1 for c in co2_values if 800 <= c < 1000) / n * 100
    time_moderate = sum(1 for c in co2_values if 1000 <= c < 1500) / n * 100
    time_bad = sum(1 for c in co2_values if c >= 1500) / n * 100

    # Determine target points based on period
    if period_hours <= 1:
        target_points = min(60, len(times))
        smooth_window = 3
    elif period_hours <= 6:
        target_points = min(80, len(times))
        smooth_window = 5
    elif period_hours <= 24:
        target_points = min(100, len(times))
        smooth_window = 7
    elif period_hours <= 168:  # 7 days
        target_points = min(120, len(times))
        smooth_window = 11
    else:  # 30 days
        target_points = min(150, len(times))
        smooth_window = 15

    # Resample and smooth data for chart
    chart_times, chart_co2 = _resample_data(times, co2_values, target_points)
    chart_co2 = _smooth_data(chart_co2, smooth_window)

    # Determine quality and main color
    if avg_co2 < 800:
        quality_color = COLORS['accent_green']
    elif avg_co2 < 1000:
        quality_color = COLORS['accent_yellow']
    elif avg_co2 < 1500:
        quality_color = COLORS['accent_orange']
    else:
        quality_color = COLORS['accent_red']

    # Change indicator
    co2_change = current_co2 - co2_values[0]
    change_sign = '+' if co2_change >= 0 else ''
    change_color = COLORS['accent_red'] if co2_change > 0 else COLORS['accent_green']

    # === CREATE FIGURE ===
    fig = plt.figure(figsize=(12, 14), facecolor=COLORS['bg_dark'])

    # Simplified layout: Header, Chart, Stats
    gs = fig.add_gridspec(4, 3, height_ratios=[1.0, 2.5, 1.0, 1.2],
                          hspace=0.2, wspace=0.2,
                          left=0.05, right=0.95, top=0.95, bottom=0.05)

    # === HEADER ===
    ax_header = fig.add_subplot(gs[0, :])
    ax_header.set_facecolor(COLORS['bg_dark'])
    ax_header.axis('off')

    # Device name
    ax_header.text(0.0, 0.8, device_name, fontsize=28, fontweight='bold',
                   color=COLORS['text_primary'], transform=ax_header.transAxes)

    # Current CO2 value (large)
    ax_header.text(0.0, 0.25, f'{current_co2}', fontsize=64, fontweight='bold',
                   color=quality_color, transform=ax_header.transAxes)

    # Change indicator
    ax_header.text(0.28, 0.35, f'{change_sign}{co2_change}', fontsize=24, fontweight='bold',
                   color=change_color, transform=ax_header.transAxes)

    # Units and period
    ax_header.text(0.0, 0.0, f'ppm  •  {period_label}', fontsize=16,
                   color=COLORS['text_secondary'], transform=ax_header.transAxes)

    # Date on right
    ax_header.text(0.98, 0.5, times[-1].strftime('%d.%m.%Y'),
                   fontsize=18, color=COLORS['text_secondary'],
                   ha='right', va='center', transform=ax_header.transAxes)

    # === MAIN CO2 CHART ===
    ax_main = fig.add_subplot(gs[1, :])
    ax_main.set_facecolor(COLORS['bg_dark'])

    # Remove all spines
    for spine in ax_main.spines.values():
        spine.set_visible(False)

    # Minimal grid
    ax_main.yaxis.grid(True, color=COLORS['grid'], alpha=0.2, linestyle='-', linewidth=0.5)
    ax_main.xaxis.grid(False)
    ax_main.tick_params(colors=COLORS['text_secondary'], labelsize=14)
    ax_main.tick_params(axis='x', length=0)
    ax_main.tick_params(axis='y', length=0)

    # Set limits before gradient fill
    y_min = min(350, min_co2 - 30)
    y_max = max(1600, max_co2 + 50)
    ax_main.set_ylim(y_min, y_max)
    ax_main.set_xlim(chart_times[0], chart_times[-1])

    # Get color for each point based on smoothed CO2 value
    segment_colors = [get_co2_color(int(c)) for c in chart_co2]

    # Draw multi-color gradient fill (Apple Stocks style)
    n_strips = 40
    y_arr = np.array(chart_co2)

    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        seg_times = chart_times[seg_idx:seg_idx + 2]
        seg_y = y_arr[seg_idx:seg_idx + 2]

        # Draw vertical gradient strips for this segment
        for i in range(n_strips):
            frac = i / n_strips
            alpha = 0.45 * (1 - frac) ** 2.5
            strip_top = y_min + (seg_y - y_min) * (1 - frac)
            strip_bot = y_min + (seg_y - y_min) * (1 - (i + 1) / n_strips)
            ax_main.fill_between(seg_times, strip_bot, strip_top, color=seg_color,
                                 alpha=alpha, linewidth=0, zorder=1)

    # Main line with multi-color segments (thicker, smoother)
    for seg_idx in range(len(chart_times) - 1):
        seg_color = segment_colors[seg_idx]
        ax_main.plot(chart_times[seg_idx:seg_idx + 2], chart_co2[seg_idx:seg_idx + 2],
                     color=seg_color, linewidth=3.5, zorder=2, solid_capstyle='round')

    # Subtle threshold lines with labels
    for thresh, label in [(800, '800'), (1000, '1000'), (1500, '1500')]:
        if y_min < thresh < y_max:
            ax_main.axhline(y=thresh, color=COLORS['grid'], linestyle='--', alpha=0.4, linewidth=1)

    # X-axis formatting based on period
    if period_hours <= 1:
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_main.xaxis.set_major_locator(mdates.MinuteLocator(interval=10))
    elif period_hours <= 6:
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_main.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    elif period_hours <= 24:
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_main.xaxis.set_major_locator(mdates.HourLocator(interval=4))
    elif period_hours <= 168:  # 7 days
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        ax_main.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    else:  # 30 days
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        ax_main.xaxis.set_major_locator(mdates.DayLocator(interval=5))

    plt.setp(ax_main.xaxis.get_majorticklabels(), ha='center')

    # Y-axis on right side (like Stocks app)
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position('right')

    # === STATS CARDS ===
    stats_data = [
        ('Средний', f'{avg_co2:.0f}', 'ppm', get_co2_color(int(avg_co2))),
        ('Максимум', f'{max_co2}', 'ppm', COLORS['accent_red'] if max_co2 > 1000 else COLORS['text_primary']),
        ('Минимум', f'{min_co2}', 'ppm', COLORS['accent_green'] if min_co2 < 800 else COLORS['text_primary']),
    ]

    for i, (label, value, unit, color) in enumerate(stats_data):
        ax = fig.add_subplot(gs[2, i])
        ax.set_facecolor(COLORS['bg_dark'])
        ax.axis('off')

        # Card background
        rect = mpatches.FancyBboxPatch((0.05, 0.1), 0.9, 0.8,
                                        boxstyle="round,pad=0.02,rounding_size=0.15",
                                        facecolor=COLORS['bg_card'],
                                        edgecolor=COLORS['grid'], linewidth=0.5,
                                        transform=ax.transAxes)
        ax.add_patch(rect)

        ax.text(0.5, 0.78, label, fontsize=14, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.42, value, fontsize=36, fontweight='bold', color=color,
                ha='center', transform=ax.transAxes)
        ax.text(0.5, 0.15, unit, fontsize=14, color=COLORS['text_secondary'],
                ha='center', transform=ax.transAxes)

    # === BOTTOM STATS ROW ===
    ax_bottom = fig.add_subplot(gs[3, :])
    ax_bottom.set_facecolor(COLORS['bg_dark'])
    ax_bottom.axis('off')

    # Draw separator line
    ax_bottom.axhline(y=0.95, xmin=0.02, xmax=0.98, color=COLORS['grid'], linewidth=0.5)

    # Stats in two columns with larger fonts
    left_stats = [
        ('🌡️ Температура', f'{avg_temp:.1f}°C ({temp_min:.1f}° – {temp_max:.1f}°)'),
        ('💧 Влажность', f'{avg_humidity:.0f}% ({hum_min:.0f}% – {hum_max:.0f}%)'),
    ]

    right_stats = [
        ('📊 Замеров', f'{n}'),
        ('🕐 Период', f'{times[0].strftime("%d.%m %H:%M")} – {times[-1].strftime("%H:%M")}'),
    ]

    for i, (label, value) in enumerate(left_stats):
        y_pos = 0.72 - i * 0.35
        ax_bottom.text(0.02, y_pos, label, fontsize=15, color=COLORS['text_secondary'],
                       ha='left', transform=ax_bottom.transAxes)
        ax_bottom.text(0.45, y_pos, value, fontsize=15, color=COLORS['text_primary'],
                       ha='right', transform=ax_bottom.transAxes, fontweight='bold')

    for i, (label, value) in enumerate(right_stats):
        y_pos = 0.72 - i * 0.35
        ax_bottom.text(0.52, y_pos, label, fontsize=15, color=COLORS['text_secondary'],
                       ha='left', transform=ax_bottom.transAxes)
        ax_bottom.text(0.98, y_pos, value, fontsize=15, color=COLORS['text_primary'],
                       ha='right', transform=ax_bottom.transAxes, fontweight='bold')

    # Quality zones legend at bottom
    ax_bottom.axhline(y=0.12, xmin=0.02, xmax=0.98, color=COLORS['grid'], linewidth=0.5)

    zone_items = [
        (COLORS['accent_green'], f'<800: {time_excellent:.0f}%'),
        (COLORS['accent_yellow'], f'800-1000: {time_good:.0f}%'),
        (COLORS['accent_orange'], f'1000-1500: {time_moderate:.0f}%'),
        (COLORS['accent_red'], f'>1500: {time_bad:.0f}%'),
    ]

    for i, (color, text) in enumerate(zone_items):
        x_pos = 0.05 + i * 0.24
        ax_bottom.plot(x_pos, 0.02, 'o', color=color, markersize=12, transform=ax_bottom.transAxes)
        ax_bottom.text(x_pos + 0.025, 0.02, text, fontsize=13, color=COLORS['text_primary'],
                       va='center', transform=ax_bottom.transAxes, fontweight='bold')

    # Save
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS['bg_dark'], edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf


def generate_24h_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """Generate 24-hour report (wrapper for backward compatibility)."""
    return generate_period_report(data, device_name, timezone, 24, "24 часа")


def _generate_empty_chart(message: str) -> BytesIO:
    """Generate Apple-style 'no data' chart."""
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=COLORS['bg_dark'])
    ax.set_facecolor(COLORS['bg_dark'])
    ax.text(0.5, 0.5, message, ha='center', va='center',
            fontsize=16, color=COLORS['text_secondary'], fontweight='bold')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                facecolor=COLORS['bg_dark'], edgecolor='none')
    buf.seek(0)
    plt.close(fig)

    return buf

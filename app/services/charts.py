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
from scipy.interpolate import make_interp_spline

# Apple-inspired color palette (pure black like Apple Stocks)
COLORS = {
    'bg_dark': '#000000',        # Pure black background
    'bg_card': '#1C1C1E',        # Card background
    'text_primary': '#FFFFFF',   # Primary text
    'text_secondary': '#8E8E93', # Secondary text
    'accent_green': '#34C759',   # Excellent - Apple green
    'accent_yellow': '#FFD60A',  # Good - Apple yellow
    'accent_orange': '#FF9F0A',  # Moderate - Apple orange
    'accent_red': '#FF3B30',     # Bad - Apple red
    'accent_blue': '#0A84FF',    # Info - Apple blue
    'accent_cyan': '#64D2FF',    # Secondary info
    'accent_purple': '#BF5AF2',  # Highlight
    'grid': '#38383A',           # Grid lines
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
    Generate morning report (night data 22:00 - 08:00).
    Uses unified generate_period_report with night hour filtering.
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
            night_data.append(d)

    if not night_data:
        return _generate_empty_chart("Нет данных за ночь (22:00-08:00)")

    return generate_period_report(
        data=night_data,
        device_name=device_name,
        timezone=timezone,
        period_hours=10,  # ~10 hours night
        period_label="22:00-08:00",
        report_type="morning"
    )


def generate_evening_report(
    data: list[dict],
    device_name: str,
    timezone: str = "Europe/Moscow"
) -> BytesIO:
    """
    Generate evening report (daytime data 08:00 - 22:00).
    Uses unified generate_period_report with day hour filtering.
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
            day_data.append(d)

    if not day_data:
        return _generate_empty_chart("Нет данных за день (08:00-22:00)")

    return generate_period_report(
        data=day_data,
        device_name=device_name,
        timezone=timezone,
        period_hours=14,  # ~14 hours day
        period_label="08:00-22:00",
        report_type="evening"
    )


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


def _aggregate_data(times: list, values: list, group_size: int) -> tuple:
    """
    Aggregate data by averaging groups of points.
    This reduces noise before spline interpolation.
    """
    if group_size <= 1 or len(times) < group_size * 2:
        return times, values

    agg_times = []
    agg_values = []

    for i in range(0, len(times) - group_size + 1, group_size):
        chunk_times = times[i:i + group_size]
        chunk_values = values[i:i + group_size]

        # Use middle time point
        mid_idx = len(chunk_times) // 2
        agg_times.append(chunk_times[mid_idx])
        agg_values.append(sum(chunk_values) / len(chunk_values))

    # Always include the last point for continuity
    if agg_times and agg_times[-1] != times[-1]:
        agg_times.append(times[-1])
        agg_values.append(values[-1])

    return agg_times, agg_values


def _spline_smooth(times: list, values: list, num_points: int = 100) -> tuple:
    """Create smooth spline interpolation for Apple Stocks-style curves."""
    if len(times) < 4:
        return times, values

    # Convert datetime to numeric for interpolation
    x_numeric = np.array([t.timestamp() for t in times])
    y_numeric = np.array(values)

    try:
        spline = make_interp_spline(x_numeric, y_numeric, k=3)
        x_smooth = np.linspace(x_numeric.min(), x_numeric.max(), num_points)
        y_smooth = spline(x_smooth)

        # Convert back to datetime
        x_datetime = [datetime.fromtimestamp(t, tz=times[0].tzinfo) for t in x_smooth]
        return x_datetime, y_smooth.tolist()
    except Exception:
        return times, values


def _smooth_for_period(times: list, values: list, period_hours: int) -> tuple:
    """
    Apply appropriate smoothing based on period.

    Smoothing rules:
    - 1 hour: aggregate every 2 points, 50 spline points
    - 6 hours: aggregate every 4 points, 80 spline points
    - 12-24 hours: aggregate every 6 points, 100 spline points
    - 7 days: aggregate every 12 points, 120 spline points
    - 30 days: aggregate every 24 points, 150 spline points
    """
    if len(times) < 4:
        return times, values

    # Determine aggregation and spline parameters based on period
    if period_hours <= 1:
        group_size = 2
        spline_points = 50
    elif period_hours <= 6:
        group_size = 4
        spline_points = 80
    elif period_hours <= 24:
        group_size = 6
        spline_points = 100
    elif period_hours <= 168:  # 7 days
        group_size = 12
        spline_points = 120
    else:  # 30 days
        group_size = 24
        spline_points = 150

    # Step 1: Aggregate to reduce noise
    agg_times, agg_values = _aggregate_data(times, values, group_size)

    # Step 2: Apply spline smoothing
    if len(agg_times) >= 4:
        return _spline_smooth(agg_times, agg_values, spline_points)
    else:
        return agg_times, agg_values


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
    period_label: str = "24 часа",
    report_type: str = "general",  # "general", "morning", "evening"
) -> BytesIO:
    """
    Generate Apple Stocks-style report for any period.
    Unified function for all report types with mobile-optimized fonts.

    Args:
        data: List of telemetry data points
        device_name: Name of the device
        timezone: User's timezone
        period_hours: Period in hours (1, 6, 12, 24, 168 for 7 days, 720 for 30 days)
        period_label: Human-readable period label
        report_type: Type of report for header styling
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
    time_above_1000 = sum(1 for c in co2_values if c > 1000) / n * 100

    # Quality color based on average
    quality_color = get_co2_color(int(avg_co2))

    # Change indicator
    co2_change = current_co2 - co2_values[0]
    change_sign = '+' if co2_change >= 0 else ''
    change_color = COLORS['accent_red'] if co2_change > 0 else COLORS['accent_green']

    # Sleep quality for morning report
    sleep_quality = None
    if report_type == "morning":
        if avg_co2 < 800 and time_above_1000 < 10:
            sleep_quality = ("Отлично", COLORS['accent_green'])
        elif avg_co2 < 1000 and time_above_1000 < 30:
            sleep_quality = ("Хорошо", COLORS['accent_yellow'])
        elif avg_co2 < 1200:
            sleep_quality = ("Удовлетворительно", COLORS['accent_orange'])
        else:
            sleep_quality = ("Плохо", COLORS['accent_red'])

    # Smooth data with period-appropriate smoothing for Apple Stocks-style curves
    chart_times, chart_co2 = _smooth_for_period(times, co2_values, period_hours)

    # === CREATE FIGURE - Apple style proportions ===
    fig = plt.figure(figsize=(12, 18), facecolor=COLORS['bg_dark'])

    # Layout: Header (big value), Period selector, Chart, Stats, Bottom details
    gs = fig.add_gridspec(5, 1, height_ratios=[1.5, 0.3, 3.0, 1.2, 1.5],
                          hspace=0.05,
                          left=0.06, right=0.94, top=0.95, bottom=0.03)

    # === HEADER - Like Apple Stocks ===
    ax_header = fig.add_subplot(gs[0])
    ax_header.set_facecolor(COLORS['bg_dark'])
    ax_header.axis('off')

    # Report type title - secondary but readable (24pt for mobile)
    if report_type == "morning":
        title = "Ночной отчет"
    elif report_type == "evening":
        title = "Дневной отчет"
    else:
        title = device_name
    ax_header.text(0.0, 0.85, title, fontsize=24,
                   color=COLORS['text_secondary'], transform=ax_header.transAxes,
                   fontweight='medium')

    # Current CO2 - HUGE, like stock price (96pt for mobile)
    ax_header.text(0.0, 0.30, f'{current_co2}', fontsize=96, fontweight='bold',
                   color=COLORS['text_primary'], transform=ax_header.transAxes,
                   fontfamily='sans-serif')

    # Change indicator next to value (28pt)
    ax_header.text(0.38, 0.42, f'{change_sign}{co2_change} ppm', fontsize=28,
                   color=change_color, transform=ax_header.transAxes,
                   fontweight='semibold')

    # Sleep quality for morning report
    if sleep_quality:
        ax_header.text(0.98, 0.30, f'Качество сна: {sleep_quality[0]}', fontsize=20,
                       color=sleep_quality[1], transform=ax_header.transAxes,
                       ha='right', fontweight='bold')

    # === PERIOD SELECTOR (visual only) ===
    ax_period = fig.add_subplot(gs[1])
    ax_period.set_facecolor(COLORS['bg_dark'])
    ax_period.axis('off')

    periods = ['1ч', '6ч', '12ч', '24ч', '7д', '30д']
    period_map = {1: 0, 6: 1, 12: 2, 24: 3, 168: 4, 720: 5}
    selected = period_map.get(period_hours, 3)

    for i, p in enumerate(periods):
        x_pos = 0.02 + i * 0.16
        if i == selected:
            # Selected - with background pill
            rect = mpatches.FancyBboxPatch((x_pos - 0.02, 0.15), 0.12, 0.7,
                                            boxstyle="round,pad=0.01,rounding_size=0.3",
                                            facecolor=COLORS['bg_card'],
                                            transform=ax_period.transAxes)
            ax_period.add_patch(rect)
            ax_period.text(x_pos + 0.04, 0.5, p, fontsize=20, fontweight='bold',
                          color=COLORS['text_primary'], ha='center', va='center',
                          transform=ax_period.transAxes)
        else:
            ax_period.text(x_pos + 0.04, 0.5, p, fontsize=20,
                          color=COLORS['text_secondary'], ha='center', va='center',
                          transform=ax_period.transAxes)

    # === MAIN CHART - Apple style ===
    ax_main = fig.add_subplot(gs[2])
    ax_main.set_facecolor(COLORS['bg_dark'])

    # Remove all spines
    for spine in ax_main.spines.values():
        spine.set_visible(False)

    # Minimal horizontal grid only
    ax_main.yaxis.grid(True, color=COLORS['grid'], alpha=0.3, linewidth=0.5)
    ax_main.xaxis.grid(False)
    ax_main.tick_params(colors=COLORS['text_secondary'], labelsize=18)  # Mobile readable
    ax_main.tick_params(axis='x', length=0, pad=12)
    ax_main.tick_params(axis='y', length=0)

    # DYNAMIC Y-axis limits - fit data tightly with small padding
    data_min = min(chart_co2)
    data_max = max(chart_co2)
    data_range = data_max - data_min
    padding = data_range * 0.15  # 15% padding

    y_min = max(0, data_min - padding)
    y_max = data_max + padding

    # Round to nice numbers
    y_min = int(y_min / 50) * 50
    y_max = int((y_max + 49) / 50) * 50

    ax_main.set_ylim(y_min, y_max)
    ax_main.set_xlim(chart_times[0], chart_times[-1])

    # Draw gradient fill - segment by color
    y_arr = np.array(chart_co2)

    # Create gradient fill from bottom
    n_strips = 50
    for seg_idx in range(len(chart_times) - 1):
        seg_color = get_co2_color(int(chart_co2[seg_idx]))
        seg_times = [chart_times[seg_idx], chart_times[seg_idx + 1]]
        seg_y = y_arr[seg_idx:seg_idx + 2]

        for i in range(n_strips):
            frac = i / n_strips
            alpha = 0.4 * (1 - frac) ** 2
            strip_top = y_min + (seg_y - y_min) * (1 - frac)
            strip_bot = y_min + (seg_y - y_min) * (1 - (i + 1) / n_strips)
            ax_main.fill_between(seg_times, strip_bot, strip_top, color=seg_color,
                                 alpha=alpha, linewidth=0, zorder=1)

    # Main line - smooth, colored by value
    for seg_idx in range(len(chart_times) - 1):
        seg_color = get_co2_color(int(chart_co2[seg_idx]))
        ax_main.plot(chart_times[seg_idx:seg_idx + 2], chart_co2[seg_idx:seg_idx + 2],
                     color=seg_color, linewidth=2.5, zorder=2, solid_capstyle='round')

    # Threshold lines - very subtle
    for thresh in [800, 1000]:
        if y_min < thresh < y_max:
            ax_main.axhline(y=thresh, color=COLORS['grid'], linestyle='--',
                           alpha=0.4, linewidth=0.8)

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

    # Y-axis on right
    ax_main.yaxis.tick_right()
    ax_main.yaxis.set_label_position('right')

    # === STATS CARDS - Clean grid like Apple ===
    ax_stats = fig.add_subplot(gs[3])
    ax_stats.set_facecolor(COLORS['bg_dark'])
    ax_stats.axis('off')

    # Draw separator line
    ax_stats.axhline(y=0.95, xmin=0.0, xmax=1.0, color=COLORS['grid'], linewidth=0.5)

    # Stats in 3 columns - mobile-optimized font sizes
    stats = [
        ('Средний', f'{avg_co2:.0f}', 'ppm'),
        ('Максимум', f'{max_co2}', 'ppm'),
        ('Минимум', f'{min_co2}', 'ppm'),
    ]

    for i, (label, value, unit) in enumerate(stats):
        x_center = 0.17 + i * 0.33

        # Label - readable on mobile (18pt)
        ax_stats.text(x_center, 0.75, label, fontsize=18,
                     color=COLORS['text_secondary'], ha='center',
                     transform=ax_stats.transAxes)

        # Value - large, colored (48pt for mobile)
        color = get_co2_color(int(value)) if i == 0 else COLORS['text_primary']
        if i == 1 and int(value) > 1000:
            color = COLORS['accent_orange']
        if i == 2 and int(value) < 800:
            color = COLORS['accent_green']

        ax_stats.text(x_center, 0.38, value, fontsize=48, fontweight='bold',
                     color=color, ha='center', transform=ax_stats.transAxes)

        # Unit - readable (16pt)
        ax_stats.text(x_center, 0.08, unit, fontsize=16,
                     color=COLORS['text_secondary'], ha='center',
                     transform=ax_stats.transAxes)

    # === BOTTOM DETAILS ===
    ax_bottom = fig.add_subplot(gs[4])
    ax_bottom.set_facecolor(COLORS['bg_dark'])
    ax_bottom.axis('off')

    # Separator
    ax_bottom.axhline(y=0.92, xmin=0.0, xmax=1.0, color=COLORS['grid'], linewidth=0.5)

    # Two-column layout like Apple - mobile readable fonts (18-20pt)
    left_items = [
        ('Температура', f'{avg_temp:.1f}C'),
        ('Влажность', f'{avg_humidity:.0f}%'),
        ('Замеров', f'{n}'),
    ]

    right_items = [
        ('Мин. темп.', f'{temp_min:.1f}C'),
        ('Макс. темп.', f'{temp_max:.1f}C'),
        ('Период', period_label),
    ]

    for i, (label, value) in enumerate(left_items):
        y_pos = 0.75 - i * 0.26
        ax_bottom.text(0.02, y_pos, label, fontsize=18,
                      color=COLORS['text_secondary'], ha='left',
                      transform=ax_bottom.transAxes)
        ax_bottom.text(0.45, y_pos, value, fontsize=20, fontweight='semibold',
                      color=COLORS['text_primary'], ha='right',
                      transform=ax_bottom.transAxes)

    for i, (label, value) in enumerate(right_items):
        y_pos = 0.75 - i * 0.26
        ax_bottom.text(0.52, y_pos, label, fontsize=18,
                      color=COLORS['text_secondary'], ha='left',
                      transform=ax_bottom.transAxes)
        ax_bottom.text(0.98, y_pos, value, fontsize=20, fontweight='semibold',
                      color=COLORS['text_primary'], ha='right',
                      transform=ax_bottom.transAxes)

    # Zone legend at very bottom
    ax_bottom.axhline(y=0.08, xmin=0.0, xmax=1.0, color=COLORS['grid'], linewidth=0.5)

    zone_items = [
        (COLORS['accent_green'], f'<800: {time_excellent:.0f}%'),
        (COLORS['accent_yellow'], f'800-1000: {time_good:.0f}%'),
        (COLORS['accent_orange'], f'1000-1500: {time_moderate:.0f}%'),
        (COLORS['accent_red'], f'>1500: {time_bad:.0f}%'),
    ]

    for i, (color, text) in enumerate(zone_items):
        x_pos = 0.03 + i * 0.24
        ax_bottom.plot(x_pos, 0.0, 's', color=color, markersize=12,
                      transform=ax_bottom.transAxes)
        ax_bottom.text(x_pos + 0.03, 0.0, text, fontsize=16,
                      color=COLORS['text_primary'], va='center',
                      transform=ax_bottom.transAxes, fontweight='medium')

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

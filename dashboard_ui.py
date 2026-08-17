"""Pure UI helpers for the health dashboard.

This module deliberately has no Tkinter dependency so its behavior can be
tested without creating a window.
"""


def _normalize_hex(value, fallback):
    if not isinstance(value, str):
        return fallback
    value = value.strip().lower()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except ValueError:
            pass
    return fallback


def blend_hex(foreground, background, foreground_ratio):
    """Blend two hex colors, clamping the foreground ratio to 0..1."""
    foreground = _normalize_hex(foreground, "#4caf50")
    background = _normalize_hex(background, "#ffffff")
    ratio = max(0.0, min(1.0, float(foreground_ratio)))
    fg = tuple(int(foreground[index:index + 2], 16) for index in (1, 3, 5))
    bg = tuple(int(background[index:index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(
        round(foreground_part * ratio + background_part * (1 - ratio))
        for foreground_part, background_part in zip(fg, bg)
    )
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def relative_luminance(color):
    """Return WCAG 2.x relative luminance for a hex color."""
    color = _normalize_hex(color, "#000000")
    channels = []
    for index in (1, 3, 5):
        channel = int(color[index:index + 2], 16) / 255.0
        channels.append(
            channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first, second):
    """Return the WCAG contrast ratio between two hex colors."""
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def get_dashboard_colors(theme_colors):
    """Derive stable semantic dashboard colors from legacy theme colors."""
    theme_colors = theme_colors if isinstance(theme_colors, dict) else {}
    primary = _normalize_hex(theme_colors.get("button_bg"), "#4caf50")
    primary_active = _normalize_hex(theme_colors.get("button_active"), primary)
    text_primary = "#123526"
    surface_alt = blend_hex(primary, "#ffffff", 0.12)
    on_primary = max(
        ("#ffffff", text_primary), key=lambda color: contrast_ratio(color, primary))
    secondary_action_text = (
        primary if contrast_ratio(primary, surface_alt) >= 4.5 else text_primary)
    return {
        "app_bg": blend_hex(primary, "#ffffff", 0.08),
        "surface": "#ffffff",
        "surface_alt": surface_alt,
        "primary": primary,
        "primary_active": primary_active,
        "on_primary": on_primary,
        "secondary_action_text": secondary_action_text,
        "text_primary": text_primary,
        "text_secondary": "#66756c",
        "border": blend_hex(primary, "#dce5df", 0.16),
        "danger_muted": "#fff1ee",
        "danger_text": "#a54535",
    }


def get_day_greeting(hour):
    """Return the greeting used in the dashboard for a 24-hour clock hour."""
    if hour < 9:
        return "早上好"
    if hour < 12:
        return "上午好"
    if hour < 18:
        return "下午好"
    return "晚上好"


def count_completed_items(today_data, reminder_keys):
    """Count configured reminder categories with a non-empty value today."""
    if not isinstance(today_data, dict):
        return 0
    return sum(1 for key in reminder_keys if today_data.get(key))


def calculate_window_geometry(
        screen_width, screen_height, requested_width=820, requested_height=720):
    """Calculate a centered dashboard geometry bounded by screen dimensions."""
    width = min(requested_width, max(720, screen_width - 80))
    height = min(requested_height, max(520, screen_height - 80))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return width, height, x, y

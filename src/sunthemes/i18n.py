"""Локализация: плоский словарь строк RU/EN.

Язык выбирается один раз при старте приложения (app.py) через
set_language(); по умолчанию английский.
"""

_LANG = "en"

STRINGS: dict[str, dict[str, str]] = {
    # --- статусная карточка ---
    "status.active_theme": {"ru": "Активна тема", "en": "Current theme"},
    "theme.light": {"ru": "Светлая", "en": "Light"},
    "theme.dark": {"ru": "Тёмная", "en": "Dark"},
    "status.manual_suffix": {"ru": "  (применено вручную)", "en": "  (set manually)"},
    "status.mode": {"ru": "Режим", "en": "Mode"},
    "mode.sun_short": {"ru": "по солнцу", "en": "by the sun"},
    "mode.time_short": {"ru": "по расписанию", "en": "by schedule"},
    "status.checked": {"ru": "проверка", "en": "checked"},
    # --- выбор режима ---
    "mode.group": {"ru": "Режим переключения", "en": "Switching mode"},
    "mode.sun": {"ru": "По солнцу (восход/закат)", "en": "By the sun (sunrise/sunset)"},
    "mode.time": {"ru": "По расписанию (фикс. время)", "en": "By schedule (fixed time)"},
    # --- режим «по солнцу» ---
    "sun.group": {"ru": "Параметры режима «По солнцу»", "en": "Sun mode settings"},
    "sun.city": {"ru": "Город:", "en": "City:"},
    "sun.lat": {"ru": "Широта:", "en": "Latitude:"},
    "sun.lon": {"ru": "Долгота:", "en": "Longitude:"},
    "sun.offset": {"ru": "Сдвиг:", "en": "Offset:"},
    "sun.offset_suffix": {"ru": " мин", "en": " min"},
    "sun.offset_hint": {"ru": "(− раньше / + позже)", "en": "(− earlier / + later)"},
    "sun.clouds": {
        "ru": "Учитывать облачность (Open-Meteo, без ключа)",
        "en": "Account for cloud cover (Open-Meteo, no API key)",
    },
    "sun.no_astral": {
        "ru": "⚠ Не установлена библиотека astral. Выполни: pip install astral",
        "en": "⚠ The astral library is missing. Run: pip install astral",
    },
    "sun.today": {
        "ru": "Сегодня: восход {sr} → светлая {sr2} | закат {ss} → тёмная {ss2}",
        "en": "Today: sunrise {sr} → light {sr2} | sunset {ss} → dark {ss2}",
    },
    "sun.cloud_line": {
        "ru": "<br>Облачность сейчас: <b>{cloud}%</b>. Времена ниже — по реальной освещённости (Open-Meteo).",
        "en": "<br>Cloud cover now: <b>{cloud}%</b>. Times below follow actual daylight (Open-Meteo).",
    },
    "sun.no_weather": {
        "ru": "<br>⚠ Не удалось получить погоду (нет интернета?). Работаем по чистой астрономии.",
        "en": "<br>⚠ Could not fetch weather (no internet?). Falling back to pure astronomy.",
    },
    "sun.calc_error": {"ru": "⚠ Не удалось рассчитать: {error}", "en": "⚠ Calculation failed: {error}"},
    # --- режим «по расписанию» ---
    "time.group": {"ru": "Параметры режима «По расписанию»", "en": "Schedule mode settings"},
    "time.light_from": {"ru": "Светлая с:", "en": "Light from:"},
    "time.dark_from": {"ru": "Тёмная с:", "en": "Dark from:"},
    # --- кнопки, чекбоксы ---
    "autostart": {
        "ru": "Запускать при старте Windows (свёрнутым в трей)",
        "en": "Start with Windows (minimized to tray)",
    },
    "desktop_shortcut": {
        "ru": "Ярлык на рабочем столе",
        "en": "Desktop shortcut",
    },
    "shortcut.description": {
        "ru": "Sunthemes — автосмена темы Windows по солнцу",
        "en": "Sunthemes — automatic Windows theme switching by the sun",
    },
    "btn.apply": {"ru": "Сохранить и применить", "en": "Save and apply"},
    "btn.light_tip": {"ru": "Включить светлую тему вручную", "en": "Switch to light theme manually"},
    "btn.dark_tip": {"ru": "Включить тёмную тему вручную", "en": "Switch to dark theme manually"},
    # --- трей ---
    "tray.open": {"ru": "Открыть настройки", "en": "Open settings"},
    "tray.light": {"ru": "☀ Светлая тема", "en": "☀ Light theme"},
    "tray.dark": {"ru": "🌙 Тёмная тема", "en": "🌙 Dark theme"},
    "tray.quit": {"ru": "Выход", "en": "Quit"},
    "tray.saved": {"ru": "Настройки сохранены и применены.", "en": "Settings saved and applied."},
    "tray.minimized": {
        "ru": "Свернулся в трей. Двойной клик по иконке — открыть.",
        "en": "Minimized to tray. Double-click the icon to open.",
    },
    # --- ошибки и сообщения ---
    "err.title": {"ru": "Ошибка", "en": "Error"},
    "err.coords": {
        "ru": "Координаты должны быть числами (например, 55.7558).",
        "en": "Coordinates must be numbers (e.g. 55.7558).",
    },
    "err.no_tray": {"ru": "Системный трей недоступен.", "en": "System tray is not available."},
    "msg.already_running": {
        "ru": "Sunthemes уже запущен. Иконка — в трее, рядом с часами.",
        "en": "Sunthemes is already running. Look for the tray icon near the clock.",
    },
    # --- города (id должны совпадать с config.CITIES + custom) ---
    "city.custom": {"ru": "Свои координаты", "en": "Custom coordinates"},
    "city.moscow": {"ru": "Москва", "en": "Moscow"},
    "city.spb": {"ru": "Санкт-Петербург", "en": "Saint Petersburg"},
    "city.yekaterinburg": {"ru": "Екатеринбург", "en": "Yekaterinburg"},
    "city.novosibirsk": {"ru": "Новосибирск", "en": "Novosibirsk"},
    "city.kaliningrad": {"ru": "Калининград", "en": "Kaliningrad"},
    "city.london": {"ru": "Лондон", "en": "London"},
    "city.berlin": {"ru": "Берлин", "en": "Berlin"},
    "city.paris": {"ru": "Париж", "en": "Paris"},
    "city.newyork": {"ru": "Нью-Йорк", "en": "New York"},
    "city.tokyo": {"ru": "Токио", "en": "Tokyo"},
}


def set_language(lang: str) -> None:
    """Установить язык интерфейса: 'ru' или 'en' (иное → 'en')."""
    global _LANG
    _LANG = lang if lang in ("ru", "en") else "en"


def get_language() -> str:
    return _LANG


def tr(key: str, **fmt) -> str:
    """Строка по ключу на текущем языке; {плейсхолдеры} подставляются из fmt."""
    s = STRINGS[key][_LANG]
    return s.format(**fmt) if fmt else s

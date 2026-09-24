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
    "switch.to_light": {"ru": "на светлую", "en": "to light"},
    "switch.to_dark": {"ru": "на тёмную", "en": "to dark"},
    "status.next": {"ru": "Смена {to} — {when}", "en": "Switch {to} {when}"},
    "status.no_switch": {
        "ru": "Смены темы в ближайшие дни не будет",
        "en": "No theme change in the coming days",
    },
    "status.manual": {
        "ru": "Выбрано вручную, расписание вернётся {when}",
        "en": "Set manually; schedule resumes {when}",
    },
    "status.manual_no_end": {"ru": "Выбрано вручную", "en": "Set manually"},
    "status.resume": {"ru": "вернуть авто", "en": "resume auto"},
    "status.checked": {"ru": "проверено {time}", "en": "checked {time}"},
    "when.today": {"ru": "в {time}", "en": "at {time}"},
    "when.tomorrow": {"ru": "завтра в {time}", "en": "tomorrow at {time}"},
    "when.date": {"ru": "{date} в {time}", "en": "{date} at {time}"},
    "mode.sun_short": {"ru": "По солнцу", "en": "By the sun"},
    "mode.time_short": {"ru": "По расписанию", "en": "By schedule"},
    # --- выбор режима ---
    "mode.group": {"ru": "Режим переключения", "en": "Switching mode"},
    "mode.sun": {
        "ru": "По солнцу (высота над горизонтом)",
        "en": "By the sun (height above the horizon)",
    },
    "mode.time": {
        "ru": "По расписанию (фиксированное время)",
        "en": "By schedule (fixed times)",
    },
    # --- режим «по солнцу» ---
    "sun.group": {"ru": "Параметры режима «По солнцу»", "en": "Sun mode settings"},
    "sun.city": {"ru": "Город:", "en": "City:"},
    "sun.lat": {"ru": "Широта:", "en": "Latitude:"},
    "sun.lon": {"ru": "Долгота:", "en": "Longitude:"},
    "sun.morning": {"ru": "Утром:", "en": "Morning:"},
    "sun.morning_hint": {
        "ru": "светлая, когда солнце выше",
        "en": "light once the sun is above",
    },
    "sun.evening": {"ru": "Вечером:", "en": "Evening:"},
    "sun.evening_hint": {
        "ru": "тёмная, когда солнце ниже",
        "en": "dark once the sun is below",
    },
    "sun.elevation_help": {
        "ru": "Высота солнца над горизонтом: 0° — восход/закат. Больше — "
              "светлая позже утром и тёмная раньше вечером.",
        "en": "Sun height above the horizon: 0° is sunrise/sunset. Higher "
              "means light later in the morning and dark earlier in the evening.",
    },
    "sun.clouds": {
        "ru": "Учитывать облачность (прогноз Open-Meteo, без ключа)",
        "en": "Account for clouds (Open-Meteo forecast, no API key)",
    },
    "sun.clouds_tip": {
        "ru": "В пасмурную погоду светлеет позже и темнеет раньше — тема "
              "сдвигается следом, но не больше чем на {max} мин. Для прогноза "
              "координаты округляются до ~10 км.",
        "en": "On overcast days it gets light later and dark earlier — the "
              "theme follows, by at most {max} min. Coordinates are rounded to "
              "~10 km for the forecast request.",
    },
    "sun.astro": {
        "ru": "Восход {sunrise} · закат {sunset}",
        "en": "Sunrise {sunrise} · sunset {sunset}",
    },
    "sun.polar_day": {
        "ru": "Полярный день: солнце не заходит",
        "en": "Polar day: the sun does not set",
    },
    "sun.polar_night": {
        "ru": "Полярная ночь: солнце не восходит",
        "en": "Polar night: the sun does not rise",
    },
    "sun.plan": {
        "ru": "Сегодня: светлая {light} → тёмная {dark}",
        "en": "Today: light {light} → dark {dark}",
    },
    "sun.all_dark": {
        "ru": "Сегодня солнце не поднимается выше порога — весь день тёмная",
        "en": "Today the sun stays below the threshold — dark all day",
    },
    "sun.all_light": {
        "ru": "Сегодня солнце не опускается ниже порога — весь день светлая",
        "en": "Today the sun stays above the threshold — light all day",
    },
    "sun.clouds_all_dark": {
        "ru": "Сегодня слишком пасмурно — весь день тёмная",
        "en": "Too overcast today — dark all day",
    },
    "sun.clouds_line": {"ru": "Облачность {cloud}: {details}", "en": "Clouds {cloud}: {details}"},
    "sun.shift_morning": {"ru": "светлая на {min} мин позже", "en": "light {min} min later"},
    "sun.shift_evening": {"ru": "тёмная на {min} мин раньше", "en": "dark {min} min earlier"},
    "sun.no_shift": {"ru": "светло, без поправки", "en": "bright enough, no correction"},
    "sun.clouds_loading": {"ru": "Загружаю прогноз погоды…", "en": "Loading the weather forecast…"},
    "sun.no_weather": {
        "ru": "⚠ Прогноз недоступен (нет интернета?) — время по чистой астрономии.",
        "en": "⚠ Forecast unavailable (no internet?) — using pure astronomy.",
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
    "btn.light_tip": {
        "ru": "Включить светлую тему вручную (до следующей смены)",
        "en": "Switch to light manually (until the next scheduled change)",
    },
    "btn.dark_tip": {
        "ru": "Включить тёмную тему вручную (до следующей смены)",
        "en": "Switch to dark manually (until the next scheduled change)",
    },
    # --- трей ---
    "tray.open": {"ru": "Открыть настройки", "en": "Open settings"},
    "tray.light": {"ru": "☀ Светлая тема", "en": "☀ Light theme"},
    "tray.dark": {"ru": "🌙 Тёмная тема", "en": "🌙 Dark theme"},
    "tray.auto": {"ru": "Вернуть автоматический режим", "en": "Resume automatic switching"},
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
    "err.coords_range": {
        "ru": "Широта — от −90 до 90, долгота — от −180 до 180.",
        "en": "Latitude must be within −90…90 and longitude within −180…180.",
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

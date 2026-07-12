"""Пути приложения, конфиг и пресеты городов.

Имена APP_NAME (ключ автозагрузки) и каталога конфига сохранены от
ThemeSwitcher — совместимость со старыми установками.
"""

import json
import logging
import logging.handlers
from pathlib import Path

APP_NAME = "ThemeSwitcher"          # ключ в HKCU\...\Run — не менять
APP_DIR = Path.home() / ".theme_switcher"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "theme_switcher.log"
LOG_MAX_BYTES = 1_000_000           # ~1 МБ, дальше файл ротируется
LOG_BACKUPS = 2                     # хранить theme_switcher.log.1 и .log.2

log = logging.getLogger("sunthemes")


def setup_logging() -> logging.handlers.RotatingFileHandler:
    """Файловый лог с ротацией по размеру — без неё лог рос бесконечно."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    return handler

# Пресеты городов: id → (широта, долгота, IANA-таймзона).
# Отображаемые названия — в i18n по ключу "city.<id>".
CITIES: dict[str, tuple[float, float, str]] = {
    "moscow":        (55.7558, 37.6173, "Europe/Moscow"),
    "spb":           (59.9311, 30.3609, "Europe/Moscow"),
    "yekaterinburg": (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "novosibirsk":   (55.0084, 82.9357, "Asia/Novosibirsk"),
    "kaliningrad":   (54.7104, 20.4522, "Europe/Kaliningrad"),
    "london":        (51.5074, -0.1278, "Europe/London"),
    "berlin":        (52.5200, 13.4050, "Europe/Berlin"),
    "paris":         (48.8566, 2.3522,  "Europe/Paris"),
    "newyork":       (40.7128, -74.0060, "America/New_York"),
    "tokyo":         (35.6762, 139.6503, "Asia/Tokyo"),
}

# Старые конфиги хранили русское название города — маппинг на новые id.
LEGACY_CITY_NAMES: dict[str, str] = {
    "Москва": "moscow",
    "Санкт-Петербург": "spb",
    "Екатеринбург": "yekaterinburg",
    "Новосибирск": "novosibirsk",
    "Калининград": "kaliningrad",
}

DEFAULT_CONFIG: dict = {
    "mode": "sun",            # "sun" | "time"
    "city": "moscow",         # id из CITIES или "custom"
    "lat": 55.7558,
    "lon": 37.6173,
    "tz": "Europe/Moscow",
    "offset_min": 0,          # сдвиг от восхода/заката, минуты
    "light_time": "07:00",
    "dark_time": "19:00",
    "use_clouds": False,      # учитывать реальную освещённость (Open-Meteo)
    "clouds_max_offset_min": 120,  # предел отклонения от астрономии, минуты
}


def resolve_city_id(cfg: dict) -> str:
    """id города для конфига: новый id, legacy-имя или 'custom'.

    Неизвестное название (в т.ч. отсутствующее) трактуем как свои
    координаты — lat/lon/tz пользователя при этом сохраняются как есть.
    """
    raw = cfg.get("city", "")
    if raw in CITIES:
        return raw
    return LEGACY_CITY_NAMES.get(raw, "custom")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Cannot read config: %s. Using defaults.", e)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )

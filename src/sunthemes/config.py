"""Пути приложения, конфиг и пресеты городов.

Имена APP_NAME (ключ автозагрузки) и каталога конфига сохранены от
ThemeSwitcher — совместимость со старыми установками.
"""

import json
import logging
import logging.handlers
import os
from datetime import time as _time
from pathlib import Path

APP_NAME = "ThemeSwitcher"          # ключ в HKCU\...\Run — не менять
APP_DIR = Path.home() / ".theme_switcher"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "theme_switcher.log"
ICON_PATH = APP_DIR / "icon.ico"    # стабильная копия иконки для ярлыков
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


# Пресеты городов: id → (широта, долгота).
# Отображаемые названия — в i18n по ключу "city.<id>".
CITIES: dict[str, tuple[float, float]] = {
    "moscow":        (55.7558, 37.6173),
    "spb":           (59.9311, 30.3609),
    "yekaterinburg": (56.8389, 60.6057),
    "novosibirsk":   (55.0084, 82.9357),
    "kaliningrad":   (54.7104, 20.4522),
    "london":        (51.5074, -0.1278),
    "berlin":        (52.5200, 13.4050),
    "paris":         (48.8566, 2.3522),
    "newyork":       (40.7128, -74.0060),
    "tokyo":         (35.6762, 139.6503),
}

# Старые конфиги хранили русское название города — маппинг на новые id.
LEGACY_CITY_NAMES: dict[str, str] = {
    "Москва": "moscow",
    "Санкт-Петербург": "spb",
    "Екатеринбург": "yekaterinburg",
    "Новосибирск": "novosibirsk",
    "Калининград": "kaliningrad",
}

# Ключи прежних версий, которые больше ничего не значат:
# tz — время теперь системное (как на часах Windows); offset_min — единый
# сдвиг, двигавший утро и вечер в одну сторону, заменён порогами высоты
# солнца (morning_elevation / evening_elevation).
OBSOLETE_KEYS = ("tz", "offset_min")

# Допустимый диапазон порогов высоты солнца, градусы.
ELEVATION_MIN, ELEVATION_MAX = -6, 20

DEFAULT_CONFIG: dict = {
    "mode": "sun",            # "sun" | "time"
    "city": "moscow",         # id из CITIES или "custom"
    "lat": 55.7558,
    "lon": 37.6173,
    # Светлая утром — когда солнце поднимется выше, тёмная вечером — когда
    # опустится ниже этой высоты, градусы. 0° ≈ восход/закат; 5° — примерно
    # 40–60 мин от восхода/заката на широте Москвы: в комнате уже/ещё светло.
    "morning_elevation": 5,
    "evening_elevation": 5,
    "light_time": "07:00",
    "dark_time": "19:00",
    "use_clouds": False,      # учитывать реальную освещённость (Open-Meteo)
    "clouds_max_offset_min": 120,  # на сколько облака могут сдвинуть смену, мин
    # Ярлык в меню «Пуск» создаётся один раз; если пользователь удалил его —
    # не навязываем повторно (маркер «уже создавали»).
    "start_menu_shortcut_seeded": False,
    # Ярлык на рабочем столе создаётся один раз при первом запуске; удалённый
    # пользователем не навязываем повторно (маркер «уже создавали»).
    "desktop_shortcut_seeded": False,
}


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validated(cfg: dict) -> dict:
    """Каждое битое значение → дефолт поля + предупреждение в лог.
    Руками отредактированный config.json не должен ронять приложение."""
    out = dict(cfg)

    def reset(key: str, why: str) -> None:
        log.warning("Config: bad %r (%s) — default %r used",
                    key, why, DEFAULT_CONFIG[key])
        out[key] = DEFAULT_CONFIG[key]

    if out.get("mode") not in ("sun", "time"):
        reset("mode", "must be 'sun' or 'time'")
    if not isinstance(out.get("city"), str):
        reset("city", "must be a string")
    for key, lo, hi in (("lat", -90, 90), ("lon", -180, 180),
                        ("morning_elevation", ELEVATION_MIN, ELEVATION_MAX),
                        ("evening_elevation", ELEVATION_MIN, ELEVATION_MAX)):
        v = out.get(key)
        if not _is_number(v) or not lo <= v <= hi:
            reset(key, f"must be a number in [{lo}, {hi}]")
    for key in ("light_time", "dark_time"):
        try:
            _time.fromisoformat(out.get(key))
        except (TypeError, ValueError):
            reset(key, "must be HH:MM")
    v = out.get("clouds_max_offset_min")
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 720:
        reset("clouds_max_offset_min", "must be an integer in [0, 720]")
    for key in ("use_clouds", "start_menu_shortcut_seeded",
                "desktop_shortcut_seeded"):
        if not isinstance(out.get(key), bool):
            reset(key, "must be true/false")
    return out


def resolve_city_id(cfg: dict) -> str:
    """id города для конфига: новый id, legacy-имя или 'custom'.

    Неизвестное название (в т.ч. отсутствующее) трактуем как свои
    координаты — lat/lon пользователя при этом сохраняются как есть.
    """
    raw = cfg.get("city", "")
    if raw in CITIES:
        return raw
    return LEGACY_CITY_NAMES.get(raw, "custom")


def _migrated(cfg: dict) -> dict:
    """Приведение конфига прежних версий к текущему виду."""
    out = {k: v for k, v in cfg.items() if k not in OBSOLETE_KEYS}
    out["city"] = resolve_city_id(out)
    if out["city"] in CITIES:
        # Для пресета координаты — всегда пресетные: что видно в окне,
        # по тому и считаем.
        out["lat"], out["lon"] = CITIES[out["city"]]
    return out


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("top level must be an object")
            cfg.update(data)
        except (ValueError, OSError) as e:
            log.warning("Cannot read config: %s. Using defaults.", e)
    return _migrated(_validated(cfg))


def save_config(cfg: dict) -> None:
    """Атомарная запись: сбой посреди записи не оставит битый config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)


def ensure_app_icon() -> Path | None:
    """Копия иконки пакета в APP_DIR — стабильный путь для ярлыков
    (путь внутри venv меняется при обновлениях). None — если не вышло."""
    src = Path(__file__).parent / "icon.ico"
    try:
        if not src.exists():
            return None
        APP_DIR.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        if not ICON_PATH.exists() or ICON_PATH.read_bytes() != data:
            ICON_PATH.write_bytes(data)
        return ICON_PATH
    except OSError as e:
        log.warning("Cannot copy app icon: %s", e)
        return None

"""
Theme Switcher — автоматическое переключение темы Windows (светлая/тёмная)
по времени суток или по восходу/закату солнца.

Зависимости: PySide6, astral
Запуск: pythonw theme_switcher.py  (без консоли)
        python  theme_switcher.py  (с консолью, для отладки)
"""

import ctypes
from ctypes import wintypes
import json
import logging
import sys
import winreg
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from PySide6.QtCore import QAbstractNativeEventFilter, QTime, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox,
    QSystemTrayIcon, QTimeEdit, QVBoxLayout, QWidget,
)

try:
    from astral import Observer
    from astral.sun import sun
    ASTRAL_OK = True
except ImportError:
    ASTRAL_OK = False

# ---------------------------------------------------------------------------
# Конфигурация и константы
# ---------------------------------------------------------------------------

APP_NAME = "ThemeSwitcher"
APP_DIR = Path.home() / ".theme_switcher"
CONFIG_PATH = APP_DIR / "config.json"
LOG_PATH = APP_DIR / "theme_switcher.log"

THEMES_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Пресеты городов: (lat, lon, IANA timezone)
CITIES = {
    "Москва":          (55.7558, 37.6173, "Europe/Moscow"),
    "Санкт-Петербург": (59.9311, 30.3609, "Europe/Moscow"),
    "Екатеринбург":    (56.8389, 60.6057, "Asia/Yekaterinburg"),
    "Новосибирск":     (55.0084, 82.9357, "Asia/Novosibirsk"),
    "Калининград":     (54.7104, 20.4522, "Europe/Kaliningrad"),
}

DEFAULT_CONFIG = {
    "mode": "sun",            # "sun" | "time"
    "city": "Москва",
    "lat": 55.7558,
    "lon": 37.6173,
    "tz": "Europe/Moscow",
    "offset_min": 0,          # сдвиг от восхода/заката в минутах
    "light_time": "07:00",
    "dark_time": "19:00",
    "use_clouds": False,      # учитывать реальную освещённость с Open-Meteo
    "clouds_max_offset_min": 120,  # защитный лимит отклонения от астрономии (мин)
}

APP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger(APP_NAME)

# ---------------------------------------------------------------------------
# Работа с темой Windows
# ---------------------------------------------------------------------------

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002

# Power management — для отслеживания выхода из сна.
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMESUSPEND = 0x0007    # явное пробуждение пользователем
PBT_APMRESUMEAUTOMATIC = 0x0012  # автопробуждение (таймер/событие)

# В ctypes.wintypes нет LRESULT и DWORD_PTR — определяем вручную.
# LRESULT = LONG_PTR (signed, размер с указатель), DWORD_PTR = ULONG_PTR (unsigned).
LRESULT = ctypes.c_ssize_t
DWORD_PTR = ctypes.c_size_t

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_SendMessageTimeoutW = _user32.SendMessageTimeoutW
_SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(DWORD_PTR),
]
_SendMessageTimeoutW.restype = LRESULT

# Сигнатуры для singleton-мьютекса
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.GetLastError.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
ERROR_ALREADY_EXISTS = 183


def _broadcast_theme_change():
    result = DWORD_PTR()
    _SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet",
        SMTO_ABORTIFHUNG, 1000, ctypes.byref(result),
    )


def acquire_singleton_mutex(name: str = "ThemeSwitcher_singleton_v1"):
    """Захват именованного мьютекса. Возвращает handle (хранить до выхода) или None,
    если другой инстанс уже работает. handle освободится сам при завершении процесса —
    даже если процесс упал."""
    handle = _kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None
    if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return None
    return handle


def get_current_theme() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEMES_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except OSError:
        return "light"


def set_theme(theme: str) -> None:
    """theme: 'light' | 'dark'"""
    value = 1 if theme == "light" else 0
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, THEMES_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
    _broadcast_theme_change()
    log.info("Тема переключена на %s", theme)


# ---------------------------------------------------------------------------
# Автозагрузка
# ---------------------------------------------------------------------------

def _autostart_command() -> str:
    """Команда для автозапуска.
    Если запущены из собранного .exe (PyInstaller frozen) — пишем путь к самому .exe.
    Иначе — pythonw.exe + путь к скрипту, чтобы стартовало без чёрного окна."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else sys.executable)
    script = str(Path(__file__).resolve())
    return f'"{exe}" "{script}" --tray'


def resource_path(rel: str) -> Path:
    """Путь к ресурсу: рядом со скриптом для dev-запуска,
    из распакованной временной папки PyInstaller — для onefile-сборки."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / rel


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Конфиг
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Не удалось прочитать конфиг: %s. Использую дефолт.", e)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Логика расчёта целевой темы
# ---------------------------------------------------------------------------

def compute_sun_times(lat: float, lon: float, tz: str, date=None):
    """Возвращает (sunrise, sunset) как TZ-aware datetime в указанной таймзоне."""
    if not ASTRAL_OK:
        return None, None
    zone = ZoneInfo(tz)
    if date is None:
        date = datetime.now(zone).date()
    observer = Observer(latitude=lat, longitude=lon, elevation=0)
    s = sun(observer, date=date, tzinfo=zone)
    return s["sunrise"], s["sunset"]


class WeatherProvider:
    """Тянет с Open-Meteo (без API-ключа) почасовой прогноз: облачность и
    реальную солнечную радиацию shortwave_radiation (Вт/м²). Кеш 30 мин.

    Главная фишка — effective_sun_times(): возвращает не астрономический
    закат, а момент когда радиация фактически падает ниже порога сумерек.
    Это учитывает облачность нелинейно, через реальную физику Open-Meteo,
    а не пропорцию-от-балды.
    """

    URL = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={lat}&longitude={lon}"
        "&current=cloud_cover"
        "&hourly=shortwave_radiation,cloud_cover"
        "&forecast_days=2"
        "&timezone={tz}"
    )
    CACHE_TTL = timedelta(minutes=30)
    TIMEOUT_SEC = 6
    # Порог "достаточной" освещённости. ~50 Вт/м² — типичные гражданские
    # сумерки: фонарей ещё не нужно, но за ноутбуком уже комфортнее тёмное.
    THRESHOLD_W_M2 = 50

    def __init__(self) -> None:
        self._cache: tuple[datetime, float, float, dict] | None = None

    def _fetch(self, lat: float, lon: float, tz: str) -> dict | None:
        """Достаёт данные из кеша или из сети. None при сетевой ошибке."""
        now = datetime.now()
        if self._cache:
            when, c_lat, c_lon, data = self._cache
            same_loc = abs(c_lat - lat) < 0.01 and abs(c_lon - lon) < 0.01
            if same_loc and (now - when) < self.CACHE_TTL:
                return data
        try:
            url = self.URL.format(lat=lat, lon=lon, tz=tz)
            with urlopen(url, timeout=self.TIMEOUT_SEC) as r:
                data = json.loads(r.read().decode("utf-8"))
            self._cache = (now, lat, lon, data)
            log.info("Open-Meteo: получен прогноз для (%.4f, %.4f)", lat, lon)
            return data
        except (URLError, OSError, ValueError, KeyError) as e:
            log.warning("Open-Meteo недоступен: %s", e)
            return None

    def current_cloud(self, lat: float, lon: float, tz: str) -> int | None:
        data = self._fetch(lat, lon, tz)
        if not data:
            return None
        try:
            return int(data["current"]["cloud_cover"])
        except (KeyError, TypeError, ValueError):
            return None

    def effective_sun_times(
        self, lat: float, lon: float, tz: str,
        sunrise: datetime, sunset: datetime,
        max_offset_min: int = 120,
    ) -> tuple[datetime | None, datetime | None]:
        """Возвращает (eff_sunrise, eff_sunset) — моменты, когда фактическая
        солнечная радиация переходит порог THRESHOLD_W_M2 (вверх для восхода,
        вниз для заката). Между двумя соседними часами линейно интерполируем —
        в результате точность до минут, а не до часа.

        Если данные не получить или переход не найден — соответствующее
        значение = None и логика снаружи возьмёт астрономическое."""
        data = self._fetch(lat, lon, tz)
        if not data:
            return None, None
        try:
            zone = ZoneInfo(tz)
            times_iso = data["hourly"]["time"]
            rads = data["hourly"]["shortwave_radiation"]
        except KeyError:
            return None, None

        # Превратим почасовые точки в (datetime, радиация) одного дня.
        target_date = sunrise.date()
        points: list[tuple[datetime, float]] = []
        for t_iso, r in zip(times_iso, rads):
            dt = datetime.fromisoformat(t_iso).replace(tzinfo=zone)
            if dt.date() == target_date and r is not None:
                points.append((dt, float(r)))
        if len(points) < 2:
            return None, None

        threshold = self.THRESHOLD_W_M2
        eff_sr: datetime | None = None
        eff_ss: datetime | None = None

        # Идём по соседним парам и ищем пересечения порога.
        for (t0, r0), (t1, r1) in zip(points, points[1:]):
            crosses_up = r0 < threshold <= r1
            crosses_down = r0 >= threshold > r1
            if not (crosses_up or crosses_down):
                continue
            # Линейная интерполяция между t0 и t1 по моменту достижения порога.
            frac = (threshold - r0) / (r1 - r0)
            cross_t = t0 + (t1 - t0) * frac
            if crosses_up and eff_sr is None:
                eff_sr = cross_t
            if crosses_down and eff_sr is not None:
                # закат — обязательно после восхода в этот же день
                eff_ss = cross_t

        # Защитный clamp: если радиационная модель уехала далеко от астрономии
        # (например, очень короткий день / странные данные) — ограничиваем сдвиг.
        cap = timedelta(minutes=max_offset_min)
        if eff_sr is not None:
            eff_sr = min(max(eff_sr, sunrise - cap), sunrise + cap)
        if eff_ss is not None:
            eff_ss = min(max(eff_ss, sunset - cap), sunset + cap)
        return eff_sr, eff_ss


# Глобальный экземпляр — состояние кеша живёт на всё приложение.
_weather = WeatherProvider()


def _apply_weather_adjustment(
    sunrise: datetime, sunset: datetime, cfg: dict
) -> tuple[datetime, datetime, int | None]:
    """Если включён режим погоды — заменяет sunrise/sunset на эффективные по
    реальной освещённости. Третий элемент — текущая облачность для UI
    (None означает «не показываем» — выключено или сеть недоступна)."""
    if not cfg.get("use_clouds"):
        return sunrise, sunset, None
    lat, lon, tz = cfg["lat"], cfg["lon"], cfg["tz"]
    cloud = _weather.current_cloud(lat, lon, tz)
    if cloud is None:
        return sunrise, sunset, None
    max_off = cfg.get("clouds_max_offset_min", 120)
    eff_sr, eff_ss = _weather.effective_sun_times(
        lat, lon, tz, sunrise, sunset, max_offset_min=max_off,
    )
    return (eff_sr or sunrise), (eff_ss or sunset), cloud


def determine_target_theme(cfg: dict, now: datetime | None = None) -> str:
    """Сравнение ведём в TZ-aware времени той зоны, что задана в конфиге —
    тогда сборка корректна даже если системная TZ отличается от выбранной в настройках."""
    zone = ZoneInfo(cfg["tz"])
    now_z = now.astimezone(zone) if (now and now.tzinfo) else datetime.now(zone)

    if cfg["mode"] == "sun" and ASTRAL_OK:
        try:
            sunrise, sunset = compute_sun_times(
                cfg["lat"], cfg["lon"], cfg["tz"], now_z.date()
            )
            sunrise, sunset, _ = _apply_weather_adjustment(sunrise, sunset, cfg)
            offset = timedelta(minutes=cfg.get("offset_min", 0))
            return "light" if (sunrise + offset) <= now_z < (sunset + offset) else "dark"
        except Exception as e:
            log.error("Ошибка расчёта солнца: %s. Падаем на режим времени.", e)

    light_t = time.fromisoformat(cfg["light_time"])
    dark_t = time.fromisoformat(cfg["dark_time"])
    cur = now_z.time()
    if light_t <= dark_t:
        return "light" if light_t <= cur < dark_t else "dark"
    return "dark" if dark_t <= cur < light_t else "light"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Тема UI (Fluent-стиль для Win11 — светлая/тёмная палитра)
# ---------------------------------------------------------------------------

def _qss(is_dark: bool) -> str:
    """Возвращает таблицу стилей под светлую или тёмную палитру Win11."""
    if is_dark:
        bg, surface, surf_hover = "#202020", "#2c2c2c", "#383838"
        border, border_strong = "#454545", "#5a5a5a"
        text, text_dim = "#f0f0f0", "#9a9a9a"
        accent, accent_text = "#4cc2ff", "#000000"
    else:
        bg, surface, surf_hover = "#f3f3f3", "#ffffff", "#f5f5f5"
        border, border_strong = "#cccccc", "#a8a8a8"
        text, text_dim = "#1a1a1a", "#5a5a5a"
        accent, accent_text = "#0067c0", "#ffffff"

    return f"""
        QWidget {{
            background: {bg};
            color: {text};
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            font-size: 10pt;
        }}
        QGroupBox {{
            background: {surface};
            border: 1px solid {border};
            border-radius: 8px;
            margin-top: 14px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            background: {bg};
            color: {text};
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#statusCard {{
            background: {surface};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 14px;
            font-size: 11pt;
        }}
        QLabel#sunInfo {{
            color: {text_dim};
            padding-top: 4px;
        }}
        QLineEdit, QComboBox, QSpinBox, QTimeEdit {{
            background: {surface};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 22px;
            selection-background-color: {accent};
            selection-color: {accent_text};
        }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QTimeEdit:hover {{
            border-color: {border_strong};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {{
            border-color: {accent};
        }}
        QLineEdit:read-only {{
            color: {text_dim};
            background: {bg};
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background: {surface};
            color: {text};
            border: 1px solid {border};
            selection-background-color: {accent};
            selection-color: {accent_text};
            outline: 0;
        }}
        QPushButton {{
            background: {surface};
            color: {text};
            border: 1px solid {border};
            border-radius: 6px;
            padding: 8px 16px;
            min-height: 24px;
        }}
        QPushButton:hover {{ background: {surf_hover}; border-color: {border_strong}; }}
        QPushButton:pressed {{ background: {border}; }}
        QPushButton#applyBtn {{
            background: {accent};
            color: {accent_text};
            border: 1px solid {accent};
            font-weight: 600;
        }}
        QPushButton#applyBtn:hover {{ background: {accent}; border: 1px solid {accent}; }}
        QPushButton#applyBtn:pressed {{ background: {accent}; }}
        QPushButton#themeBtn {{
            font-family: "Segoe UI Emoji", "Segoe UI Symbol", sans-serif;
            font-size: 18pt;
            min-width: 56px;
            max-width: 56px;
            min-height: 42px;
            padding: 0;
        }}
        QPushButton#themeBtn[active="true"] {{
            border: 2px solid {accent};
            background: {surf_hover};
        }}
        QCheckBox {{ spacing: 8px; }}
        QToolTip {{
            background: {surface};
            color: {text};
            border: 1px solid {border};
            padding: 4px 8px;
            border-radius: 4px;
        }}
    """


def apply_app_theme(app) -> None:
    """Подбирает QSS под текущую системную палитру (Light/Dark) и применяет."""
    scheme = app.styleHints().colorScheme()
    is_dark = scheme == Qt.ColorScheme.Dark
    app.setStyleSheet(_qss(is_dark))


def make_app_icon() -> QIcon:
    """Берёт готовую icon.ico (мульти-размерная, чёткая на high-DPI),
    при отсутствии — рисует упрощённую 64×64."""
    ico = resource_path("icon.ico")
    if ico.exists():
        return QIcon(str(ico))

    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # тёмный полукруг — луна
    p.setBrush(QColor("#2c3e50"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPie(8, 8, 48, 48, 90 * 16, 180 * 16)
    # светлый полукруг — солнце
    p.setBrush(QColor("#f1c40f"))
    p.drawPie(8, 8, 48, 48, -90 * 16, 180 * 16)
    p.end()
    return QIcon(pix)


class PowerEventFilter(QAbstractNativeEventFilter):
    """Слушает WM_POWERBROADCAST. После выхода из сна сразу запускает on_resume,
    чтобы тема догналась немедленно, а не через минуту по обычному tick."""

    def __init__(self, on_resume):
        super().__init__()
        self._on_resume = on_resume

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_POWERBROADCAST and msg.wParam in (
                PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC,
            ):
                log.info("Wake-from-sleep — форсируем проверку темы")
                self._on_resume()
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.setWindowTitle("Theme Switcher")
        self.setFixedSize(500, 680)
        self.setWindowIcon(make_app_icon())

        self._build_ui()
        self._load_to_ui()
        self._setup_tray()

        # Проверка раз в минуту
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(60_000)
        self.tick()

    # ---------- построение UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusCard")
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.status_label)

        # Режим
        mode_box = QGroupBox("Режим переключения")
        ml = QVBoxLayout(mode_box)
        ml.setContentsMargins(14, 18, 14, 14)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("По солнцу (восход/закат)", "sun")
        self.mode_combo.addItem("По расписанию (фикс. время)", "time")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ml.addWidget(self.mode_combo)
        root.addWidget(mode_box)

        # Параметры «по солнцу»
        self.sun_box = QGroupBox("Параметры режима «По солнцу»")
        sl = QVBoxLayout(self.sun_box)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(10)

        # Фиксированная ширина первой колонки лейблов — иначе поля съезжают
        # друг относительно друга по горизонтали.
        LABEL_W = 76

        def _label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFixedWidth(LABEL_W)
            return lbl

        h1 = QHBoxLayout()
        h1.addWidget(_label("Город:"))
        self.city_combo = QComboBox()
        for name in CITIES:
            self.city_combo.addItem(name)
        self.city_combo.addItem("Свои координаты")
        self.city_combo.currentIndexChanged.connect(self._on_city_changed)
        h1.addWidget(self.city_combo, 1)
        sl.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(_label("Широта:"))
        self.lat_edit = QLineEdit()
        h2.addWidget(self.lat_edit, 1)
        h2.addWidget(QLabel("Долгота:"))
        self.lon_edit = QLineEdit()
        h2.addWidget(self.lon_edit, 1)
        sl.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(_label("Сдвиг:"))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-180, 180)
        self.offset_spin.setSuffix(" мин")
        h3.addWidget(self.offset_spin)
        hint = QLabel("(− раньше / + позже)")
        hint.setObjectName("sunInfo")
        h3.addWidget(hint)
        h3.addStretch()
        sl.addLayout(h3)

        # Учитывать облачность через Open-Meteo: при пасмурной погоде тёмная
        # включается раньше, светлая — позже.
        self.clouds_cb = QCheckBox("Учитывать облачность (берём с Open-Meteo, без ключа)")
        self.clouds_cb.toggled.connect(self._update_sun_info)
        sl.addWidget(self.clouds_cb)

        self.sun_info_label = QLabel()
        self.sun_info_label.setObjectName("sunInfo")
        self.sun_info_label.setWordWrap(True)
        sl.addWidget(self.sun_info_label)
        root.addWidget(self.sun_box)

        # Параметры «по расписанию»
        self.time_box = QGroupBox("Параметры режима «По расписанию»")
        tl = QHBoxLayout(self.time_box)
        tl.setContentsMargins(14, 18, 14, 14)
        tl.addWidget(QLabel("Светлая с:"))
        self.light_time_edit = QTimeEdit()
        self.light_time_edit.setDisplayFormat("HH:mm")
        tl.addWidget(self.light_time_edit)
        tl.addSpacing(20)
        tl.addWidget(QLabel("Тёмная с:"))
        self.dark_time_edit = QTimeEdit()
        self.dark_time_edit.setDisplayFormat("HH:mm")
        tl.addWidget(self.dark_time_edit)
        tl.addStretch()
        root.addWidget(self.time_box)

        self.autostart_cb = QCheckBox("Запускать при старте Windows (свёрнутым в трей)")
        root.addWidget(self.autostart_cb)

        # Кнопки
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.apply_btn = QPushButton("Сохранить и применить")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self._on_apply)
        bl.addWidget(self.apply_btn, 2)

        self.light_btn = QPushButton("☀")
        self.light_btn.setObjectName("themeBtn")
        self.light_btn.setToolTip("Включить светлую тему вручную")
        self.light_btn.clicked.connect(lambda: self._manual_set("light"))
        bl.addWidget(self.light_btn)

        self.dark_btn = QPushButton("🌙")
        self.dark_btn.setObjectName("themeBtn")
        self.dark_btn.setToolTip("Включить тёмную тему вручную")
        self.dark_btn.clicked.connect(lambda: self._manual_set("dark"))
        bl.addWidget(self.dark_btn)
        root.addLayout(bl)

        root.addStretch()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip("Theme Switcher")
        menu = QMenu()

        a_show = QAction("Открыть настройки", self)
        a_show.triggered.connect(self._show_window)
        menu.addAction(a_show)
        menu.addSeparator()

        a_light = QAction("☀ Светлая тема", self)
        a_light.triggered.connect(lambda: self._manual_set("light"))
        menu.addAction(a_light)

        a_dark = QAction("🌙 Тёмная тема", self)
        a_dark.triggered.connect(lambda: self._manual_set("dark"))
        menu.addAction(a_dark)

        menu.addSeparator()
        a_quit = QAction("Выход", self)
        a_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(a_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ---------- наполнение из конфига ----------
    def _load_to_ui(self):
        idx = self.mode_combo.findData(self.cfg["mode"])
        self.mode_combo.setCurrentIndex(max(0, idx))

        idx = self.city_combo.findText(self.cfg.get("city", "Москва"))
        self.city_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.lat_edit.setText(str(self.cfg["lat"]))
        self.lon_edit.setText(str(self.cfg["lon"]))
        self.offset_spin.setValue(self.cfg.get("offset_min", 0))

        self.light_time_edit.setTime(QTime.fromString(self.cfg["light_time"], "HH:mm"))
        self.dark_time_edit.setTime(QTime.fromString(self.cfg["dark_time"], "HH:mm"))

        self.clouds_cb.setChecked(bool(self.cfg.get("use_clouds", False)))
        self.autostart_cb.setChecked(is_autostart_enabled())

        self._on_mode_changed()
        self._on_city_changed()

    # ---------- обработчики ----------
    def _on_mode_changed(self):
        is_sun = self.mode_combo.currentData() == "sun"
        self.sun_box.setVisible(is_sun)
        self.time_box.setVisible(not is_sun)
        if is_sun and not ASTRAL_OK:
            self.sun_info_label.setText(
                "⚠ Не установлена библиотека astral. Выполни: pip install astral"
            )

    def _on_city_changed(self):
        name = self.city_combo.currentText()
        custom = name == "Свои координаты"
        self.lat_edit.setReadOnly(not custom)
        self.lon_edit.setReadOnly(not custom)
        if not custom and name in CITIES:
            lat, lon, _tz = CITIES[name]
            self.lat_edit.setText(str(lat))
            self.lon_edit.setText(str(lon))
        self._update_sun_info()

    def _update_sun_info(self):
        if not ASTRAL_OK:
            return
        try:
            lat = float(self.lat_edit.text())
            lon = float(self.lon_edit.text())
            name = self.city_combo.currentText()
            tz = CITIES.get(name, (None, None, "Europe/Moscow"))[2]
            sr, ss = compute_sun_times(lat, lon, tz)
            if not (sr and ss):
                return
            offset = self.offset_spin.value()

            # Если включена погода — берём эффективные времена по реальной радиации.
            cloud_line = ""
            if self.clouds_cb.isChecked():
                tmp_cfg = {
                    "lat": lat, "lon": lon, "tz": tz, "use_clouds": True,
                    "clouds_max_offset_min": self.cfg.get("clouds_max_offset_min", 120),
                }
                sr, ss, cloud = _apply_weather_adjustment(sr, ss, tmp_cfg)
                if cloud is not None:
                    cloud_line = (
                        f"<br>Облачность сейчас: <b>{cloud}%</b>. "
                        f"Времена ниже — по реальной освещённости (Open-Meteo)."
                    )
                else:
                    cloud_line = "<br>⚠ Не удалось получить погоду (нет интернета?). Работаем по чистому солнцу."

            sr2 = sr + timedelta(minutes=offset)
            ss2 = ss + timedelta(minutes=offset)
            self.sun_info_label.setText(
                f"Сегодня: восход {sr.strftime('%H:%M')} → светлая {sr2.strftime('%H:%M')} | "
                f"закат {ss.strftime('%H:%M')} → тёмная {ss2.strftime('%H:%M')}"
                + cloud_line
            )
        except Exception as e:
            self.sun_info_label.setText(f"⚠ Не удалось рассчитать: {e}")

    def _gather_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg["mode"] = self.mode_combo.currentData()
        cfg["city"] = self.city_combo.currentText()
        try:
            cfg["lat"] = float(self.lat_edit.text().replace(",", "."))
            cfg["lon"] = float(self.lon_edit.text().replace(",", "."))
        except ValueError:
            raise ValueError("Координаты должны быть числами (например, 55.7558).")
        if cfg["city"] in CITIES:
            cfg["tz"] = CITIES[cfg["city"]][2]
        cfg["offset_min"] = self.offset_spin.value()
        cfg["light_time"] = self.light_time_edit.time().toString("HH:mm")
        cfg["dark_time"] = self.dark_time_edit.time().toString("HH:mm")
        cfg["use_clouds"] = self.clouds_cb.isChecked()
        return cfg

    def _on_apply(self):
        try:
            self.cfg = self._gather_config()
        except ValueError as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            return
        save_config(self.cfg)
        set_autostart(self.autostart_cb.isChecked())
        self.tick()
        self._update_sun_info()
        self.tray.showMessage("Theme Switcher", "Настройки сохранены и применены.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def _manual_set(self, theme: str):
        set_theme(theme)
        self._update_status(theme, manual=True)

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        # При закрытии окна — прячем в трей, не выходим
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Theme Switcher",
            "Свернулся в трей. Двойной клик по иконке — открыть.",
            QSystemTrayIcon.MessageIcon.Information, 2000,
        )

    # ---------- основной цикл ----------
    def tick(self):
        try:
            target = determine_target_theme(self.cfg)
            current = get_current_theme()
            if target != current:
                set_theme(target)
            self._update_status(target)
            self._update_sun_info()
        except Exception as e:
            log.exception("Ошибка в tick: %s", e)

    def _update_status(self, theme: str, manual: bool = False):
        icon = "☀" if theme == "light" else "🌙"
        name = "Светлая" if theme == "light" else "Тёмная"
        suffix = "  (применено вручную)" if manual else ""
        mode = "по солнцу" if self.cfg["mode"] == "sun" else "по расписанию"
        # Эмодзи рендерим через Segoe UI Emoji — иначе они получаются монохромными.
        icon_html = f'<span style="font-family:\'Segoe UI Emoji\';">{icon}</span>'
        self.status_label.setText(
            f"{icon_html}  Активна тема: <b>{name}</b>{suffix}<br>"
            f"Режим: {mode}  •  проверка: {datetime.now().strftime('%H:%M:%S')}"
        )
        # Отмечаем активную кнопку солнце/луна рамкой акцентного цвета.
        for btn, key in ((self.light_btn, "light"), (self.dark_btn, "dark")):
            btn.setProperty("active", theme == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_app_icon())

    # Современный кросс-платформенный стиль + Fluent-палитра под Win11.
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    apply_app_theme(app)
    # При смене темы Windows (вручную или нашими же кнопками) — перерисоваться.
    app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply_app_theme(app))

    # Singleton: второй инстанс не нужен — с ним будет два процесса в трее,
    # конкурирующих за переключение темы.
    mutex = acquire_singleton_mutex()
    if mutex is None:
        log.info("Theme Switcher уже запущен — выходим")
        if "--tray" not in sys.argv:
            QMessageBox.information(
                None, "Theme Switcher",
                "Theme Switcher уже запущен. Найди иконку в трее (рядом с часами).",
            )
        sys.exit(0)
    # mutex держится в локальной переменной до конца main — освободится автоматически.

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Ошибка", "Системный трей недоступен.")
        sys.exit(1)

    win = MainWindow()

    # Подписка на WM_POWERBROADCAST — после wake форсим tick.
    power_filter = PowerEventFilter(on_resume=win.tick)
    app.installNativeEventFilter(power_filter)

    if "--tray" not in sys.argv:
        win.show()

    log.info("Theme Switcher запущен (tray=%s)", "--tray" in sys.argv)
    exit_code = app.exec()
    _kernel32.CloseHandle(mutex)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

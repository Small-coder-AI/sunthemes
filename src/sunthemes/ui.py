"""Окно настроек, трей и QSS-темы (Fluent-стиль под Win11).

Решения «какая тема и когда» принимает scheduler; тема Windows пишется
ТОЛЬКО через инжектированный theme_setter (поэтапный сеттер из app.py).
"""

import html
import importlib.resources
import logging
import time as _time
from datetime import datetime, timedelta

from PySide6.QtCore import QPointF, QTime, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox, QSystemTrayIcon,
    QTimeEdit, QVBoxLayout, QWidget,
)

from . import config, winapi
from .i18n import tr
from .scheduler import DARK, LIGHT, Status, SunPreview

log = logging.getLogger("sunthemes")

APP_DISPLAY_NAME = "Sunthemes"
WINDOW_WIDTH = 520
TICK_MS = 60_000
# После смены темы флаги дописываются поэтапно (~1.2 с): автоматическая
# проверка в это окно увидела бы «рассинхрон» и начала бы смену заново.
# Ручные кнопки это ожидание не касается.
SETTLE_SEC = 3.0


# ---------------------------------------------------------------------------
# Тема UI (светлая/тёмная палитра)
# ---------------------------------------------------------------------------

_PALETTES = {
    True: {   # тёмная
        "bg": "#202020", "surface": "#2c2c2c", "surf_hover": "#383838",
        "border": "#454545", "border_strong": "#5a5a5a",
        "text": "#f0f0f0", "text_dim": "#9a9a9a",
        "accent": "#4cc2ff", "accent_text": "#000000",
    },
    False: {  # светлая
        "bg": "#f3f3f3", "surface": "#ffffff", "surf_hover": "#f5f5f5",
        "border": "#cccccc", "border_strong": "#a8a8a8",
        "text": "#1a1a1a", "text_dim": "#5a5a5a",
        "accent": "#0067c0", "accent_text": "#ffffff",
    },
}


def _is_dark() -> bool:
    app = QApplication.instance()
    return app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark


# Версия в имени файла — чтобы изменённый рисунок не прятался за старым кешем.
_ARROW_POINTS = {
    "up": ((3, 11), (8, 5), (13, 11)),
    "down": ((3, 5), (8, 11), (13, 5)),
}


def _arrow_images(color: str) -> dict[str, str] | None:
    """Стрелки для спинбоксов: QSS берёт картинки только из файлов, поэтому
    они рисуются в каталог приложения. PNG, а не SVG: поддержка PNG встроена
    в Qt, а SVG требует плагина, которого может не оказаться в exe-сборке.
    None — не вышло (останутся стрелки по умолчанию)."""
    folder = config.APP_DIR / "ui"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        images = {}
        for name, points in _ARROW_POINTS.items():
            file = folder / f"arrow_{name}_{color.lstrip('#')}_v1.png"
            if not file.exists():
                # 16×16 при показе 8×8 — чёткие стрелки и на 200 % масштаба.
                pix = QPixmap(16, 16)
                pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                pen = QPen(QColor(color), 2.4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPolyline([QPointF(x, y) for x, y in points])
                painter.end()
                if not pix.save(str(file), "PNG"):
                    raise OSError(f"cannot save {file}")
            images[name] = file.as_posix()
        return images
    except OSError as e:
        log.warning("Cannot write spinbox arrows: %s", e)
        return None


def _spin_arrows_qss(images: dict[str, str] | None) -> str:
    if not images:
        return ""
    return f"""
        QSpinBox::up-button, QTimeEdit::up-button,
        QSpinBox::down-button, QTimeEdit::down-button {{
            subcontrol-origin: border;
            width: 22px;
            border: none;
            background: transparent;
        }}
        QSpinBox::up-button, QTimeEdit::up-button {{ subcontrol-position: top right; }}
        QSpinBox::down-button, QTimeEdit::down-button {{ subcontrol-position: bottom right; }}
        QSpinBox::up-arrow, QTimeEdit::up-arrow {{
            image: url("{images['up']}"); width: 8px; height: 8px;
        }}
        QSpinBox::down-arrow, QTimeEdit::down-arrow {{
            image: url("{images['down']}"); width: 8px; height: 8px;
        }}
    """


def _qss(is_dark: bool, arrows: dict[str, str] | None = None) -> str:
    """Таблица стилей под светлую или тёмную палитру Win11."""
    c = _PALETTES[is_dark]
    return _spin_arrows_qss(arrows) + f"""
        QWidget {{
            background: {c['bg']};
            color: {c['text']};
            font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            font-size: 10pt;
        }}
        QGroupBox {{
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            margin-top: 14px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            padding: 0 8px;
            background: {c['bg']};
            color: {c['text']};
        }}
        QGroupBox QLabel, QGroupBox QCheckBox {{
            font-weight: normal;
        }}
        QLabel {{
            background: transparent;
        }}
        QLabel#statusCard {{
            background: {c['surface']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            padding: 14px;
            font-size: 11pt;
        }}
        QLabel#dim {{
            color: {c['text_dim']};
        }}
        QLabel#sunInfo {{
            color: {c['text_dim']};
            padding-top: 4px;
        }}
        QLineEdit, QComboBox, QSpinBox, QTimeEdit {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 6px 10px;
            min-height: 22px;
            selection-background-color: {c['accent']};
            selection-color: {c['accent_text']};
        }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QTimeEdit:hover {{
            border-color: {c['border_strong']};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus {{
            border-color: {c['accent']};
        }}
        QLineEdit:read-only {{
            color: {c['text_dim']};
            background: {c['bg']};
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            selection-background-color: {c['accent']};
            selection-color: {c['accent_text']};
            outline: 0;
        }}
        QPushButton {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 8px 16px;
            min-height: 24px;
        }}
        QPushButton:hover {{ background: {c['surf_hover']}; border-color: {c['border_strong']}; }}
        QPushButton:pressed {{ background: {c['border']}; }}
        QPushButton#applyBtn {{
            background: {c['accent']};
            color: {c['accent_text']};
            border: 1px solid {c['accent']};
            font-weight: 600;
        }}
        QPushButton#applyBtn:hover {{ background: {c['accent']}; border: 1px solid {c['accent']}; }}
        QPushButton#applyBtn:pressed {{ background: {c['accent']}; }}
        QPushButton#themeBtn {{
            font-family: "Segoe UI Emoji", "Segoe UI Symbol", sans-serif;
            font-size: 18pt;
            min-width: 56px;
            max-width: 56px;
            min-height: 42px;
            padding: 0;
        }}
        QPushButton#themeBtn[active="true"] {{
            border: 2px solid {c['accent']};
            background: {c['surf_hover']};
        }}
        QCheckBox {{ spacing: 8px; }}
        QGroupBox QCheckBox {{ background: {c['surface']}; }}
        QToolTip {{
            background: {c['surface']};
            color: {c['text']};
            border: 1px solid {c['border']};
            padding: 4px 8px;
            border-radius: 4px;
        }}
    """


def apply_app_theme(app) -> None:
    """Подбирает QSS под текущую системную палитру (Light/Dark)."""
    is_dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    app.setStyleSheet(_qss(is_dark, _arrow_images(_PALETTES[is_dark]["text_dim"])))


def make_app_icon() -> QIcon:
    """icon.ico из ресурсов пакета; при отсутствии — рисованный запасной."""
    ico = importlib.resources.files("sunthemes") / "icon.ico"
    if ico.is_file():
        return QIcon(str(ico))
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#2c3e50"))       # тёмный полукруг — луна
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPie(8, 8, 48, 48, 90 * 16, 180 * 16)
    p.setBrush(QColor("#f1c40f"))       # светлый полукруг — солнце
    p.drawPie(8, 8, 48, 48, -90 * 16, 180 * 16)
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Форматирование времени (локальное время системы — как на часах Windows)
# ---------------------------------------------------------------------------

def _hhmm(moment: datetime) -> str:
    return moment.astimezone().strftime("%H:%M")


def _when(moment: datetime) -> str:
    """«в 18:02» / «завтра в 07:32» / «26.09 в 07:32»."""
    local = moment.astimezone()
    today = datetime.now().astimezone().date()
    hhmm = local.strftime("%H:%M")
    if local.date() == today:
        return tr("when.today", time=hhmm)
    if local.date() == today + timedelta(days=1):
        return tr("when.tomorrow", time=hhmm)
    return tr("when.date", date=local.strftime("%d.%m"), time=hhmm)


def _edge(moment: datetime, boundary: datetime) -> str:
    """Время границы окна; «—», если окно упирается в край солнечных суток."""
    return "—" if moment == boundary else _hhmm(moment)


def _minutes(delta: timedelta) -> int:
    return round(delta.total_seconds() / 60)


def _theme_name(theme: str) -> str:
    return tr("theme.light") if theme == LIGHT else tr("theme.dark")


def preview_lines(p: SunPreview) -> list[str]:
    """Строки подсказки «что будет сегодня» для режима по солнцу."""
    lines = []
    astro = p.astro
    if not astro.has_light:
        lines.append(tr("sun.polar_night"))
    elif astro.light_all_day:
        lines.append(tr("sun.polar_day"))
    else:
        lines.append(tr("sun.astro", sunrise=_edge(astro.light_from, astro.start),
                        sunset=_edge(astro.dark_from, astro.end)))

    plan, base = p.plan, p.base
    if not plan.has_light:
        lines.append(tr("sun.clouds_all_dark") if base.has_light else tr("sun.all_dark"))
    elif plan.light_all_day:
        lines.append(tr("sun.all_light"))
    else:
        lines.append(tr("sun.plan", light=_edge(plan.light_from, plan.start),
                        dark=_edge(plan.dark_from, plan.end)))

    if p.weather == "ok" and plan.has_light:
        details = []
        late = _minutes(plan.light_from - base.light_from)
        early = _minutes(base.dark_from - plan.dark_from)
        if late > 0:
            details.append(tr("sun.shift_morning", min=late))
        if early > 0:
            details.append(tr("sun.shift_evening", min=early))
        cloud = "—" if p.cloud_cover is None else f"{p.cloud_cover}%"
        lines.append(tr("sun.clouds_line", cloud=cloud,
                        details=", ".join(details) or tr("sun.no_shift")))
    elif p.weather == "loading":
        lines.append(tr("sun.clouds_loading"))
    elif p.weather == "failed":
        lines.append(tr("sun.no_weather"))
    return lines


# ---------------------------------------------------------------------------
# Окно
# ---------------------------------------------------------------------------

class MainWindow(QWidget):
    """Окно настроек и трей.

    scheduler — ThemeScheduler (решения); theme_setter — функция смены темы
    Windows. weather_updated можно испускать из любого потока (например, из
    колбэка WeatherProvider) — обработка уйдёт в GUI-поток."""

    weather_updated = Signal()

    def __init__(self, scheduler, theme_setter):
        super().__init__()
        self._scheduler = scheduler
        self._set_theme = theme_setter
        self._last_set = float("-inf")      # monotonic() последней записи темы
        self._last_status: Status | None = None
        self._loading = True
        self._minimize_hint_shown = False
        self._fit_pending = False
        self.cfg = config.load_config()

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowIcon(make_app_icon())
        self.setFixedWidth(WINDOW_WIDTH)

        self._build_ui()
        self._setup_tray()
        self._load_to_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.weather_updated.connect(self.tick)
        QApplication.instance().styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed)

    def start_ticking(self, initial_delay_ms: int) -> None:
        """Проверка раз в минуту; первая — через initial_delay_ms.

        Задержка нужна при автозапуске: переключение темы, пока оболочка
        Windows ещё прогружается, чаще всего ловит глюк полуперекрашенного
        интерфейса."""
        self.timer.start(TICK_MS)
        QTimer.singleShot(initial_delay_ms, self.tick)

    # ---------- построение UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusCard")
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_label.setWordWrap(True)
        self.status_label.linkActivated.connect(lambda _href: self._resume_auto())
        root.addWidget(self.status_label)

        # Режим
        mode_box = QGroupBox(tr("mode.group"))
        ml = QVBoxLayout(mode_box)
        ml.setContentsMargins(14, 18, 14, 14)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("mode.sun"), "sun")
        self.mode_combo.addItem(tr("mode.time"), "time")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ml.addWidget(self.mode_combo)
        root.addWidget(mode_box)

        root.addWidget(self._build_sun_box())

        # Параметры «по расписанию»
        self.time_box = QGroupBox(tr("time.group"))
        tl = QHBoxLayout(self.time_box)
        tl.setContentsMargins(14, 18, 14, 14)
        tl.addWidget(QLabel(tr("time.light_from")))
        self.light_time_edit = QTimeEdit()
        self.light_time_edit.setDisplayFormat("HH:mm")
        tl.addWidget(self.light_time_edit)
        tl.addSpacing(20)
        tl.addWidget(QLabel(tr("time.dark_from")))
        self.dark_time_edit = QTimeEdit()
        self.dark_time_edit.setDisplayFormat("HH:mm")
        tl.addWidget(self.dark_time_edit)
        tl.addStretch()
        root.addWidget(self.time_box)

        self.autostart_cb = QCheckBox(tr("autostart"))
        root.addWidget(self.autostart_cb)
        self.desktop_lnk_cb = QCheckBox(tr("desktop_shortcut"))
        root.addWidget(self.desktop_lnk_cb)

        # Кнопки
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.apply_btn = QPushButton(tr("btn.apply"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self._on_apply)
        bl.addWidget(self.apply_btn, 2)
        self.light_btn = self._theme_button("☀", "btn.light_tip", LIGHT)
        bl.addWidget(self.light_btn)
        self.dark_btn = self._theme_button("🌙", "btn.dark_tip", DARK)
        bl.addWidget(self.dark_btn)
        root.addLayout(bl)

    def _build_sun_box(self) -> QGroupBox:
        self.sun_box = QGroupBox(tr("sun.group"))
        sl = QVBoxLayout(self.sun_box)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(10)

        # Фиксированная ширина колонки лейблов — чтобы поля не съезжали.
        def row(label_key: str, *widgets) -> None:
            h = QHBoxLayout()
            lbl = QLabel(tr(label_key))
            lbl.setFixedWidth(76)
            h.addWidget(lbl)
            for w in widgets:
                if isinstance(w, tuple):
                    h.addWidget(*w)
                else:
                    h.addWidget(w)
            sl.addLayout(h)

        self.city_combo = QComboBox()
        for city_id in config.CITIES:
            self.city_combo.addItem(tr(f"city.{city_id}"), city_id)
        self.city_combo.addItem(tr("city.custom"), "custom")
        self.city_combo.currentIndexChanged.connect(self._on_city_changed)
        row("sun.city", (self.city_combo, 1))

        self.lat_edit = QLineEdit()
        self.lon_edit = QLineEdit()
        for edit in (self.lat_edit, self.lon_edit):
            edit.editingFinished.connect(self._update_preview)
        row("sun.lat", (self.lat_edit, 1), QLabel(tr("sun.lon")), (self.lon_edit, 1))

        self.morning_spin = self._elevation_spin()
        self.evening_spin = self._elevation_spin()
        for spin, label_key, hint_key in (
            (self.morning_spin, "sun.morning", "sun.morning_hint"),
            (self.evening_spin, "sun.evening", "sun.evening_hint"),
        ):
            hint = QLabel(tr(hint_key))
            hint.setObjectName("dim")
            row(label_key, spin, (hint, 1))

        help_label = QLabel(tr("sun.elevation_help"))
        help_label.setObjectName("dim")
        help_label.setWordWrap(True)
        sl.addWidget(help_label)

        self.clouds_cb = QCheckBox(tr("sun.clouds"))
        self.clouds_cb.toggled.connect(self._update_preview)
        sl.addWidget(self.clouds_cb)

        self.sun_info_label = QLabel()
        self.sun_info_label.setObjectName("sunInfo")
        self.sun_info_label.setTextFormat(Qt.TextFormat.RichText)
        self.sun_info_label.setWordWrap(True)
        sl.addWidget(self.sun_info_label)
        return self.sun_box

    def _elevation_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(config.ELEVATION_MIN, config.ELEVATION_MAX)
        spin.setSuffix("°")
        spin.setFixedWidth(84)
        spin.valueChanged.connect(self._update_preview)
        return spin

    def _theme_button(self, glyph: str, tip_key: str, theme: str) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setObjectName("themeBtn")
        btn.setToolTip(tr(tip_key))
        btn.clicked.connect(lambda: self._manual_set(theme))
        return btn

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu(self)

        def action(key: str, slot) -> QAction:
            a = QAction(tr(key), self)
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        action("tray.open", self._show_window)
        menu.addSeparator()
        action("tray.light", lambda: self._manual_set(LIGHT))
        action("tray.dark", lambda: self._manual_set(DARK))
        self.auto_action = action("tray.auto", self._resume_auto)
        self.auto_action.setVisible(False)
        menu.addSeparator()
        action("tray.quit", QApplication.instance().quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ---------- наполнение из конфига ----------
    def _load_to_ui(self):
        self._loading = True
        cfg = self.cfg
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(cfg["mode"])))
        self.city_combo.setCurrentIndex(max(0, self.city_combo.findData(cfg["city"])))
        self.lat_edit.setText(str(cfg["lat"]))
        self.lon_edit.setText(str(cfg["lon"]))
        self.morning_spin.setValue(round(cfg["morning_elevation"]))
        self.evening_spin.setValue(round(cfg["evening_elevation"]))
        self.light_time_edit.setTime(QTime.fromString(cfg["light_time"], "HH:mm"))
        self.dark_time_edit.setTime(QTime.fromString(cfg["dark_time"], "HH:mm"))
        self.clouds_cb.setChecked(cfg["use_clouds"])
        self.clouds_cb.setToolTip(tr("sun.clouds_tip", max=cfg["clouds_max_offset_min"]))
        try:
            self.autostart_cb.setChecked(winapi.is_autostart_enabled())
        except OSError as e:
            log.warning("Autostart state: %s", e)
        # Состояние чекбокса — это факт существования файла ярлыка.
        try:
            self.desktop_lnk_cb.setChecked(winapi.desktop_shortcut_path().exists())
        except OSError:
            self.desktop_lnk_cb.setEnabled(False)
        self._loading = False
        self._on_mode_changed()
        self._on_city_changed()

    # ---------- обработчики формы ----------
    def _on_mode_changed(self):
        is_sun = self.mode_combo.currentData() == "sun"
        self.sun_box.setVisible(is_sun)
        self.time_box.setVisible(not is_sun)
        self._update_preview()
        self._fit_height()

    def _on_city_changed(self):
        city_id = self.city_combo.currentData()
        preset = city_id in config.CITIES
        self.lat_edit.setReadOnly(preset)
        self.lon_edit.setReadOnly(preset)
        if preset:
            lat, lon = config.CITIES[city_id]
            self.lat_edit.setText(str(lat))
            self.lon_edit.setText(str(lon))
        self._update_preview()

    def _form_config(self) -> dict:
        """Конфиг из полей формы; ValueError с понятным текстом при ошибке."""
        cfg = dict(self.cfg)
        cfg["mode"] = self.mode_combo.currentData()
        cfg["city"] = self.city_combo.currentData()
        if cfg["city"] in config.CITIES:
            cfg["lat"], cfg["lon"] = config.CITIES[cfg["city"]]
        else:
            try:
                lat = float(self.lat_edit.text().replace(",", "."))
                lon = float(self.lon_edit.text().replace(",", "."))
            except ValueError:
                raise ValueError(tr("err.coords")) from None
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(tr("err.coords_range"))
            cfg["lat"], cfg["lon"] = lat, lon
        cfg["morning_elevation"] = self.morning_spin.value()
        cfg["evening_elevation"] = self.evening_spin.value()
        cfg["light_time"] = self.light_time_edit.time().toString("HH:mm")
        cfg["dark_time"] = self.dark_time_edit.time().toString("HH:mm")
        cfg["use_clouds"] = self.clouds_cb.isChecked()
        return cfg

    def _update_preview(self):
        """Подсказка «что будет сегодня» по ещё не сохранённым полям формы."""
        if self._loading or self.mode_combo.currentData() != "sun":
            return
        try:
            lines = preview_lines(self._scheduler.preview(self._form_config()))
            text = "<br>".join(lines)
        except ValueError as e:
            text = "⚠ " + html.escape(str(e))
        except Exception as e:
            log.exception("Preview failed")
            text = html.escape(tr("sun.calc_error", error=e))
        if text != self.sun_info_label.text():
            self.sun_info_label.setText(text)
            self._fit_height()

    def _fit_height(self):
        """Высота окна — по содержимому: блоки режимов скрываются, подсказка
        и статус меняют число строк. Пересчёт откладывается до обработки
        событий раскладки — иначе кеш размеров ещё старый, и нижние строки
        обрезаются."""
        if not self._fit_pending:
            self._fit_pending = True
            QTimer.singleShot(0, self._do_fit_height)

    def _do_fit_height(self):
        self._fit_pending = False
        self.ensurePolished()
        self.layout().activate()
        height = self.heightForWidth(WINDOW_WIDTH)
        self.setFixedHeight(height if height > 0 else self.sizeHint().height())

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_height()

    def _on_apply(self):
        try:
            cfg = self._form_config()
        except ValueError as e:
            QMessageBox.warning(self, tr("err.title"), str(e))
            return
        try:
            config.save_config(cfg)
        except OSError as e:
            log.error("Cannot save config: %s", e)
            QMessageBox.warning(self, tr("err.title"), str(e))
            return
        self.cfg = cfg
        try:
            winapi.set_autostart(self.autostart_cb.isChecked())
        except OSError as e:
            log.warning("Autostart: %s", e)
        self._apply_desktop_shortcut(self.desktop_lnk_cb.isChecked())
        self.clouds_cb.setToolTip(tr("sun.clouds_tip", max=cfg["clouds_max_offset_min"]))
        # Новые настройки — новое расписание: ручной выбор больше не нужен.
        self._scheduler.clear_manual()
        self.tick(force=True)
        self.tray.showMessage(APP_DISPLAY_NAME, tr("tray.saved"),
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def _apply_desktop_shortcut(self, want: bool) -> None:
        """Создать или удалить ярлык на рабочем столе по чекбоксу."""
        try:
            lnk = winapi.desktop_shortcut_path()
            if want:
                winapi.create_app_shortcut(
                    lnk, config.ensure_app_icon(), tr("shortcut.description"))
            else:
                lnk.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Desktop shortcut: %s", e)

    # ---------- тема ----------
    def _apply(self, theme: str) -> bool:
        """Записать тему, если в реестре другая (или флаги рассинхронены —
        остаток сбоя прошлой смены; полная поэтапная запись выравнивает оба)."""
        if theme == winapi.get_current_theme() and winapi.theme_flags_in_sync():
            return False
        self._set_theme(theme)
        self._last_set = _time.monotonic()
        return True

    def tick(self, force: bool = False):
        """Проверка по расписанию. force — действие пользователя: применить
        сразу, не дожидаясь окончания поэтапной записи прошлой смены."""
        try:
            status = self._scheduler.evaluate(self.cfg)
            if force or _time.monotonic() - self._last_set >= SETTLE_SEC:
                self._apply(status.theme)
            self._show_status(status)
            if self.isVisible():        # скрытому окну подсказка не нужна
                self._update_preview()
        except Exception:
            log.exception("tick failed")

    def _manual_set(self, theme: str):
        try:
            self._scheduler.set_manual(theme, self.cfg)
            status = self._scheduler.evaluate(self.cfg)
            self._apply(status.theme)
            self._show_status(status)
        except Exception:
            log.exception("Manual switch failed")

    def _resume_auto(self):
        self._scheduler.clear_manual()
        self.tick(force=True)

    def _on_color_scheme_changed(self, _scheme):
        # Цвета в HTML статуса зависят от палитры — перерисовать.
        if self._last_status is not None:
            self._show_status(self._last_status)

    # ---------- статус ----------
    def _show_status(self, st: Status):
        self._last_status = st
        colors = _PALETTES[_is_dark()]
        if st.manual:
            line = (tr("status.manual", when=_when(st.next_switch))
                    if st.next_switch else tr("status.manual_no_end"))
            link = (f' · <a href="auto" style="color:{colors["accent"]};">'
                    f'{tr("status.resume")}</a>')
        elif st.next_switch is not None:
            to = tr("switch.to_light") if st.next_theme == LIGHT else tr("switch.to_dark")
            line, link = tr("status.next", to=to, when=_when(st.next_switch)), ""
        else:
            line, link = tr("status.no_switch"), ""

        icon = "☀" if st.theme == LIGHT else "🌙"
        mode = tr("mode.sun_short") if self.cfg["mode"] == "sun" else tr("mode.time_short")
        checked = tr("status.checked", time=datetime.now().strftime("%H:%M:%S"))
        # Эмодзи через Segoe UI Emoji — иначе рендерятся монохромными.
        self.status_label.setText(
            f'<span style="font-family:\'Segoe UI Emoji\';">{icon}</span>&nbsp; '
            f'{tr("status.active_theme")}: <b>{_theme_name(st.theme)}</b><br>'
            f'{html.escape(line)}{link}<br>'
            f'<span style="color:{colors["text_dim"]}; font-size:9pt;">'
            f'{mode} · {checked}</span>'
        )
        self.tray.setToolTip(
            f"{APP_DISPLAY_NAME}\n{tr('status.active_theme')}: "
            f"{_theme_name(st.theme)}\n{line}")
        self.auto_action.setVisible(st.manual)
        self._fit_height()
        for btn, key in ((self.light_btn, LIGHT), (self.dark_btn, DARK)):
            btn.setProperty("active", st.theme == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ---------- окно и трей ----------
    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _show_window(self):
        self._update_preview()
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        # Закрытие окна — сворачивание в трей, не выход.
        event.ignore()
        self.hide()
        if not self._minimize_hint_shown:
            self._minimize_hint_shown = True
            self.tray.showMessage(APP_DISPLAY_NAME, tr("tray.minimized"),
                                  QSystemTrayIcon.MessageIcon.Information, 2000)

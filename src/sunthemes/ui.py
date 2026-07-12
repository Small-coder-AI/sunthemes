"""Окно настроек, трей и QSS-темы (Fluent-стиль под Win11)."""

import importlib.resources
import logging
from datetime import datetime, timedelta

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox,
    QSystemTrayIcon, QTimeEdit, QVBoxLayout, QWidget,
)

from . import config, suncalc, winapi
from .i18n import tr

log = logging.getLogger("sunthemes")

APP_DISPLAY_NAME = "Sunthemes"


# ---------------------------------------------------------------------------
# Тема UI (светлая/тёмная палитра)
# ---------------------------------------------------------------------------

def _qss(is_dark: bool) -> str:
    """Таблица стилей под светлую или тёмную палитру Win11."""
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
    """Подбирает QSS под текущую системную палитру (Light/Dark)."""
    scheme = app.styleHints().colorScheme()
    app.setStyleSheet(_qss(scheme == Qt.ColorScheme.Dark))


def make_app_icon() -> QIcon:
    """icon.ico из ресурсов пакета; при отсутствии — рисованный запасной."""
    ico = importlib.resources.files("sunthemes") / "icon.ico"
    try:
        return QIcon(str(ico))
    except OSError:
        pass
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


class MainWindow(QMainWindow):
    """Окно настроек. theme_setter — функция смены темы Windows
    (поэтапный сеттер из app.py: два флага с паузой + повторный broadcast)."""

    def __init__(self, theme_setter):
        super().__init__()
        self._set_theme = theme_setter
        self.cfg = config.load_config()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setFixedSize(500, 680)
        self.setWindowIcon(make_app_icon())

        self._build_ui()
        self._load_to_ui()
        self._setup_tray()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start_ticking(self, initial_delay_ms: int) -> None:
        """Проверка раз в минуту; первая — через initial_delay_ms.

        Задержка нужна при автозапуске: переключение темы, пока оболочка
        Windows ещё прогружается, чаще всего ловит глюк полуперекрашенного
        интерфейса."""
        self.timer.start(60_000)
        QTimer.singleShot(initial_delay_ms, self.tick)

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
        mode_box = QGroupBox(tr("mode.group"))
        ml = QVBoxLayout(mode_box)
        ml.setContentsMargins(14, 18, 14, 14)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("mode.sun"), "sun")
        self.mode_combo.addItem(tr("mode.time"), "time")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ml.addWidget(self.mode_combo)
        root.addWidget(mode_box)

        # Параметры «по солнцу»
        self.sun_box = QGroupBox(tr("sun.group"))
        sl = QVBoxLayout(self.sun_box)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(10)

        # Фиксированная ширина колонки лейблов — чтобы поля не съезжали.
        LABEL_W = 76

        def _label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setFixedWidth(LABEL_W)
            return lbl

        h1 = QHBoxLayout()
        h1.addWidget(_label(tr("sun.city")))
        self.city_combo = QComboBox()
        for city_id in config.CITIES:
            self.city_combo.addItem(tr(f"city.{city_id}"), city_id)
        self.city_combo.addItem(tr("city.custom"), "custom")
        self.city_combo.currentIndexChanged.connect(self._on_city_changed)
        h1.addWidget(self.city_combo, 1)
        sl.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(_label(tr("sun.lat")))
        self.lat_edit = QLineEdit()
        h2.addWidget(self.lat_edit, 1)
        h2.addWidget(QLabel(tr("sun.lon")))
        self.lon_edit = QLineEdit()
        h2.addWidget(self.lon_edit, 1)
        sl.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(_label(tr("sun.offset")))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-180, 180)
        self.offset_spin.setSuffix(tr("sun.offset_suffix"))
        h3.addWidget(self.offset_spin)
        hint = QLabel(tr("sun.offset_hint"))
        hint.setObjectName("sunInfo")
        h3.addWidget(hint)
        h3.addStretch()
        sl.addLayout(h3)

        self.clouds_cb = QCheckBox(tr("sun.clouds"))
        self.clouds_cb.toggled.connect(self._update_sun_info)
        sl.addWidget(self.clouds_cb)

        self.sun_info_label = QLabel()
        self.sun_info_label.setObjectName("sunInfo")
        self.sun_info_label.setWordWrap(True)
        sl.addWidget(self.sun_info_label)
        root.addWidget(self.sun_box)

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

        # Кнопки
        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.apply_btn = QPushButton(tr("btn.apply"))
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self._on_apply)
        bl.addWidget(self.apply_btn, 2)

        self.light_btn = QPushButton("☀")
        self.light_btn.setObjectName("themeBtn")
        self.light_btn.setToolTip(tr("btn.light_tip"))
        self.light_btn.clicked.connect(lambda: self._manual_set("light"))
        bl.addWidget(self.light_btn)

        self.dark_btn = QPushButton("🌙")
        self.dark_btn.setObjectName("themeBtn")
        self.dark_btn.setToolTip(tr("btn.dark_tip"))
        self.dark_btn.clicked.connect(lambda: self._manual_set("dark"))
        bl.addWidget(self.dark_btn)
        root.addLayout(bl)

        root.addStretch()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(APP_DISPLAY_NAME)
        menu = QMenu()

        a_show = QAction(tr("tray.open"), self)
        a_show.triggered.connect(self._show_window)
        menu.addAction(a_show)
        menu.addSeparator()

        a_light = QAction(tr("tray.light"), self)
        a_light.triggered.connect(lambda: self._manual_set("light"))
        menu.addAction(a_light)

        a_dark = QAction(tr("tray.dark"), self)
        a_dark.triggered.connect(lambda: self._manual_set("dark"))
        menu.addAction(a_dark)

        menu.addSeparator()
        a_quit = QAction(tr("tray.quit"), self)
        a_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(a_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ---------- наполнение из конфига ----------
    def _load_to_ui(self):
        idx = self.mode_combo.findData(self.cfg["mode"])
        self.mode_combo.setCurrentIndex(max(0, idx))

        # Миграция: старые конфиги хранили русское название («Москва»),
        # неизвестные города («Истра») превращаются в «Свои координаты»
        # с сохранением lat/lon/tz пользователя.
        city_id = config.resolve_city_id(self.cfg)
        idx = self.city_combo.findData(city_id)
        self.city_combo.setCurrentIndex(max(0, idx))

        self.lat_edit.setText(str(self.cfg["lat"]))
        self.lon_edit.setText(str(self.cfg["lon"]))
        self.offset_spin.setValue(self.cfg.get("offset_min", 0))

        self.light_time_edit.setTime(QTime.fromString(self.cfg["light_time"], "HH:mm"))
        self.dark_time_edit.setTime(QTime.fromString(self.cfg["dark_time"], "HH:mm"))

        self.clouds_cb.setChecked(bool(self.cfg.get("use_clouds", False)))
        self.autostart_cb.setChecked(winapi.is_autostart_enabled())

        self._on_mode_changed()
        self._on_city_changed()

    # ---------- обработчики ----------
    def _on_mode_changed(self):
        is_sun = self.mode_combo.currentData() == "sun"
        self.sun_box.setVisible(is_sun)
        self.time_box.setVisible(not is_sun)
        if is_sun and not suncalc.ASTRAL_OK:
            self.sun_info_label.setText(tr("sun.no_astral"))

    def _current_tz(self) -> str:
        """Таймзона выбранного пресета или из конфига (для своих координат)."""
        city_id = self.city_combo.currentData()
        if city_id in config.CITIES:
            return config.CITIES[city_id][2]
        return self.cfg.get("tz", "Europe/Moscow")

    def _on_city_changed(self):
        city_id = self.city_combo.currentData()
        custom = city_id == "custom"
        self.lat_edit.setReadOnly(not custom)
        self.lon_edit.setReadOnly(not custom)
        if not custom and city_id in config.CITIES:
            lat, lon, _tz = config.CITIES[city_id]
            self.lat_edit.setText(str(lat))
            self.lon_edit.setText(str(lon))
        self._update_sun_info()

    def _update_sun_info(self):
        if not suncalc.ASTRAL_OK:
            return
        try:
            lat = float(self.lat_edit.text())
            lon = float(self.lon_edit.text())
            tz = self._current_tz()
            sr, ss = suncalc.compute_sun_times(lat, lon, tz)
            if not (sr and ss):
                return
            offset = self.offset_spin.value()

            cloud_line = ""
            if self.clouds_cb.isChecked():
                tmp_cfg = {
                    "lat": lat, "lon": lon, "tz": tz, "use_clouds": True,
                    "clouds_max_offset_min": self.cfg.get("clouds_max_offset_min", 120),
                }
                # Работает по кешу; свежие данные подтянет фоновый поток к
                # следующему tick.
                suncalc.weather.refresh_in_background(lat, lon, tz)
                sr, ss, cloud = suncalc.apply_weather_adjustment(sr, ss, tmp_cfg)
                if cloud is not None:
                    cloud_line = tr("sun.cloud_line", cloud=cloud)
                else:
                    cloud_line = tr("sun.no_weather")

            sr2 = sr + timedelta(minutes=offset)
            ss2 = ss + timedelta(minutes=offset)
            self.sun_info_label.setText(
                tr("sun.today",
                   sr=sr.strftime("%H:%M"), sr2=sr2.strftime("%H:%M"),
                   ss=ss.strftime("%H:%M"), ss2=ss2.strftime("%H:%M"))
                + cloud_line
            )
        except Exception as e:
            self.sun_info_label.setText(tr("sun.calc_error", error=e))

    def _gather_config(self) -> dict:
        cfg = dict(self.cfg)
        cfg["mode"] = self.mode_combo.currentData()
        cfg["city"] = self.city_combo.currentData()
        try:
            cfg["lat"] = float(self.lat_edit.text().replace(",", "."))
            cfg["lon"] = float(self.lon_edit.text().replace(",", "."))
        except ValueError:
            raise ValueError(tr("err.coords"))
        if cfg["city"] in config.CITIES:
            cfg["tz"] = config.CITIES[cfg["city"]][2]
        cfg["offset_min"] = self.offset_spin.value()
        cfg["light_time"] = self.light_time_edit.time().toString("HH:mm")
        cfg["dark_time"] = self.dark_time_edit.time().toString("HH:mm")
        cfg["use_clouds"] = self.clouds_cb.isChecked()
        return cfg

    def _on_apply(self):
        try:
            self.cfg = self._gather_config()
        except ValueError as e:
            QMessageBox.warning(self, tr("err.title"), str(e))
            return
        config.save_config(self.cfg)
        winapi.set_autostart(self.autostart_cb.isChecked())
        self.tick()
        self._update_sun_info()
        self.tray.showMessage(APP_DISPLAY_NAME, tr("tray.saved"),
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    def _manual_set(self, theme: str):
        self._set_theme(theme)
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
        # Закрытие окна — сворачивание в трей, не выход.
        event.ignore()
        self.hide()
        self.tray.showMessage(APP_DISPLAY_NAME, tr("tray.minimized"),
                              QSystemTrayIcon.MessageIcon.Information, 2000)

    # ---------- основной цикл ----------
    def tick(self):
        try:
            if self.cfg.get("use_clouds"):
                # Обновление кеша погоды — в фоне, tick не блокируется.
                suncalc.weather.refresh_in_background(
                    self.cfg["lat"], self.cfg["lon"], self.cfg["tz"])
            target = suncalc.determine_target_theme(self.cfg)
            current = winapi.get_current_theme()
            if target != current:
                self._set_theme(target)
            self._update_status(target)
            self._update_sun_info()
        except Exception as e:
            log.exception("tick failed: %s", e)

    def _update_status(self, theme: str, manual: bool = False):
        icon = "☀" if theme == "light" else "🌙"
        name = tr("theme.light") if theme == "light" else tr("theme.dark")
        suffix = tr("status.manual_suffix") if manual else ""
        mode = tr("mode.sun_short") if self.cfg["mode"] == "sun" else tr("mode.time_short")
        # Эмодзи через Segoe UI Emoji — иначе рендерятся монохромными.
        icon_html = f'<span style="font-family:\'Segoe UI Emoji\';">{icon}</span>'
        self.status_label.setText(
            f"{icon_html}  {tr('status.active_theme')}: <b>{name}</b>{suffix}<br>"
            f"{tr('status.mode')}: {mode}  •  {tr('status.checked')}: "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        for btn, key in ((self.light_btn, "light"), (self.dark_btn, "dark")):
            btn.setProperty("active", theme == key)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

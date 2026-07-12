"""Точка входа: сборка приложения, поэтапная смена темы, power-события."""

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import config, i18n, ui, winapi

log = logging.getLogger("sunthemes")

# Первая проверка темы при автозапуске откладывается: смена темы в момент
# прогрузки оболочки Windows чаще всего ловит глюк полуперекрашенного UI.
TRAY_STARTUP_DELAY_MS = 15_000


def switch_theme_staged(theme: str) -> None:
    """Поэтапная смена темы Windows — смягчение глюка «тёмный текст на
    тёмном фоне»: флаги пишутся по одному с паузой, broadcast после
    каждого и ещё раз через секунду. Гарантии нет (баг оболочки), но
    частота глюка заметно ниже, чем при записи двух флагов залпом."""
    light = theme == "light"
    winapi.write_theme_flag("AppsUseLightTheme", light)
    winapi.broadcast_theme_change()

    def _second_flag():
        winapi.write_theme_flag("SystemUsesLightTheme", light)
        winapi.broadcast_theme_change()

    QTimer.singleShot(100, _second_flag)
    QTimer.singleShot(1200, winapi.broadcast_theme_change)
    log.info("Theme switched to %s", theme)


class PowerEventFilter(QAbstractNativeEventFilter):
    """WM_POWERBROADCAST: после выхода из сна тема догоняется сразу,
    а не через минуту по обычному tick."""

    def __init__(self, on_resume):
        super().__init__()
        self._on_resume = on_resume

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == winapi.WM_POWERBROADCAST and msg.wParam in (
                winapi.PBT_APMRESUMESUSPEND, winapi.PBT_APMRESUMEAUTOMATIC,
            ):
                log.info("Wake from sleep — forcing theme check")
                self._on_resume()
        return False


def _log_unhandled(exc_type, exc, tb):
    """Неперехваченное исключение — в лог, затем стандартная печать.
    Иначе падение оставляет пустой лог и его не отладить post-mortem."""
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


def main() -> None:
    config.setup_logging()
    sys.excepthook = _log_unhandled

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(ui.APP_DISPLAY_NAME)
    app.setWindowIcon(ui.make_app_icon())

    i18n.set_language(winapi.get_ui_language())

    # Современный стиль + Fluent-палитра; перерисовка при смене темы ОС.
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI Variable", 10))
    ui.apply_app_theme(app)
    app.styleHints().colorSchemeChanged.connect(lambda _s: ui.apply_app_theme(app))

    tray_mode = "--tray" in sys.argv

    # Singleton: второй экземпляр конкурировал бы за переключение темы.
    mutex = winapi.acquire_singleton_mutex()
    if mutex is None:
        log.info("Sunthemes is already running — exiting")
        if not tray_mode:
            QMessageBox.information(
                None, ui.APP_DISPLAY_NAME, i18n.tr("msg.already_running"))
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, i18n.tr("err.title"), i18n.tr("err.no_tray"))
        sys.exit(1)

    win = ui.MainWindow(theme_setter=switch_theme_staged)

    power_filter = PowerEventFilter(on_resume=win.tick)
    app.installNativeEventFilter(power_filter)

    if not tray_mode:
        win.show()
    win.start_ticking(TRAY_STARTUP_DELAY_MS if tray_mode else 0)

    log.info("Sunthemes started (tray=%s)", tray_mode)
    exit_code = app.exec()
    log.info("Sunthemes exited (code=%s)", exit_code)
    winapi.close_handle(mutex)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

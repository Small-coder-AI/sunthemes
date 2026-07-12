"""Windows-специфика: реестр темы, broadcast, mutex, автозагрузка, язык UI.

Модуль предоставляет атомарные операции; последовательность «поэтапной»
смены темы (два флага с паузой) координирует app.py — здесь нет ни Qt,
ни задержек.
"""

import ctypes
import logging
import shutil
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from .config import APP_NAME

log = logging.getLogger("sunthemes")

THEMES_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002

# Power management — для отслеживания выхода из сна (используется в app.py).
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMESUSPEND = 0x0007    # явное пробуждение пользователем
PBT_APMRESUMEAUTOMATIC = 0x0012  # автопробуждение (таймер/событие)

# В ctypes.wintypes нет LRESULT и DWORD_PTR — определяем вручную.
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

_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.GetLastError.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
ERROR_ALREADY_EXISTS = 183


# --- тема ---

def get_current_theme() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEMES_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if value == 1 else "dark"
    except OSError:
        return "light"


def write_theme_flag(value_name: str, light: bool) -> None:
    """Записать один флаг темы: 'AppsUseLightTheme' | 'SystemUsesLightTheme'."""
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, THEMES_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, 1 if light else 0)


def broadcast_theme_change() -> None:
    result = DWORD_PTR()
    _SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet",
        SMTO_ABORTIFHUNG, 1000, ctypes.byref(result),
    )


# --- singleton ---

def acquire_singleton_mutex(name: str = "ThemeSwitcher_singleton_v1"):
    """Handle именованного мьютекса (держать до выхода) или None, если
    другой экземпляр уже работает. ОС освободит handle при смерти процесса."""
    handle = _kernel32.CreateMutexW(None, False, name)
    if not handle:
        return None
    if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return None
    return handle


def close_handle(handle) -> None:
    _kernel32.CloseHandle(handle)


# --- автозагрузка ---

def autostart_command() -> str:
    """Команда для HKCU\\...\\Run.

    Приоритет: запущенный .exe (шим uv/venv) → шим `sunthemes` в PATH →
    dev-fallback: pythonw.exe + текущий скрипт."""
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.suffix.lower() == ".exe":
        return f'"{argv0}" --tray'
    shim = shutil.which("sunthemes")
    if shim:
        return f'"{Path(shim).resolve()}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    # Запуск скрипта напрямую (argv0) ломает относительные импорты пакета —
    # используем `-m sunthemes`, как при штатном запуске `python -m sunthemes`.
    return f'"{exe}" -m sunthemes --tray'


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
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# --- язык системы ---

def get_ui_language() -> str:
    """'ru' для русской Windows, иначе 'en' (по языку UI пользователя)."""
    LANG_RUSSIAN = 0x19
    try:
        langid = _kernel32.GetUserDefaultUILanguage()
        return "ru" if (langid & 0x3FF) == LANG_RUSSIAN else "en"
    except Exception:
        return "en"

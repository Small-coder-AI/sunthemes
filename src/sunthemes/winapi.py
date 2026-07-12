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


def theme_flags_in_sync() -> bool:
    """True, если оба флага темы согласованы (или их не прочитать).

    Рассинхрон (приложения светлые, оболочка тёмная) остаётся после сбоя
    посреди прошлой поэтапной смены — tick форсирует полную перезапись."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, THEMES_KEY) as key:
            apps, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            system, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
        return bool(apps) == bool(system)
    except OSError:
        return True


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

def launcher() -> tuple[str, str]:
    """(программа, аргументы) для запуска приложения — без --tray.

    Приоритет: запущенный .exe (шим uv/venv) → шим `sunthemes` в PATH →
    dev-fallback: pythonw.exe + `-m sunthemes`."""
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.suffix.lower() == ".exe":
        return str(argv0), ""
    shim = shutil.which("sunthemes")
    if shim:
        return str(Path(shim).resolve()), ""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    # Запуск скрипта напрямую (argv0) ломает относительные импорты пакета —
    # используем `-m sunthemes`, как при штатном запуске `python -m sunthemes`.
    return str(exe), "-m sunthemes"


def autostart_command() -> str:
    """Команда для HKCU\\...\\Run (в трей, без окна)."""
    exe, args = launcher()
    all_args = f"{args} --tray".strip()
    return f'"{exe}" {all_args}'


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


# --- known folders и ярлыки (.lnk) ---
# Ярлык создаётся через COM IShellLinkW на чистом ctypes: PowerShell может
# быть запрещён политикой, WSH — отключён, а COM-интерфейс есть всегда.

_ole32 = ctypes.windll.ole32
_shell32 = ctypes.windll.shell32

# Known Folders надёжнее %USERPROFILE%\Desktop: рабочий стол бывает
# перенесён (OneDrive, перенаправление профиля).
FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_PROGRAMS = "{A77F5D77-2E2B-44C3-A6A2-ABA601054A51}"

_CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 2

SHORTCUT_NAME = "Sunthemes.lnk"

_HRESULT = ctypes.c_long


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(s: str) -> _GUID:
    g = _GUID()
    if _ole32.CLSIDFromString(s, ctypes.byref(g)) != 0:
        raise OSError(f"Bad GUID: {s}")
    return g


def known_folder_path(folder_guid: str) -> Path:
    """Путь Known Folder текущего пользователя (SHGetKnownFolderPath)."""
    fid = _guid(folder_guid)
    out = ctypes.c_wchar_p()
    hr = _shell32.SHGetKnownFolderPath(
        ctypes.byref(fid), 0, None, ctypes.byref(out))
    if hr != 0:
        raise OSError(f"SHGetKnownFolderPath({folder_guid}): 0x{hr & 0xFFFFFFFF:08X}")
    try:
        return Path(out.value)
    finally:
        _ole32.CoTaskMemFree(out)


def _com_call(obj, vtbl_index: int, *args, argtypes=()):
    """Вызов метода COM-объекта по индексу vtable; отрицательный HRESULT → OSError."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(_HRESULT, ctypes.c_void_p, *argtypes)
    hr = proto(vtbl[vtbl_index])(obj, *args)
    if hr < 0:
        raise OSError(f"COM method #{vtbl_index} failed: 0x{hr & 0xFFFFFFFF:08X}")
    return hr


def _com_release(obj) -> None:
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])(obj)  # IUnknown::Release


def create_shortcut(
    lnk_path: Path, target: str, arguments: str = "",
    icon_path: Path | None = None, description: str = "",
) -> None:
    """Создать или перезаписать ярлык .lnk.

    Повторный CoInitializeEx в GUI-потоке Qt безопасен (вернёт S_FALSE);
    CoUninitialize не зовём — COM нужен Qt до конца работы процесса."""
    _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    link = ctypes.c_void_p()
    hr = _ole32.CoCreateInstance(
        ctypes.byref(_guid(_CLSID_SHELL_LINK)), None, _CLSCTX_INPROC_SERVER,
        ctypes.byref(_guid(_IID_ISHELL_LINK_W)), ctypes.byref(link))
    if hr < 0:
        raise OSError(f"CoCreateInstance(ShellLink): 0x{hr & 0xFFFFFFFF:08X}")
    LPCWSTR = wintypes.LPCWSTR
    try:
        # Индексы vtable IShellLinkW: 7 SetDescription, 9 SetWorkingDirectory,
        # 11 SetArguments, 17 SetIconLocation, 20 SetPath.
        _com_call(link, 20, target, argtypes=(LPCWSTR,))
        _com_call(link, 11, arguments, argtypes=(LPCWSTR,))
        _com_call(link, 9, str(Path(target).parent), argtypes=(LPCWSTR,))
        if description:
            _com_call(link, 7, description, argtypes=(LPCWSTR,))
        if icon_path is not None:
            _com_call(link, 17, str(icon_path), 0, argtypes=(LPCWSTR, ctypes.c_int))
        pf = ctypes.c_void_p()
        _com_call(link, 0, ctypes.byref(_guid(_IID_IPERSIST_FILE)), ctypes.byref(pf),
                  argtypes=(ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)))
        try:
            _com_call(pf, 6, str(lnk_path), True,
                      argtypes=(LPCWSTR, wintypes.BOOL))  # IPersistFile::Save
        finally:
            _com_release(pf)
    finally:
        _com_release(link)


def desktop_shortcut_path() -> Path:
    return known_folder_path(FOLDERID_DESKTOP) / SHORTCUT_NAME


def start_menu_shortcut_path() -> Path:
    return known_folder_path(FOLDERID_PROGRAMS) / SHORTCUT_NAME


def create_app_shortcut(
    lnk_path: Path, icon_path: Path | None = None, description: str = "",
) -> None:
    """Ярлык приложения: запуск с окном настроек (без --tray)."""
    exe, args = launcher()
    create_shortcut(lnk_path, exe, args, icon_path, description)

"""Тесты winapi: только чистые части (формирование команды, язык)."""
import sys

from sunthemes import winapi


def test_autostart_command_uses_running_exe(monkeypatch, tmp_path):
    shim = tmp_path / "sunthemes.exe"
    shim.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(shim)])
    assert winapi.autostart_command() == f'"{shim.resolve()}" --tray'


def test_autostart_command_dev_fallback_uses_pythonw_or_python(monkeypatch, tmp_path):
    script = tmp_path / "run_dev.py"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(script)])
    monkeypatch.setattr(winapi.shutil, "which", lambda name: None)
    cmd = winapi.autostart_command()
    # Фолбэк использует `-m sunthemes`, а не путь к скрипту (argv[0] — это
    # __main__.py при `python -m sunthemes`, и прямой запуск ломает импорты).
    assert cmd.endswith(' -m sunthemes --tray')
    assert "python" in cmd.lower()


def test_get_ui_language_returns_supported_code():
    assert winapi.get_ui_language() in ("ru", "en")


def test_launcher_agrees_with_autostart_command(monkeypatch, tmp_path):
    shim = tmp_path / "sunthemes.exe"
    shim.write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(shim)])
    exe, args = winapi.launcher()
    assert exe == str(shim.resolve())
    assert args == ""


def test_known_folders_exist():
    assert winapi.known_folder_path(winapi.FOLDERID_DESKTOP).is_dir()
    assert winapi.known_folder_path(winapi.FOLDERID_PROGRAMS).is_dir()


def test_create_shortcut_writes_lnk(tmp_path):
    lnk = tmp_path / "test.lnk"
    winapi.create_shortcut(lnk, sys.executable, "-m sunthemes", None, "test")
    assert lnk.exists()
    assert lnk.stat().st_size > 0


def test_theme_flags_in_sync_returns_bool():
    # Реестр не трогаем — только чтение; оба исхода валидны.
    assert winapi.theme_flags_in_sync() in (True, False)


def test_set_app_user_model_id_applies():
    """AUMID реально выставляется в процессе — иначе панель задач берёт
    иконку python-хоста (SetCurrentProcessExplicitAppUserModelID зовётся
    один раз на процесс, в тестовом процессе это первый вызов)."""
    import ctypes

    winapi.set_app_user_model_id("Sunthemes.PytestCheck")
    out = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
        ctypes.byref(out))
    assert hr == 0
    try:
        assert out.value == "Sunthemes.PytestCheck"
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)

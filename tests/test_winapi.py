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
    assert cmd.endswith(f' "{script.resolve()}" --tray')
    assert "python" in cmd.lower()


def test_get_ui_language_returns_supported_code():
    assert winapi.get_ui_language() in ("ru", "en")

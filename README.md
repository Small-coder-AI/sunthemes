# Theme Switcher

Автоматическое переключение темы Windows (светлая ↔ тёмная) по восходу/закату солнца или по фиксированному расписанию.

## Что делает

- **Режим «По солнцу»** — берёт координаты (город из списка или свои), считает восход и закат через библиотеку `astral`, переключает тему. Можно задать сдвиг ±N минут (например, включать тёмную за 30 мин до заката).
- **Режим «По расписанию»** — два фиксированных времени включения светлой/тёмной.
- Прямая запись в реестр (`HKCU\…\Themes\Personalize`) + broadcast `WM_SETTINGCHANGE` → Explorer и приложения подхватывают смену темы сразу, без перелогина.
- Висит в системном трее, проверяет тему раз в минуту.
- После выхода ноутбука из сна — мгновенная проверка темы (через `WM_POWERBROADCAST`), а не ждать минуту.
- Только один экземпляр — второй запуск молча показывает «уже работает» и выходит (через named-mutex Win32).
- Все расчёты в TZ-aware времени (`zoneinfo`) — корректно даже если системная таймзона отличается от выбранной.
- Кнопки «☀ / 🌙» — переключить тему вручную, не отключая автоматику.
- Автозапуск с Windows (через `HKCU\…\Run`, прячется в трей при старте). Автозапуск умеет и dev-режим (`pythonw.exe`), и собранный `.exe`.

## Установка

Требуется Python 3.10+ для Windows.

```cmd
install.bat
```

Или вручную:

```cmd
pip install PySide6 astral
```

## Запуск

```cmd
run.bat
```

`run.bat` стартует через `pythonw.exe`, поэтому без чёрного окна консоли.

## Сборка в .exe (без Python на целевой машине)

```cmd
build.bat
```

Сделает всё сам: установит PyInstaller + Pillow + зависимости, сгенерирует иконку, соберёт `dist\ThemeSwitcher.exe` (~30–40 МБ, onefile, без консоли). Этот `.exe` можно скопировать на любую машину Windows — Python там не нужен.

Размер ужат за счёт `excludes` в `ThemeSwitcher.spec` — лишние модули PySide6 (QtWebEngine, QtMultimedia, Qt3D и т.п.) не попадают в сборку. UPX отключён намеренно, чтобы реже срабатывали антивирусы.

⚠️ **Антивирусы:** PyInstaller onefile иногда даёт false-positive у Windows Defender. Если ругается — добавь в исключения или собери в `--onedir` (поправь `EXE(...)` в `ThemeSwitcher.spec`, получится папка вместо одного файла, AV срабатывает реже).

⚠️ **Первый запуск** onefile-сборки занимает 3–5 секунд — exe распаковывается во временную папку. Это нормально.

## Файлы

- `theme_switcher.py` — само приложение
- `requirements.txt` — зависимости
- `run.bat` / `install.bat` — запуск и установка из исходников
- `build.bat` / `generate_icon.py` — сборка в `.exe`
- Конфиг и лог: `%USERPROFILE%\.theme_switcher\` (`config.json`, `theme_switcher.log`)

## Как это работает технически

| Что | Где |
|---|---|
| Запись темы | `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize` → `AppsUseLightTheme`, `SystemUsesLightTheme` (DWORD: 1=light, 0=dark) |
| Уведомление системы | `SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "ImmersiveColorSet", …)` через `ctypes` |
| Автозагрузка | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` → `ThemeSwitcher = "pythonw.exe" "…\theme_switcher.py" --tray` |
| Восход/закат | `astral.sun` по координатам и таймзоне |

## Если что-то пошло не так

- Лог: `%USERPROFILE%\.theme_switcher\theme_switcher.log`
- Удалить из автозагрузки: убрать ключ `ThemeSwitcher` из `HKCU\…\Run` (или сними галку в окне и применить).
- Сбросить настройки: удалить `%USERPROFILE%\.theme_switcher\config.json`.

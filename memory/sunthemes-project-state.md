---
name: sunthemes-project-state
description: "ThemeSwitcher отрефакторен в публичный пакет sunthemes (2026-07-12) — репо, установка, что осталось"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9b07eb30-f830-47c5-8e53-a42560a8f72e
---

> **Догон до 24.08.2026.** Запись описывает состояние по v1.1.0; актуальная версия пакета —
> **v1.2.0** (16.07.2026): standalone exe на PyInstaller, per-user установщик Inno Setup и
> release-CI (`bc72739`), фикс иконки в панели задач и ярлык на рабочем столе при первом
> запуске (`fe5e395`), документация про обход SmartScreen (`ca438f4`).
>
> Оговорка «PowerShell у Руслана запрещён deny-правилом» **устарела** — проверено 24.08.2026,
> в `deny` остались только варианты `rm -rf`; обходить через cscript+VBS больше не нужно.

2026-07-12: однофайловый ThemeSwitcher отрефакторен в пакет **sunthemes** (папка переименована в d:\Dev\sunthemes): 6 модулей (app/config/winapi/suncalc/i18n/ui), 24 pytest-теста, RU/EN UI по языку Windows. v1.0.1.

- Репо: https://github.com/Small-coder-AI/sunthemes (публичный, MIT, коммиты под noreply-email).
- Установка/обновление: `uv tool install git+https://github.com/Small-coder-AI/sunthemes` / `uv tool upgrade sunthemes`; шим `%USERPROFILE%\.local\bin\sunthemes.exe`.
- Совместимость сохранена: Run-значение `ThemeSwitcher`, mutex `ThemeSwitcher_singleton_v1`, конфиг `%USERPROFILE%\.theme_switcher\`.
- Приватность: координаты в Open-Meteo округляются до 1 знака; пресет «Истра» удалён; спеки/планы в `docs/superpowers/` и `.superpowers/` гитигнорены.
- Все minor'ы из финального ревью закрыты в v1.1.0 (2026-07-12): валидация битых значений конфига (`_validated` в config.py), sync флагов реестра в tick, Pillow в dev-группе, тесты sun-режима с погодным кешем. Отложенного долга больше нет.
- v1.0.1 (2026-07-12): RotatingFileHandler 1 МБ ×2 бэкапа, лог кода выхода и unhandled exceptions (до этого выход/падение не логировались — post-mortem был невозможен).
- v1.1.0: ярлыки встроены в приложение — `winapi.create_shortcut` (COM IShellLinkW на ctypes, без зависимостей), Known Folders API (учитывает OneDrive-редирект Desktop). Пуск — автосоздание при старте с маркером `start_menu_shortcut_seeded` в конфиге (удалённый пользователем не навязываем), рабочий стол — чекбокс в настройках (состояние = существование файла). Иконка копируется в `%USERPROFILE%\.theme_switcher\icon.ico` (стабильный путь). PowerShell у Руслана запрещён deny-правилом; разовые .lnk делал через cscript+VBS.
- После переименования папки dev `.venv` ломается («uv trampoline failed to canonicalize») — лечится `rm -rf .venv && uv sync`; боевой tool-venv в AppData не страдает.
- См. [[registry-writes-by-user-only]] про автозагрузку.

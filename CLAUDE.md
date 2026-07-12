# CLAUDE.md — sunthemes

Windows-утилита автопереключения светлой/тёмной темы по солнцу (трей, PySide6).
Публичный репозиторий: https://github.com/Small-coder-AI/sunthemes (MIT).

## Команды

```bash
uv sync                 # dev-окружение (.venv)
uv run pytest -q        # тесты (обязательно зелёные перед коммитом)
uv run python -m sunthemes          # dev-запуск GUI
uv tool install git+https://github.com/Small-coder-AI/sunthemes   # боевая установка
```

## Структура

- `src/sunthemes/app.py` — точка входа, поэтапная смена темы (switch_theme_staged), power-события
- `src/sunthemes/ui.py` — окно, трей, QSS; тему пишет ТОЛЬКО через инжектированный theme_setter
- `src/sunthemes/winapi.py` — весь Windows API (реестр, broadcast, mutex, автозагрузка); без Qt и сети
- `src/sunthemes/suncalc.py` — астрономия + погода Open-Meteo; без Qt; сеть только в фоновом потоке
- `src/sunthemes/config.py` — конфиг, пресеты городов по id, миграция legacy-имён
- `src/sunthemes/i18n.py` — словарь строк RU/EN, tr()

## Жёсткие правила

- **Совместимость не ломать**: Run-значение `ThemeSwitcher`, mutex `ThemeSwitcher_singleton_v1`, конфиг `%USERPROFILE%\.theme_switcher\` — имена фиксированы.
- **Приватность**: координаты в URL Open-Meteo — только `round(…, 1)` (~10 км); никакой автогеолокации; никаких личных данных в коде, доках и коммитах. `docs/superpowers/` и `.superpowers/` не коммитить (в .gitignore).
- **Языки**: идентификаторы, коммиты, лог-сообщения — английский; комментарии и docstrings — русский; все пользовательские строки — только через `i18n.tr()` (ключ обязан существовать в обоих языках, есть тест).
- **Границы модулей**: не тащить Qt в winapi/suncalc, сеть — только в WeatherProvider, реестр — только в winapi.
- **GUI в тестах не запускать**: singleton-mutex общий с работающим у пользователя экземпляром; тесты — чистая логика (см. tests/).
- Смена темы Windows — только поэтапная последовательность из `app.switch_theme_staged` (флаг → broadcast → 100 мс → флаг → broadcast → 1.2 с → broadcast); не «оптимизировать» в запись залпом — вернётся глюк полуперекрашенной оболочки.

## Версии

Версия задаётся в двух местах: `pyproject.toml` и `src/sunthemes/__init__.py` — менять синхронно.

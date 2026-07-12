# Sunthemes

Автоматическое переключение темы Windows (светлая ↔ тёмная) — по
восходу/закату солнца или по расписанию. Умеет учитывать *реальную*
освещённость по облачности и солнечной радиации: в пасмурный день
тёмная тема включится раньше астрономического заката.

[English version](README.md)

## Возможности

- **Режим «По солнцу»** — считает восход и закат для твоей точки
  (пресет города или свои координаты) и переключает тему; есть сдвиг
  ±N минут.
- **Режим «по реальному свету»** — почасовая солнечная радиация с
  [Open-Meteo](https://open-meteo.com/) (без API-ключа): тема следует
  за фактической темнотой, а не за календарём.
- **Режим «По расписанию»** — два фиксированных времени.
- Живёт в трее, проверяет раз в минуту, после выхода из сна — сразу.
- Ручные кнопки ☀ / 🌙.
- Автозапуск с Windows (свёрнутым в трей).
- Интерфейс на русском или английском (по языку Windows).
- Только один экземпляр; все расчёты с учётом таймзоны.

## Приватность

- Никакой геолокации: используются только координаты, которые ты сам
  выбрал.
- Перед запросом погоды координаты округляются до одного знака
  (~10 км) — точное местоположение не покидает компьютер.
- Ни телеметрии, ни аккаунтов, ни ключей. Единственный сетевой запрос —
  опциональный прогноз Open-Meteo.

## Установка

Нужна Windows 10/11. Через [uv](https://docs.astral.sh/uv/)
(Python поставится сам, если его нет):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install git+https://github.com/Small-coder-AI/sunthemes
```

Дальше запусти `sunthemes` (команда появится в PATH, окно консоли не
открывается), поставь галку **«Запускать при старте Windows»** и нажми
**«Сохранить и применить»** — всё.

Обновление:

```powershell
uv tool upgrade sunthemes
```

## Как это работает

| Что | Где |
|---|---|
| Запись темы | `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize` → `AppsUseLightTheme`, `SystemUsesLightTheme` |
| Уведомление системы | `SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, …, "ImmersiveColorSet", …)` — флаги пишутся по одному с паузой и повторным broadcast, чтобы реже ловить глюк полуперекрашенной оболочки |
| Восход/закат | [astral](https://github.com/sffjunkie/astral) по координатам и таймзоне |
| Реальный свет | почасовая `shortwave_radiation` Open-Meteo; переключение — на пересечении ~50 Вт/м² (гражданские сумерки), с линейной интерполяцией между часами |
| Автозагрузка | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |

Конфиг и лог: `%USERPROFILE%\.theme_switcher\`
(`config.json`, `theme_switcher.log`).

## Если что-то пошло не так

- Лог: `%USERPROFILE%\.theme_switcher\theme_switcher.log`.
- Сброс настроек: удалить `%USERPROFILE%\.theme_switcher\config.json`.
- Убрать из автозагрузки: снять галку и применить, либо удалить
  значение `ThemeSwitcher` в `HKCU\...\Run`.

## Разработка

```powershell
git clone https://github.com/Small-coder-AI/sunthemes
cd sunthemes
uv sync
uv run pytest
uv run python -m sunthemes
```

## Лицензия

[MIT](LICENSE)

# Sunthemes

Automatic Windows light/dark theme switching — by sunrise and sunset,
or on a fixed schedule. Optionally follows *actual* daylight using
cloud-cover and solar-radiation data, so a gloomy afternoon can switch
you to dark mode before the astronomical sunset.

[Русская версия](README.ru.md)

## Features

- **Sun mode** — computes sunrise/sunset for your location (city preset
  or custom coordinates) and switches the Windows theme accordingly,
  with an optional ±N minutes offset.
- **Real daylight mode** — hourly solar radiation from
  [Open-Meteo](https://open-meteo.com/) (no API key): the theme follows
  when it actually gets dark, not when the almanac says so.
- **Schedule mode** — plain fixed times for light and dark.
- Sits in the system tray, checks once a minute, re-checks immediately
  after wake-from-sleep.
- Manual ☀ / 🌙 override buttons.
- Autostart with Windows (minimized to tray).
- Start Menu shortcut is created on first run; desktop shortcut is
  an opt-in checkbox in settings.
- UI in English or Russian (follows the Windows display language).
- Single instance guard, timezone-aware calculations.

## Privacy

- No geolocation: the app only uses coordinates you pick yourself.
- Coordinates are rounded to one decimal (~10 km) before the weather
  request — your exact location never leaves the machine.
- No telemetry, no accounts, no keys. The only network call is the
  optional Open-Meteo forecast.

## Install

### Regular install (recommended)

1. Open the [releases page](https://github.com/Small-coder-AI/sunthemes/releases)
   and download `SunthemesSetup.exe`.
2. Run it. On first launch Windows SmartScreen may warn "Windows protected
   your PC" — click **"More info" → "Run anyway"**. The app is not signed with
   a paid certificate, but the source is open.
3. In the wizard, keep **"Desktop shortcut"** and **"Start with Windows"**
   checked and install — no admin rights required.

The app lives in the system tray near the clock: ☀ / 🌙 buttons and settings.

### For developers (via uv)

Requires Windows 10/11. With [uv](https://docs.astral.sh/uv/)
(installs Python automatically if needed):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv tool install git+https://github.com/Small-coder-AI/sunthemes
```

Then run `sunthemes` in a **new** terminal window (PATH only updates in a new
window). No console window opens — it goes to the tray and creates Start Menu
and Desktop shortcuts.

Update later with:

```powershell
uv tool upgrade sunthemes
```

## How it works

| What | Where |
|---|---|
| Theme write | `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize` → `AppsUseLightTheme`, `SystemUsesLightTheme` |
| Change notification | `SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, …, "ImmersiveColorSet", …)` — flags written one by one with a short pause and a repeated broadcast to minimize the half-repainted-shell glitch |
| Sunrise/sunset | [astral](https://github.com/sffjunkie/astral) from coordinates and timezone |
| Real daylight | Open-Meteo hourly `shortwave_radiation`; the switch happens when radiation crosses ~50 W/m² (civil twilight), linearly interpolated between hours |
| Autostart | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |

Config and log live in `%USERPROFILE%\.theme_switcher\`
(`config.json`, `theme_switcher.log`).

## Troubleshooting

- Check the log: `%USERPROFILE%\.theme_switcher\theme_switcher.log`.
- Reset settings: delete `%USERPROFILE%\.theme_switcher\config.json`.
- Remove from autostart: untick **Start with Windows** and apply, or
  delete the `ThemeSwitcher` value under `HKCU\...\Run`.

## Development

```powershell
git clone https://github.com/Small-coder-AI/sunthemes
cd sunthemes
uv sync
uv run pytest
uv run python -m sunthemes
```

## License

[MIT](LICENSE)

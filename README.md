# Sunthemes

Automatic Windows light/dark theme switching — by the sun's height above
the horizon, or on a fixed schedule. Optionally follows *actual* daylight
from a cloud forecast, so on a gloomy day dark mode comes earlier in the
evening and light mode later in the morning.

[Русская версия](README.ru.md)

## Features

- **Sun mode** — light theme while the sun is above a threshold height
  (city preset or custom coordinates). Morning and evening thresholds are
  separate; the default 5° is roughly 40–60 minutes after sunrise and
  before sunset at Moscow's latitude, when a room is actually lit. Polar
  day and night just work.
- **Cloud awareness** — hourly solar radiation forecast from
  [Open-Meteo](https://open-meteo.com/) (no API key): clouds raise the
  threshold, so the theme follows when it actually gets dark, not when
  the almanac says so.
- **Schedule mode** — plain fixed times for light and dark (Windows clock).
- The window shows today's sunrise/sunset and when the theme will switch.
- Sits in the system tray, checks once a minute, re-checks immediately
  after wake-from-sleep.
- Manual ☀ / 🌙 buttons: the choice holds until the next scheduled switch
  (resume auto earlier via the link in the window or the tray menu).
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
| Sun height | [astral](https://github.com/sffjunkie/astral) from coordinates; light theme while the sun is above the threshold (separate for morning and evening) |
| Real daylight | Open-Meteo hourly `shortwave_radiation` is an *average over the preceding hour*; it is turned into a clearness index against a clear-sky model (Haurwitz) averaged over the same hour. Clouds raise the threshold: light while "clearness × clear-sky radiation" stays above the clear-sky radiation at the threshold. Clouds only shorten the light window, by at most `clouds_max_offset_min` (120 min) on each side. If `api.open-meteo.com` is unreachable, the same forecast comes from Open-Meteo's Previous Runs API (another server) |
| Stability | a switch that already happened is never undone by a newer forecast — no back-and-forth flicker |
| Autostart | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |

Config and log live in `%USERPROFILE%\.theme_switcher\`
(`config.json`, `theme_switcher.log`). Config-only setting:
`clouds_max_offset_min` — how many minutes clouds may shift a switch.

**Upgrading from 1.2.x.** The single "±N minutes" offset moved morning and
evening in the same direction, so making the evening earlier also made
the morning earlier. It is replaced by sun-height thresholds; the old
offset is reset, and the new defaults already move the evening earlier
and the morning later.

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

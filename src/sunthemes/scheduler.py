"""Какая тема нужна сейчас и когда следующая смена — без Qt, реестра и сети.

Состояние между тиками:
- план текущих солнечных суток: прошедшие границы «замораживаются», чтобы
  обновлённый прогноз не вернул тему назад (светлая → тёмная → светлая);
- ручной выбор: держится до следующей автоматической смены, дальше снова
  работает расписание.

Режим «по расписанию» и все отображаемые времена — в локальном времени
системы (то, что показывают часы Windows); tz подменяется в тестах.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from . import suncalc
from .suncalc import HALF_DAY, DayPlan

log = logging.getLogger("sunthemes")

LIGHT, DARK = "light", "dark"
DAY = timedelta(days=1)
# Сколько суток вперёд искать следующую смену (полярные день и ночь).
LOOKAHEAD_DAYS = 3


def schedule_theme(light_t: time, dark_t: time, current: time) -> str:
    """Тема по фиксированному расписанию; допускает переход через полночь."""
    if light_t <= dark_t:
        return LIGHT if light_t <= current < dark_t else DARK
    return DARK if dark_t <= current < light_t else LIGHT


@dataclass(frozen=True)
class Status:
    theme: str                     # что должно стоять сейчас
    auto_theme: str                # что решило бы расписание без ручного выбора
    manual: bool                   # действует ручной выбор
    next_switch: datetime | None   # следующая авто-смена (при ручном — возврат к авто)
    next_theme: str | None         # тема после next_switch


@dataclass(frozen=True)
class SunPreview:
    """Расчёт на сегодня для подсказки в окне настроек."""
    astro: DayPlan           # восход/закат
    base: DayPlan            # по порогам высоты солнца, без облаков
    plan: DayPlan            # итог с учётом облаков (== base без погоды)
    weather: str             # 'off' | 'ok' | 'loading' | 'failed'
    cloud_cover: int | None  # облачность сейчас, %


@dataclass(frozen=True)
class _Manual:
    theme: str
    auto_theme: str               # авто-тема в момент выбора
    until: datetime | None        # следующая авто-смена на момент выбора
    until_theme: str | None


class ThemeScheduler:
    """weather — WeatherProvider (или None — без погоды); tz — зона для
    расписания и «сегодня» (None — системная); clock — текущее время (UTC)."""

    def __init__(self, weather=None, tz: tzinfo | None = None, clock=None) -> None:
        self._weather = weather
        self._tz = tz
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._plans: dict[tuple, DayPlan] = {}
        self._clearness: dict[tuple, object] = {}
        self._current: tuple[tuple, DayPlan] | None = None   # (настройки, план)
        self._manual: _Manual | None = None

    # --- публичное API ---

    @property
    def manual_active(self) -> bool:
        return self._manual is not None

    def evaluate(self, cfg: dict, now: datetime | None = None) -> Status:
        """Решение на момент `now`. Никогда не блокируется: погода — из кеша,
        обновление кеша (если нужно) уходит в фоновый поток."""
        now = self._resolve(now)
        self._request_weather(cfg)
        auto = self._auto_theme(cfg, now)
        manual = self._manual
        if manual is not None and (
            (manual.until is not None and now >= manual.until)
            or auto != manual.auto_theme
        ):
            log.info("Manual %s override ended — back to schedule", manual.theme)
            self._manual = manual = None
        if manual is not None:
            return Status(manual.theme, auto, True, manual.until, manual.until_theme)
        nxt = self._next_change(cfg, now, auto)
        return Status(auto, auto, False, *(nxt or (None, None)))

    def set_manual(self, theme: str, cfg: dict, now: datetime | None = None) -> None:
        """Ручной выбор до следующей авто-смены. Выбор той темы, что и так
        стоит по расписанию, снимает ручной режим."""
        now = self._resolve(now)
        auto = self._auto_theme(cfg, now)
        if theme == auto:
            self._manual = None
            return
        nxt = self._next_change(cfg, now, auto)
        self._manual = _Manual(theme, auto, *(nxt or (None, None)))
        log.info("Manual %s override until %s", theme,
                 nxt[0].isoformat(timespec="minutes") if nxt else "next change")

    def clear_manual(self) -> None:
        self._manual = None

    def preview(self, cfg: dict, now: datetime | None = None) -> SunPreview:
        """Расчёт на сегодняшнюю дату для настроек `cfg` (без заморозки)."""
        now = self._resolve(now)
        self._request_weather(cfg)
        today_noon = self._local_at(self._local(now).date(), time(12))
        noon = suncalc.solar_day_noon(cfg["lon"], today_noon)
        weather, cloud = self._weather_info(cfg, noon, now)
        return SunPreview(
            astro=suncalc.astronomical_day(cfg["lat"], cfg["lon"], noon),
            base=self._plan(dict(cfg, use_clouds=False), noon),
            plan=self._plan(cfg, noon),
            weather=weather,
            cloud_cover=cloud,
        )

    # --- время ---

    def _resolve(self, now: datetime | None) -> datetime:
        now = self._clock() if now is None else now
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        return now

    def _local(self, when: datetime) -> datetime:
        return when.astimezone(self._tz)       # tz=None → системная зона

    def _local_at(self, day: date, hhmm: time) -> datetime:
        if self._tz is not None:
            return datetime.combine(day, hhmm, tzinfo=self._tz)
        return datetime.combine(day, hhmm).astimezone()

    # --- решение ---

    def _auto_theme(self, cfg: dict, now: datetime) -> str:
        if cfg["mode"] == "time":
            return self._theme_at(cfg, now)
        return LIGHT if self._current_plan(cfg, now).is_light(now) else DARK

    def _theme_at(self, cfg: dict, when: datetime) -> str:
        if cfg["mode"] == "time":
            return schedule_theme(time.fromisoformat(cfg["light_time"]),
                                  time.fromisoformat(cfg["dark_time"]),
                                  self._local(when).time())
        return LIGHT if self._plan_at(cfg, when).is_light(when) else DARK

    def _next_change(self, cfg: dict, now: datetime, current: str):
        """(момент, тема) ближайшей смены после `now` или None."""
        for moment in sorted(self._boundaries(cfg, now)):
            if moment > now:
                theme = self._theme_at(cfg, moment)
                if theme != current:
                    return moment, theme
        return None

    def _boundaries(self, cfg: dict, now: datetime):
        if cfg["mode"] == "time":
            today = self._local(now).date()
            for k in range(LOOKAHEAD_DAYS):
                for hhmm in (cfg["light_time"], cfg["dark_time"]):
                    yield self._local_at(today + k * DAY, time.fromisoformat(hhmm))
            return
        noon = suncalc.solar_day_noon(cfg["lon"], now)
        for k in range(LOOKAHEAD_DAYS):
            plan = self._plan_at(cfg, noon + k * DAY)
            if plan.has_light:
                yield plan.light_from
                yield plan.dark_from

    # --- планы по солнцу ---

    @staticmethod
    def _settings_key(cfg: dict) -> tuple:
        return (cfg["lat"], cfg["lon"], cfg["morning_elevation"],
                cfg["evening_elevation"], cfg["use_clouds"],
                cfg["clouds_max_offset_min"])

    def _current_plan(self, cfg: dict, now: datetime) -> DayPlan:
        """План текущих суток с замороженными прошедшими границами.

        Уже случившееся переключение прогноз не отменяет: если утром тема
        стала светлой, новый прогноз «светлеет позже» её не вернёт; если
        вечером стала тёмной — «темнеет позже» не вернёт светлую. Будущие
        границы по-прежнему следуют свежему прогнозу."""
        noon = suncalc.solar_day_noon(cfg["lon"], now)
        fresh = self._plan(cfg, noon)
        key = self._settings_key(cfg)
        plan = fresh
        if self._current is not None:
            old_key, old = self._current
            if old_key == key and old.noon == noon and old.has_light:
                light_from = old.light_from if old.light_from <= now else fresh.light_from
                dark_from = old.dark_from if old.dark_from <= now else fresh.dark_from
                plan = DayPlan(noon, light_from, max(light_from, dark_from))
        self._current = (key, plan)
        return plan

    def _plan_at(self, cfg: dict, when: datetime) -> DayPlan:
        """План суток, в которые попадает `when` (для текущих — замороженный)."""
        noon = suncalc.solar_day_noon(cfg["lon"], when)
        if self._current is not None:
            key, plan = self._current
            if key == self._settings_key(cfg) and plan.noon == noon:
                return plan
        return self._plan(cfg, noon)

    def _plan(self, cfg: dict, noon: datetime) -> DayPlan:
        """Свежий план суток (кеш: пересчёт только при смене настроек,
        суток или прогноза)."""
        clearness, forecast = self._clearness_for(cfg, noon)
        key = (noon, cfg["lat"], cfg["lon"], cfg["morning_elevation"],
               cfg["evening_elevation"], cfg["clouds_max_offset_min"], forecast)
        plan = self._plans.get(key)
        if plan is None:
            if len(self._plans) > 64:
                self._plans.clear()
            plan = suncalc.day_plan(
                cfg["lat"], cfg["lon"], noon,
                cfg["morning_elevation"], cfg["evening_elevation"],
                clearness=clearness,
                max_shift=timedelta(minutes=cfg["clouds_max_offset_min"]),
            )
            self._plans[key] = plan
        return plan

    # --- погода ---

    def _request_weather(self, cfg: dict) -> None:
        if cfg["mode"] == "sun" and cfg["use_clouds"] and self._weather is not None:
            self._weather.refresh_in_background(cfg["lat"], cfg["lon"])

    def _usable_forecast(self, cfg: dict, noon: datetime):
        """Прогноз, покрывающий солнечные сутки целиком, или None."""
        if not cfg["use_clouds"] or self._weather is None:
            return None
        forecast = self._weather.forecast(cfg["lat"], cfg["lon"])
        if forecast is None or not forecast.covers(noon - HALF_DAY, noon + HALF_DAY):
            return None
        return forecast

    def _clearness_for(self, cfg: dict, noon: datetime):
        """(kc(t), прогноз) или (None, None), если учитывать нечего."""
        forecast = self._usable_forecast(cfg, noon)
        if forecast is None:
            return None, None
        key = (forecast, cfg["lat"], cfg["lon"])
        if key not in self._clearness:
            if len(self._clearness) > 8:
                self._clearness.clear()
            self._clearness[key] = suncalc.interpolator(
                suncalc.clearness_anchors(cfg["lat"], cfg["lon"], forecast.radiation))
        clearness = self._clearness[key]
        return (clearness, forecast) if clearness is not None else (None, None)

    def _weather_info(self, cfg: dict, noon: datetime, now: datetime):
        if not cfg["use_clouds"] or self._weather is None:
            return "off", None
        forecast = self._usable_forecast(cfg, noon)
        if forecast is not None:
            return "ok", forecast.cloud_cover_at(now)
        status = self._weather.status(cfg["lat"], cfg["lon"])
        return ("loading", None) if status in ("loading", "idle") else ("failed", None)

"""Прогноз Open-Meteo: почасовая радиация и облачность для учёта погоды.

Правила модуля:
- Никакого Qt. Сеть — только в фоновом daemon-потоке
  (refresh_in_background); остальные методы работают по кешу и никогда
  не блокируются.
- Неудачный запрос запоминается: повтор не раньше чем через 5 минут.
- Приватность: координаты в URL округляются до 1 знака (~10 км) —
  точная геолокация в сеть не уходит; на расчёт света это не влияет.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

log = logging.getLogger("sunthemes")

API_URL = "https://api.open-meteo.com/v1/forecast"
UTC = timezone.utc
HOUR = timedelta(hours=1)


@dataclass(frozen=True, eq=False)
class Forecast:
    """Разобранный ответ Open-Meteo, время — UTC, ряды отсортированы.

    radiation — (конец часа, средняя радиация за предыдущий час, Вт/м²):
    так Open-Meteo отдаёт shortwave_radiation. cloud_cover — (момент,
    облачность %), мгновенные значения."""

    radiation: tuple[tuple[datetime, float], ...]
    cloud_cover: tuple[tuple[datetime, float], ...] = ()

    def covers(self, start: datetime, end: datetime) -> bool:
        """Покрывает ли ряд радиации интервал [start, end] целиком."""
        if not self.radiation:
            return False
        return self.radiation[0][0] - HOUR <= start and self.radiation[-1][0] >= end

    def cloud_cover_at(self, when: datetime) -> int | None:
        """Облачность в ближайший к `when` час (не дальше 1.5 ч) или None."""
        nearest = min(self.cloud_cover, key=lambda p: abs(p[0] - when), default=None)
        if nearest is None or abs(nearest[0] - when) > 1.5 * HOUR:
            return None
        return round(nearest[1])


def parse_forecast(data: dict) -> Forecast:
    """JSON Open-Meteo (timeformat=unixtime) → Forecast; ValueError при
    неожиданной структуре. Пустые значения (null) пропускаются."""
    try:
        hourly = data["hourly"]
        times = [datetime.fromtimestamp(int(t), UTC) for t in hourly["time"]]

        def series(name: str) -> tuple[tuple[datetime, float], ...]:
            values = hourly.get(name) or []
            return tuple(sorted(
                (t, float(v)) for t, v in zip(times, values, strict=True) if v is not None))

        return Forecast(series("shortwave_radiation"), series("cloud_cover"))
    except (KeyError, TypeError, ValueError, OverflowError) as e:
        raise ValueError(f"unexpected Open-Meteo response: {e!r}") from e


def _fetch_json(url: str, timeout: float) -> dict:
    with urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


@dataclass
class _Entry:
    forecast: Forecast | None = None
    fetched_at: float | None = None      # clock() последней удачной загрузки
    failed_at: float | None = None       # clock() последней ошибки
    in_flight: bool = False


class WeatherProvider:
    """Кеш прогнозов по округлённым координатам + фоновая загрузка.

    on_update — колбэк без аргументов после каждой попытки загрузки;
    вызывается ИЗ ФОНОВОГО ПОТОКА (в Qt — через сигнал)."""

    CACHE_TTL = 30 * 60          # с: свежий прогноз не перезапрашиваем
    FAILURE_RETRY = 5 * 60       # с: пауза после неудачи
    TIMEOUT_SEC = 6
    MAX_POINTS = 4               # сколько точек держать (превью другого города)

    def __init__(
        self,
        fetch_json: Callable[[str, float], dict] = _fetch_json,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch_json = fetch_json
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[tuple[float, float], _Entry] = {}
        self.on_update: Callable[[], None] | None = None

    @staticmethod
    def point(lat: float, lon: float) -> tuple[float, float]:
        """Ключ кеша и координаты запроса: округление до ~10 км."""
        return round(lat, 1), round(lon, 1)

    @classmethod
    def url(cls, lat: float, lon: float) -> str:
        p_lat, p_lon = cls.point(lat, lon)
        return API_URL + "?" + urlencode({
            "latitude": p_lat,
            "longitude": p_lon,
            "hourly": "shortwave_radiation,cloud_cover",
            # Вчера + 2 дня (UTC) — солнечные сутки покрыты при любой таймзоне.
            "past_days": 1,
            "forecast_days": 2,
            "timeformat": "unixtime",
        })

    # --- чтение кеша (без сети) ---

    def forecast(self, lat: float, lon: float) -> Forecast | None:
        """Последний удачный прогноз для точки (возможно, устаревший) или None."""
        with self._lock:
            entry = self._entries.get(self.point(lat, lon))
            return entry.forecast if entry else None

    def status(self, lat: float, lon: float) -> str:
        """'loading' — идёт загрузка; 'ok' — прогноз есть; 'failed' —
        последняя попытка неудачна; 'idle' — ещё не запрашивали."""
        with self._lock:
            entry = self._entries.get(self.point(lat, lon))
            if entry is None:
                return "idle"
            if entry.in_flight:
                return "loading"
            if entry.forecast is not None:
                return "ok"
            return "failed" if entry.failed_at is not None else "idle"

    def needs_refresh(self, lat: float, lon: float) -> bool:
        with self._lock:
            return self._needs_refresh_locked(self.point(lat, lon))

    def _needs_refresh_locked(self, key: tuple[float, float]) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return True
        if entry.in_flight:
            return False
        now = self._clock()
        if entry.failed_at is not None and now - entry.failed_at < self.FAILURE_RETRY:
            return False
        if entry.fetched_at is not None and now - entry.fetched_at < self.CACHE_TTL:
            return False
        return True

    # --- сеть ---

    def refresh_in_background(self, lat: float, lon: float) -> bool:
        """Запустить загрузку в daemon-потоке, если она нужна. True — запущена."""
        key = self._claim(lat, lon)
        if key is None:
            return False
        threading.Thread(target=self._run, args=(key,), daemon=True,
                         name="open-meteo").start()
        return True

    def refresh(self, lat: float, lon: float) -> None:
        """Синхронная загрузка (если нужна) — тот же путь, что у фонового потока."""
        key = self._claim(lat, lon)
        if key is not None:
            self._run(key)

    def _claim(self, lat: float, lon: float) -> tuple[float, float] | None:
        """Пометить точку «в загрузке», если её пора обновить."""
        key = self.point(lat, lon)
        with self._lock:
            if not self._needs_refresh_locked(key):
                return None
            if key not in self._entries:
                self._entries[key] = _Entry()
                self._evict_locked()
            self._entries[key].in_flight = True
        return key

    def _evict_locked(self) -> None:
        for old in list(self._entries):
            if len(self._entries) <= self.MAX_POINTS:
                break
            if not self._entries[old].in_flight:
                del self._entries[old]

    def _run(self, key: tuple[float, float]) -> None:
        try:
            forecast = parse_forecast(self._fetch_json(self.url(*key), self.TIMEOUT_SEC))
        except Exception as e:
            with self._lock:
                entry = self._entries.setdefault(key, _Entry())
                entry.failed_at = self._clock()
                entry.in_flight = False
            log.warning("Open-Meteo unavailable: %s", e)
        else:
            with self._lock:
                entry = self._entries.setdefault(key, _Entry())
                entry.forecast = forecast
                entry.fetched_at = self._clock()
                entry.failed_at = None
                entry.in_flight = False
            log.info("Open-Meteo: forecast received for (%.1f, %.1f)", *key)
        callback = self.on_update
        if callback is not None:
            try:
                callback()
            except Exception:
                log.exception("Weather update callback failed")

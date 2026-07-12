"""Астрономия (astral), погода (Open-Meteo) и расчёт целевой темы.

Правила модуля:
- Никакого Qt: модуль тестируется без GUI.
- Сеть — только в фоновом потоке (refresh_in_background); все остальные
  методы работают по кешу и никогда не блокируются.
- Неудачный запрос запоминается: повтор не раньше чем через 5 минут.
- Приватность: координаты в URL округляются до 1 десятичного знака
  (~10 км) — точная геолокация в сеть не уходит, на восход/закат
  влияние секунды.
"""

import json
import logging
import threading
from datetime import datetime, time, timedelta
from urllib.request import urlopen
from zoneinfo import ZoneInfo

try:
    from astral import Observer
    from astral.sun import sun
    ASTRAL_OK = True
except ImportError:
    ASTRAL_OK = False

log = logging.getLogger("sunthemes")


def _now() -> datetime:
    """Текущее время; вынесено для подмены в тестах."""
    return datetime.now()


def compute_sun_times(lat: float, lon: float, tz: str, date=None):
    """(sunrise, sunset) как TZ-aware datetime в заданной зоне; (None, None) без astral."""
    if not ASTRAL_OK:
        return None, None
    zone = ZoneInfo(tz)
    if date is None:
        date = datetime.now(zone).date()
    observer = Observer(latitude=lat, longitude=lon, elevation=0)
    s = sun(observer, date=date, tzinfo=zone)
    return s["sunrise"], s["sunset"]


class WeatherProvider:
    """Почасовой прогноз Open-Meteo: облачность + реальная солнечная
    радиация shortwave_radiation (Вт/м²).

    effective_sun_times() возвращает не астрономический восход/закат, а
    моменты, когда радиация фактически пересекает порог сумерек — так
    облачность учитывается через физику, а не пропорцию-на-глаз.
    """

    URL = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={lat}&longitude={lon}"
        "&current=cloud_cover"
        "&hourly=shortwave_radiation,cloud_cover"
        "&forecast_days=2"
        "&timezone={tz}"
    )
    CACHE_TTL = timedelta(minutes=30)
    FAILURE_RETRY = timedelta(minutes=5)
    TIMEOUT_SEC = 6
    # ~50 Вт/м² — гражданские сумерки: фонари ещё не нужны,
    # но за экраном уже комфортнее тёмная тема.
    THRESHOLD_W_M2 = 50

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: tuple[datetime, float, float, dict] | None = None
        self._failed_at: datetime | None = None
        self._in_flight = False

    # --- работа с кешем (без сети) ---

    def cached_data(self, lat: float, lon: float) -> dict | None:
        """Данные из кеша для этой точки (возможно, устаревшие) или None."""
        with self._lock:
            if self._cache:
                _, c_lat, c_lon, data = self._cache
                if abs(c_lat - lat) < 0.01 and abs(c_lon - lon) < 0.01:
                    return data
        return None

    def needs_refresh(self, lat: float, lon: float) -> bool:
        with self._lock:
            return self._needs_refresh_locked(lat, lon)

    def _needs_refresh_locked(self, lat: float, lon: float) -> bool:
        if self._in_flight:
            return False
        if self._failed_at and _now() - self._failed_at < self.FAILURE_RETRY:
            return False  # negative-cache: после ошибки ждём FAILURE_RETRY
        if self._cache:
            when, c_lat, c_lon, _ = self._cache
            same_loc = abs(c_lat - lat) < 0.01 and abs(c_lon - lon) < 0.01
            if same_loc and _now() - when < self.CACHE_TTL:
                return False
        return True

    # --- сеть (только фоновый поток) ---

    def refresh_in_background(self, lat: float, lon: float, tz: str) -> None:
        """Запустить обновление кеша в daemon-потоке, если оно нужно."""
        with self._lock:
            if not self._needs_refresh_locked(lat, lon):
                return
            self._in_flight = True
        threading.Thread(
            target=self._refresh_worker, args=(lat, lon, tz), daemon=True,
        ).start()

    def _refresh_worker(self, lat: float, lon: float, tz: str) -> None:
        """Синхронная загрузка прогноза; вызывается из фонового потока."""
        try:
            # Округление до 1 знака (~10 км): точная геолокация не уходит в сеть.
            url = self.URL.format(lat=round(lat, 1), lon=round(lon, 1), tz=tz)
            with urlopen(url, timeout=self.TIMEOUT_SEC) as r:
                data = json.loads(r.read().decode("utf-8"))
            with self._lock:
                self._cache = (_now(), lat, lon, data)
                self._failed_at = None
            log.info("Open-Meteo: forecast received for (%.1f, %.1f)", lat, lon)
        except Exception as e:
            with self._lock:
                self._failed_at = _now()
            log.warning("Open-Meteo unavailable: %s", e)
        finally:
            with self._lock:
                self._in_flight = False

    # --- производные значения (по кешу) ---

    def current_cloud(self, lat: float, lon: float) -> int | None:
        data = self.cached_data(lat, lon)
        if not data:
            return None
        try:
            return int(data["current"]["cloud_cover"])
        except (KeyError, TypeError, ValueError):
            return None

    def effective_sun_times(
        self, lat: float, lon: float, tz: str,
        sunrise: datetime, sunset: datetime,
        max_offset_min: int = 120,
    ) -> tuple[datetime | None, datetime | None]:
        """(eff_sunrise, eff_sunset) — моменты пересечения радиацией порога
        THRESHOLD_W_M2 (вверх — восход, вниз — закат), линейная интерполяция
        между часами. None — если данных нет или переход не найден."""
        data = self.cached_data(lat, lon)
        if not data:
            return None, None
        try:
            zone = ZoneInfo(tz)
            times_iso = data["hourly"]["time"]
            rads = data["hourly"]["shortwave_radiation"]
        except KeyError:
            return None, None

        target_date = sunrise.date()
        points: list[tuple[datetime, float]] = []
        for t_iso, r in zip(times_iso, rads):
            dt = datetime.fromisoformat(t_iso).replace(tzinfo=zone)
            if dt.date() == target_date and r is not None:
                points.append((dt, float(r)))
        if len(points) < 2:
            return None, None

        threshold = self.THRESHOLD_W_M2
        eff_sr: datetime | None = None
        eff_ss: datetime | None = None

        for (t0, r0), (t1, r1) in zip(points, points[1:]):
            crosses_up = r0 < threshold <= r1
            crosses_down = r0 >= threshold > r1
            if not (crosses_up or crosses_down):
                continue
            frac = (threshold - r0) / (r1 - r0)
            cross_t = t0 + (t1 - t0) * frac
            if crosses_up and eff_sr is None:
                eff_sr = cross_t
            if crosses_down and eff_sr is not None:
                eff_ss = cross_t  # закат — после восхода того же дня

        # Защитный clamp: не даём радиационной модели уехать от астрономии.
        cap = timedelta(minutes=max_offset_min)
        if eff_sr is not None:
            eff_sr = min(max(eff_sr, sunrise - cap), sunrise + cap)
        if eff_ss is not None:
            eff_ss = min(max(eff_ss, sunset - cap), sunset + cap)
        return eff_sr, eff_ss


# Глобальный экземпляр: кеш живёт на всё приложение.
weather = WeatherProvider()


def apply_weather_adjustment(
    sunrise: datetime, sunset: datetime, cfg: dict,
) -> tuple[datetime, datetime, int | None]:
    """Заменяет sunrise/sunset на эффективные по реальной освещённости,
    если включён режим погоды и в кеше есть данные. Третий элемент —
    текущая облачность для UI (None — выключено или данных нет).
    Не блокируется: работает строго по кешу."""
    if not cfg.get("use_clouds"):
        return sunrise, sunset, None
    lat, lon, tz = cfg["lat"], cfg["lon"], cfg["tz"]
    cloud = weather.current_cloud(lat, lon)
    if cloud is None:
        return sunrise, sunset, None
    max_off = cfg.get("clouds_max_offset_min", 120)
    eff_sr, eff_ss = weather.effective_sun_times(
        lat, lon, tz, sunrise, sunset, max_offset_min=max_off,
    )
    return (eff_sr or sunrise), (eff_ss or sunset), cloud


def determine_target_theme(cfg: dict, now: datetime | None = None) -> str:
    """'light' | 'dark'. Сравнение в TZ-aware времени зоны из конфига —
    корректно, даже если системная таймзона отличается от выбранной."""
    zone = ZoneInfo(cfg["tz"])
    now_z = now.astimezone(zone) if (now and now.tzinfo) else datetime.now(zone)

    if cfg["mode"] == "sun" and ASTRAL_OK:
        try:
            sunrise, sunset = compute_sun_times(
                cfg["lat"], cfg["lon"], cfg["tz"], now_z.date()
            )
            sunrise, sunset, _ = apply_weather_adjustment(sunrise, sunset, cfg)
            offset = timedelta(minutes=cfg.get("offset_min", 0))
            return "light" if (sunrise + offset) <= now_z < (sunset + offset) else "dark"
        except Exception as e:
            log.error("Sun calculation failed: %s. Falling back to schedule.", e)

    light_t = time.fromisoformat(cfg["light_time"])
    dark_t = time.fromisoformat(cfg["dark_time"])
    cur = now_z.time()
    if light_t <= dark_t:
        return "light" if light_t <= cur < dark_t else "dark"
    return "dark" if dark_t <= cur < light_t else "light"

"""Тесты чистой логики: целевая тема, интерполяция радиации, negative-cache."""
from datetime import datetime, timedelta
from urllib.error import URLError
from zoneinfo import ZoneInfo

import pytest

from sunthemes import suncalc

MSK = ZoneInfo("Europe/Moscow")


def make_cfg(**over):
    cfg = {
        "mode": "time", "city": "moscow",
        "lat": 55.7558, "lon": 37.6173, "tz": "Europe/Moscow",
        "offset_min": 0, "light_time": "07:00", "dark_time": "19:00",
        "use_clouds": False, "clouds_max_offset_min": 120,
    }
    cfg.update(over)
    return cfg


# --- режим «по расписанию»: границы, включая переход через полночь ---

@pytest.mark.parametrize("hhmm,expected", [
    ("06:59", "dark"), ("07:00", "light"), ("18:59", "light"), ("19:00", "dark"),
])
def test_time_mode_boundaries(hhmm, expected):
    h, m = map(int, hhmm.split(":"))
    now = datetime(2026, 7, 12, h, m, tzinfo=MSK)
    assert suncalc.determine_target_theme(make_cfg(), now) == expected


def test_time_mode_inverted_schedule_crosses_midnight():
    # светлая с 19:00, тёмная с 07:00 — «ночная смена»
    cfg = make_cfg(light_time="19:00", dark_time="07:00")
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 7, 12, 20, 0, tzinfo=MSK)) == "light"
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 7, 12, 8, 0, tzinfo=MSK)) == "dark"


# --- режим «по солнцу»: детерминированная астрономия ---

def test_sun_mode_midday_light_midnight_dark():
    cfg = make_cfg(mode="sun")
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 6, 21, 13, 0, tzinfo=MSK)) == "light"
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 6, 21, 23, 55, tzinfo=MSK)) == "dark"


# --- интерполяция радиации ---

def _fake_forecast(date_iso: str, rads: list[float]) -> dict:
    times = [f"{date_iso}T{h:02d}:00" for h in range(len(rads))]
    return {"current": {"cloud_cover": 75},
            "hourly": {"time": times, "shortwave_radiation": rads}}


def test_effective_sun_times_interpolates_threshold_crossing():
    p = suncalc.WeatherProvider()
    # радиация: 0 до 05:00, потом 100 — порог 50 пересекается в 05:30
    rads = [0, 0, 0, 0, 0, 0, 100, 100, 100, 100, 100, 100,
            100, 100, 100, 100, 100, 0, 0, 0, 0, 0, 0, 0]
    p._cache = (suncalc._now(), 55.8, 37.6, _fake_forecast("2026-07-12", rads))
    sunrise = datetime(2026, 7, 12, 4, 0, tzinfo=MSK)
    sunset = datetime(2026, 7, 12, 21, 0, tzinfo=MSK)
    eff_sr, eff_ss = p.effective_sun_times(
        55.8, 37.6, "Europe/Moscow", sunrise, sunset, max_offset_min=600)
    assert eff_sr == datetime(2026, 7, 12, 5, 30, tzinfo=MSK)
    assert eff_ss == datetime(2026, 7, 12, 16, 30, tzinfo=MSK)


def test_effective_sun_times_clamps_to_max_offset():
    p = suncalc.WeatherProvider()
    rads = [0] * 6 + [100] * 12 + [0] * 6
    p._cache = (suncalc._now(), 55.8, 37.6, _fake_forecast("2026-07-12", rads))
    sunrise = datetime(2026, 7, 12, 4, 0, tzinfo=MSK)
    sunset = datetime(2026, 7, 12, 21, 0, tzinfo=MSK)
    eff_sr, _ = p.effective_sun_times(
        55.8, 37.6, "Europe/Moscow", sunrise, sunset, max_offset_min=30)
    # без clamp был бы 05:30 — ограничен sunrise + 30 мин
    assert eff_sr == sunrise + timedelta(minutes=30)


# --- sun-режим с погодным кешем (сквозной путь determine_target_theme) ---

def test_sun_mode_with_weather_cache_delays_light_theme(monkeypatch):
    """Хмурое утро: радиация переходит порог в 07:30, позже
    астрономического восхода (~04:00) — в 06:00 тема ещё тёмная,
    хотя по чистой астрономии была бы светлой."""
    p = suncalc.WeatherProvider()
    rads = [0] * 8 + [100] * 9 + [0] * 7
    p._cache = (suncalc._now(), 55.7558, 37.6173,
                _fake_forecast("2026-07-12", rads))
    monkeypatch.setattr(suncalc, "weather", p)

    cfg = make_cfg(mode="sun", use_clouds=True, clouds_max_offset_min=600)
    at_6am = datetime(2026, 7, 12, 6, 0, tzinfo=MSK)
    assert suncalc.determine_target_theme(cfg, at_6am) == "dark"
    # без учёта погоды в тот же момент — светлая
    assert suncalc.determine_target_theme(make_cfg(mode="sun"), at_6am) == "light"


def test_sun_mode_weather_clamped_by_max_offset(monkeypatch):
    """Тот же хмурый прогноз, но предел отклонения 30 минут: сдвиг
    обрезается до восход+30, и в 06:00 уже светло."""
    p = suncalc.WeatherProvider()
    rads = [0] * 8 + [100] * 9 + [0] * 7
    p._cache = (suncalc._now(), 55.7558, 37.6173,
                _fake_forecast("2026-07-12", rads))
    monkeypatch.setattr(suncalc, "weather", p)

    cfg = make_cfg(mode="sun", use_clouds=True, clouds_max_offset_min=30)
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 7, 12, 6, 0, tzinfo=MSK)) == "light"


def test_sun_mode_empty_weather_cache_falls_back_to_astronomy(monkeypatch):
    monkeypatch.setattr(suncalc, "weather", suncalc.WeatherProvider())
    cfg = make_cfg(mode="sun", use_clouds=True)
    assert suncalc.determine_target_theme(
        cfg, datetime(2026, 7, 12, 13, 0, tzinfo=MSK)) == "light"


# --- negative-cache и приватность ---

def test_failed_fetch_backs_off_five_minutes(monkeypatch):
    p = suncalc.WeatherProvider()

    def boom(url, timeout):
        raise URLError("no network")

    monkeypatch.setattr(suncalc, "urlopen", boom)
    p._refresh_worker(55.8, 37.6, "Europe/Moscow")   # синхронный путь воркера
    assert p.cached_data(55.8, 37.6) is None
    assert p.needs_refresh(55.8, 37.6) is False      # backoff действует

    later = suncalc._now() + timedelta(minutes=6)
    monkeypatch.setattr(suncalc, "_now", lambda: later)
    assert p.needs_refresh(55.8, 37.6) is True       # 5 минут прошло


def test_successful_cache_expires_after_30_minutes(monkeypatch):
    p = suncalc.WeatherProvider()
    base = suncalc._now()
    monkeypatch.setattr(suncalc, "_now", lambda: base)

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"current": {"cloud_cover": 0}, "hourly": {"time": [], "shortwave_radiation": []}}'

    monkeypatch.setattr(suncalc, "urlopen", lambda url, timeout: FakeResponse())
    p._refresh_worker(55.8, 37.6, "Europe/Moscow")   # успешная загрузка → кеш
    assert p.cached_data(55.8, 37.6) is not None

    almost = base + timedelta(minutes=29)
    monkeypatch.setattr(suncalc, "_now", lambda: almost)
    assert p.needs_refresh(55.8, 37.6) is False      # TTL ещё не истёк

    later = base + timedelta(minutes=31)
    monkeypatch.setattr(suncalc, "_now", lambda: later)
    assert p.needs_refresh(55.8, 37.6) is True       # 30 минут прошло


def test_fetch_url_rounds_coordinates(monkeypatch):
    p = suncalc.WeatherProvider()
    seen = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"current": {"cloud_cover": 0}, "hourly": {"time": [], "shortwave_radiation": []}}'

    def fake_urlopen(url, timeout):
        seen["url"] = url
        return FakeResponse()

    monkeypatch.setattr(suncalc, "urlopen", fake_urlopen)
    p._refresh_worker(55.912345, 36.867890, "Europe/Moscow")
    # точные координаты в сеть не уходят — только 1 знак после запятой
    assert "latitude=55.9" in seen["url"]
    assert "longitude=36.9" in seen["url"]
    assert "55.912345" not in seen["url"]

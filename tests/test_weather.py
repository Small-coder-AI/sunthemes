"""Тесты провайдера Open-Meteo: разбор ответа, кеш, backoff, запасной адрес, приватность."""
import threading
from datetime import datetime, timedelta, timezone

import pytest

from sunthemes import weather

UTC = timezone.utc
T0 = datetime(2026, 9, 23, tzinfo=UTC)


def api_response(hours=3, radiation=None, cloud=None) -> dict:
    """Ответ Open-Meteo с timeformat=unixtime."""
    times = [int((T0 + timedelta(hours=h)).timestamp()) for h in range(hours)]
    return {"hourly": {
        "time": times,
        "shortwave_radiation": radiation if radiation is not None else [0.0] * hours,
        "cloud_cover": cloud if cloud is not None else [50] * hours,
    }}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def provider(fetch=None, clock=None):
    return weather.WeatherProvider(
        fetch_json=fetch or (lambda url, timeout: api_response()),
        clock=clock or FakeClock())


# --- приватность и запрос ---

def test_url_rounds_coordinates_to_about_10_km():
    url = weather.WeatherProvider.url(51.234567, 7.654321)
    # точные координаты в сеть не уходят — только 1 знак после запятой
    assert "latitude=51.2" in url and "longitude=7.7" in url
    assert "51.234567" not in url and "7.654321" not in url
    assert "timeformat=unixtime" in url and "past_days=1" in url


def test_nearby_points_share_one_cache_entry():
    calls = []
    p = provider(lambda url, timeout: calls.append(url) or api_response())
    p.refresh(55.7558, 37.6173)
    p.refresh(55.7512, 37.6199)         # те же ~10 км — повторного запроса нет
    assert len(calls) == 1
    assert p.forecast(55.76, 37.62) is not None


# --- разбор ответа ---

def test_parse_forecast_reads_unixtime_and_skips_nulls():
    fc = weather.parse_forecast(api_response(radiation=[0, None, 120.5], cloud=[None, 80, 90]))
    assert fc.radiation == ((T0, 0.0), (T0 + timedelta(hours=2), 120.5))
    assert fc.cloud_cover == ((T0 + timedelta(hours=1), 80.0), (T0 + timedelta(hours=2), 90.0))
    assert all(t.tzinfo is UTC for t, _ in fc.radiation)


@pytest.mark.parametrize("data", [{}, {"hourly": {}}, {"hourly": {"time": ["x"]}}, []])
def test_parse_forecast_rejects_unexpected_shape(data):
    with pytest.raises(ValueError):
        weather.parse_forecast(data)


def test_forecast_coverage_and_cloud_cover_lookup():
    fc = weather.parse_forecast(api_response(hours=5, cloud=[10, 20, 30, 40, 50]))
    # первое значение — среднее за час ДО метки времени
    assert fc.covers(T0 - timedelta(hours=1), T0 + timedelta(hours=4))
    assert not fc.covers(T0 - timedelta(hours=2), T0 + timedelta(hours=4))
    assert not fc.covers(T0, T0 + timedelta(hours=5))
    assert fc.cloud_cover_at(T0 + timedelta(hours=2, minutes=20)) == 30
    assert fc.cloud_cover_at(T0 + timedelta(hours=9)) is None     # слишком далеко


# --- кеш и повторы ---

def test_failed_fetch_backs_off_five_minutes():
    clock = FakeClock()

    def boom(url, timeout):
        raise OSError("no network")

    p = provider(boom, clock)
    p.refresh(55.8, 37.6)
    assert p.forecast(55.8, 37.6) is None
    assert p.status(55.8, 37.6) == "failed"
    assert p.needs_refresh(55.8, 37.6) is False      # backoff действует
    clock.now += 6 * 60
    assert p.needs_refresh(55.8, 37.6) is True       # 5 минут прошло


def test_successful_fetch_is_cached_for_30_minutes():
    clock = FakeClock()
    p = provider(clock=clock)
    assert p.status(55.8, 37.6) == "idle"
    p.refresh(55.8, 37.6)
    assert p.status(55.8, 37.6) == "ok"
    clock.now += 29 * 60
    assert p.needs_refresh(55.8, 37.6) is False
    clock.now += 2 * 60
    assert p.needs_refresh(55.8, 37.6) is True


def test_failure_after_success_keeps_old_forecast():
    clock = FakeClock()
    responses = [api_response(), OSError("down"), OSError("down")]   # потом лежат оба адреса

    def fetch(url, timeout):
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    p = provider(fetch, clock)
    p.refresh(55.8, 37.6)
    clock.now += 31 * 60
    p.refresh(55.8, 37.6)
    assert p.forecast(55.8, 37.6) is not None        # устаревший, но лучше чем ничего


# --- запасной адрес ---

def blocked(*hosts):
    """fetch_json, для которого адреса `hosts` недоступны; плюс журнал вызовов."""
    calls = []

    def fetch(url, timeout):
        calls.append(url.split("?")[0])
        if any(url.startswith(h) for h in hosts):
            raise OSError("connection reset")
        return api_response()
    return fetch, calls


def test_mirror_serves_forecast_while_primary_is_blocked():
    clock = FakeClock()
    primary, mirror = weather.API_URLS
    fetch, calls = blocked(primary)
    p = provider(fetch, clock)
    p.refresh(55.8, 37.6)
    assert p.status(55.8, 37.6) == "ok"
    assert calls == [primary, mirror]
    # следующий запрос — сразу на ответивший адрес, заблокированный не ждём
    calls.clear()
    clock.now += 31 * 60
    p.refresh(55.8, 37.6)
    assert calls == [mirror]


def test_all_hosts_down_logs_every_error(caplog):
    fetch, calls = blocked(*weather.API_URLS)
    p = provider(fetch)
    p.refresh(55.8, 37.6)
    assert p.status(55.8, 37.6) == "failed"
    assert calls == list(weather.API_URLS)
    assert "api.open-meteo.com: connection reset" in caplog.text
    assert "previous-runs-api.open-meteo.com: connection reset" in caplog.text


def test_status_is_loading_while_request_in_flight():
    seen = {}
    p = provider()

    def fetch(url, timeout):
        seen["status"] = p.status(55.8, 37.6)
        return api_response()

    p._fetch_json = fetch
    p.refresh(55.8, 37.6)
    assert seen["status"] == "loading"


def test_background_refresh_notifies_listener():
    done = threading.Event()
    p = provider()
    p.on_update = done.set
    assert p.refresh_in_background(55.8, 37.6) is True
    assert done.wait(5)
    assert p.forecast(55.8, 37.6) is not None
    assert p.refresh_in_background(55.8, 37.6) is False   # кеш свежий


def test_cache_keeps_a_few_points_only():
    p = provider()
    for i in range(weather.WeatherProvider.MAX_POINTS + 3):
        p.refresh(50 + i, 30)
    assert p.forecast(50, 30) is None                     # самая старая вытеснена
    assert p.forecast(50 + weather.WeatherProvider.MAX_POINTS + 2, 30) is not None


def test_eviction_never_drops_points_being_loaded():
    """Много точек подряд при медленной сети (колесо мыши по списку городов)
    раньше роняло _claim с KeyError."""
    release = threading.Event()
    finished = threading.Semaphore(0)

    def slow_fetch(url, timeout):
        release.wait(5)
        return api_response()

    p = provider(slow_fetch)
    p.on_update = finished.release
    n = weather.WeatherProvider.MAX_POINTS + 2
    for i in range(n):
        assert p.refresh_in_background(50 + i, 30) is True
    release.set()
    for _ in range(n):
        assert finished.acquire(timeout=5)
    assert p.forecast(50 + n - 1, 30) is not None

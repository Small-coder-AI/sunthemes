"""Тесты модели света: пороги высоты солнца, солнечные сутки, облачность."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from astral import Observer
from astral.sun import SunDirection, sunrise, sunset, time_at_elevation

from sunthemes import suncalc

from .forecast_utils import MOSCOW, UTC, hourly_ghi

MSK = ZoneInfo("Europe/Moscow")
MURMANSK = (68.97, 33.08)
SPB = (59.9311, 30.3609)
MINUTE = timedelta(minutes=1)


def noon_of(lat_lon, day: date, tz=MSK):
    """Солнечные сутки, в которые попадает местный полдень `day`."""
    return suncalc.solar_day_noon(lat_lon[1], datetime(day.year, day.month, day.day, 12, tzinfo=tz))


def cloudy(lat_lon, noon, kc):
    """kc(t) из синтетического прогноза с облачностью kc."""
    ghi = hourly_ghi(*lat_lon, noon - timedelta(hours=14), 28, kc)
    return suncalc.interpolator(suncalc.clearness_anchors(*lat_lon, ghi))


# --- базовые функции ---

def test_clear_sky_ghi_zero_at_night_and_grows_with_elevation():
    assert suncalc.clear_sky_ghi(-5) == 0
    assert suncalc.clear_sky_ghi(0) == 0
    values = [suncalc.clear_sky_ghi(h) for h in (1, 3, 5, 10, 30, 60, 90)]
    assert values == sorted(values)
    assert 40 < suncalc.clear_sky_ghi(5) < 60      # ~50 Вт/м² при 5°
    assert 900 < suncalc.clear_sky_ghi(90) < 1100


@pytest.mark.parametrize("lon", [-179.9, -74.0, 0.0, 37.6, 139.65, 179.9])
def test_solar_days_contain_the_moment_and_are_contiguous(lon):
    moment = datetime(2026, 3, 1, tzinfo=UTC)
    for _ in range(50):
        noon = suncalc.solar_day_noon(lon, moment)
        assert noon - suncalc.HALF_DAY <= moment < noon + suncalc.HALF_DAY
        # стык соседних суток — без щели и перекрытия
        assert suncalc.solar_day_noon(lon, noon + suncalc.HALF_DAY) == noon + timedelta(days=1)
        moment += timedelta(hours=7, minutes=13)


# --- астрономия ---

@pytest.mark.parametrize("day", [date(2026, 3, 20), date(2026, 6, 21), date(2026, 12, 21)])
def test_astronomical_day_matches_astral(day):
    observer = Observer(*MOSCOW)
    astro = suncalc.astronomical_day(*MOSCOW, noon_of(MOSCOW, day))
    assert abs(astro.light_from - sunrise(observer, day, tzinfo=MSK)) < 2 * MINUTE
    assert abs(astro.dark_from - sunset(observer, day, tzinfo=MSK)) < 2 * MINUTE


@pytest.mark.parametrize("day", [date(2026, 3, 20), date(2026, 12, 21)])
def test_threshold_matches_astral_time_at_elevation(day):
    observer = Observer(*MOSCOW)
    plan = suncalc.day_plan(*MOSCOW, noon_of(MOSCOW, day), 5, 5)
    rising = time_at_elevation(observer, 5, day, SunDirection.RISING, MSK)
    setting = time_at_elevation(observer, 5, day, SunDirection.SETTING, MSK)
    assert abs(plan.light_from - rising) < 2 * MINUTE
    assert abs(plan.dark_from - setting) < 2 * MINUTE


def test_positive_threshold_means_light_later_and_dark_earlier():
    """Жалоба «вечером тёмная поздно, утром светлая рано»: порог 5° над
    горизонтом сдвигает обе границы к полудню — утро позже восхода,
    вечер раньше заката (в Москве в равноденствие — на ~40 мин)."""
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    astro = suncalc.astronomical_day(*MOSCOW, noon)
    plan = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    assert timedelta(minutes=30) < plan.light_from - astro.light_from < timedelta(minutes=50)
    assert timedelta(minutes=30) < astro.dark_from - plan.dark_from < timedelta(minutes=50)


def test_morning_and_evening_thresholds_are_independent():
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    both5 = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    both0 = suncalc.day_plan(*MOSCOW, noon, 0, 0)
    mixed = suncalc.day_plan(*MOSCOW, noon, 5, 0)
    assert mixed.light_from == both5.light_from
    assert mixed.dark_from == both0.dark_from


def test_polar_night_is_dark_all_day():
    noon = noon_of(MURMANSK, date(2026, 12, 21))
    assert not suncalc.astronomical_day(*MURMANSK, noon).has_light
    plan = suncalc.day_plan(*MURMANSK, noon, 5, 5)
    assert not plan.has_light
    assert not plan.is_light(noon)


def test_polar_day_is_light_all_day_without_gaps_between_days():
    noon = noon_of(MURMANSK, date(2026, 6, 21))
    assert suncalc.astronomical_day(*MURMANSK, noon).light_all_day
    today = suncalc.day_plan(*MURMANSK, noon, 0, 0)
    tomorrow = suncalc.day_plan(*MURMANSK, noon + timedelta(days=1), 0, 0)
    assert today.light_all_day and tomorrow.light_all_day
    assert today.dark_from == tomorrow.light_from     # на стыке суток не темнеет


def test_polar_day_below_threshold_at_midnight_gives_short_night():
    # В полночь солнце в Мурманске 21 июня — на ~2.4°: при пороге 5° тёмная
    # тема включится ненадолго вокруг солнечной полуночи.
    noon = noon_of(MURMANSK, date(2026, 6, 21))
    plan = suncalc.day_plan(*MURMANSK, noon, 5, 5)
    assert plan.has_light and not plan.light_all_day
    assert not plan.is_light(plan.end - timedelta(minutes=1))


def test_threshold_above_noon_sun_gives_dark_day():
    # В Петербурге в декабре солнце поднимается лишь до ~6.6°.
    noon = noon_of(SPB, date(2026, 12, 21))
    assert suncalc.day_plan(*SPB, noon, 5, 5).has_light
    assert not suncalc.day_plan(*SPB, noon, 10, 10).has_light


# --- облачность ---

def test_clearness_anchors_recover_kc_from_hour_averages():
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    ghi = hourly_ghi(*MOSCOW, noon - timedelta(hours=14), 28, kc=0.5)
    anchors = suncalc.clearness_anchors(*MOSCOW, ghi)
    assert 6 <= len(anchors) <= 14                    # только светлые часы
    assert all(abs(k - 0.5) < 0.01 for _, k in anchors)
    ends = {end for end, _ in ghi}
    # kc привязан к середине часа, за который усреднена радиация
    assert all(t + timedelta(minutes=30) in ends for t, _ in anchors)


def test_clear_forecast_keeps_threshold_times():
    """Регрессия: радиация Open-Meteo — среднее за предыдущий час. Прежний
    код считал её мгновенной, и в ясный вечер тема темнела на полчаса позже.
    Ясный прогноз не должен сдвигать границы вовсе."""
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    base = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    clear = suncalc.day_plan(*MOSCOW, noon, 5, 5, clearness=cloudy(MOSCOW, noon, 1.0))
    assert abs(clear.light_from - base.light_from) < MINUTE
    assert abs(clear.dark_from - base.dark_from) < MINUTE


def test_overcast_delays_light_and_advances_dark():
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    base = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    grey = suncalc.day_plan(*MOSCOW, noon, 5, 5, clearness=cloudy(MOSCOW, noon, 0.5))
    assert timedelta(minutes=10) < grey.light_from - base.light_from < timedelta(minutes=40)
    assert timedelta(minutes=10) < base.dark_from - grey.dark_from < timedelta(minutes=40)


def test_cloud_shift_is_capped_by_max_shift():
    noon = noon_of(MOSCOW, date(2026, 6, 21))
    base = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    gloom = suncalc.day_plan(*MOSCOW, noon, 5, 5, clearness=lambda t: 0.05,
                             max_shift=timedelta(minutes=90))
    assert gloom.light_from == base.light_from + timedelta(minutes=90)
    assert gloom.dark_from == base.dark_from - timedelta(minutes=90)


def test_gloomy_short_winter_day_can_stay_dark():
    """Прежний код в такой день (порог радиации не достигнут ни разу)
    откатывался к чистой астрономии — самое длинное светлое окно
    в самый тёмный день. Теперь окно только сжимается."""
    noon = noon_of(MOSCOW, date(2026, 12, 21))
    plan = suncalc.day_plan(*MOSCOW, noon, 5, 5, clearness=lambda t: 0.05,
                            max_shift=timedelta(hours=3))
    assert not plan.has_light


def test_clouds_never_lengthen_the_day():
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    base = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    bright = suncalc.day_plan(*MOSCOW, noon, 5, 5, clearness=cloudy(MOSCOW, noon, 1.3))
    assert bright == base


def test_threshold_at_horizon_ignores_clouds():
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    base = suncalc.day_plan(*MOSCOW, noon, 0, -3)
    grey = suncalc.day_plan(*MOSCOW, noon, 0, -3, clearness=lambda t: 0.2)
    assert grey == base


def test_midday_gloom_does_not_split_the_window():
    """Туча в полдень не должна мигать темой: окно — от первого «светло»
    утром до последнего «светло» вечером."""
    noon = noon_of(MOSCOW, date(2026, 9, 23))
    dip = suncalc.day_plan(
        *MOSCOW, noon, 5, 5,
        clearness=lambda t: 0.05 if abs(t - noon) < timedelta(hours=1) else 1.0)
    assert dip.is_light(noon)
    assert dip == suncalc.day_plan(*MOSCOW, noon, 5, 5)


def test_interpolator_is_linear_inside_and_flat_outside():
    t0 = datetime(2026, 1, 1, 10, tzinfo=UTC)
    kc = suncalc.interpolator([(t0, 0.2), (t0 + timedelta(hours=1), 0.6)])
    assert kc(t0 - timedelta(hours=5)) == pytest.approx(0.2)
    assert kc(t0 + timedelta(minutes=30)) == pytest.approx(0.4)
    assert kc(t0 + timedelta(hours=9)) == pytest.approx(0.6)
    assert suncalc.interpolator([]) is None

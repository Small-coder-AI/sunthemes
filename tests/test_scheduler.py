"""Тесты решений о теме: режимы, ручной выбор, устойчивость к новым прогнозам."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sunthemes import config, suncalc
from sunthemes.scheduler import DARK, LIGHT, ThemeScheduler

from .forecast_utils import MOSCOW, make_forecast

MSK = ZoneInfo("Europe/Moscow")
DAY = date(2026, 9, 23)          # в Москве: восход ~06:16, закат ~18:26


def at(hhmm: str, day: date = DAY) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=MSK)


def make_cfg(**over) -> dict:
    return dict(config.DEFAULT_CONFIG, **over)


class FakeWeather:
    """Кеш погоды без сети: прогноз подменяется прямо в тесте."""

    def __init__(self, forecast=None, status="ok"):
        self.current = forecast
        self._status = status
        self.requests = []

    def forecast(self, lat, lon):
        return self.current

    def status(self, lat, lon):
        return self._status

    def refresh_in_background(self, lat, lon):
        self.requests.append((lat, lon))
        return False


def scheduler(weather=None) -> ThemeScheduler:
    return ThemeScheduler(weather, tz=MSK)


# --- режим «по расписанию»: границы, включая переход через полночь ---

@pytest.mark.parametrize("hhmm,expected", [
    ("06:59", DARK), ("07:00", LIGHT), ("18:59", LIGHT), ("19:00", DARK),
])
def test_time_mode_boundaries(hhmm, expected):
    assert scheduler().evaluate(make_cfg(mode="time"), at(hhmm)).theme == expected


def test_time_mode_inverted_schedule_crosses_midnight():
    cfg = make_cfg(mode="time", light_time="19:00", dark_time="07:00")
    assert scheduler().evaluate(cfg, at("20:00")).theme == LIGHT
    assert scheduler().evaluate(cfg, at("08:00")).theme == DARK


def test_time_mode_next_switch():
    st = scheduler().evaluate(make_cfg(mode="time"), at("20:00"))
    assert (st.next_switch, st.next_theme) == (at("07:00", DAY + timedelta(days=1)), LIGHT)


def test_time_mode_uses_local_wall_clock():
    """Расписание — по часам системы, а не по таймзоне города из конфига."""
    moment = datetime(2026, 9, 23, 7, 30, tzinfo=ZoneInfo("Asia/Tokyo"))  # 01:30 МСК
    tokyo = ThemeScheduler(None, tz=ZoneInfo("Asia/Tokyo"))
    assert tokyo.evaluate(make_cfg(mode="time"), moment).theme == LIGHT
    assert scheduler().evaluate(make_cfg(mode="time"), moment).theme == DARK


# --- режим «по солнцу» ---

def test_sun_mode_default_shifts_both_ends_towards_noon():
    """Жалоба пользователя: вечером тёмная приходила поздно, утром светлая —
    рано. С порогом 5° по умолчанию сразу после восхода ещё тёмная, а
    незадолго до заката уже тёмная."""
    s, cfg = scheduler(), make_cfg()
    assert s.evaluate(cfg, at("06:25")).theme == DARK     # восход ~06:16
    assert s.evaluate(cfg, at("07:05")).theme == LIGHT
    assert s.evaluate(cfg, at("17:40")).theme == LIGHT
    assert s.evaluate(cfg, at("18:10")).theme == DARK     # закат ~18:26
    assert s.evaluate(cfg, at("23:55")).theme == DARK


def test_sun_mode_next_switch_follows_plan():
    s, cfg = scheduler(), make_cfg()
    noon = suncalc.solar_day_noon(MOSCOW[1], at("12:00"))
    today = suncalc.day_plan(*MOSCOW, noon, 5, 5)
    tomorrow = suncalc.day_plan(*MOSCOW, noon + timedelta(days=1), 5, 5)
    st = s.evaluate(cfg, at("12:00"))
    assert (st.next_switch, st.next_theme) == (today.dark_from, DARK)
    st = s.evaluate(cfg, at("23:00"))
    assert (st.next_switch, st.next_theme) == (tomorrow.light_from, LIGHT)


def test_polar_night_has_no_switch_soon():
    cfg = make_cfg(city="custom", lat=68.97, lon=33.08)
    st = scheduler().evaluate(cfg, at("12:00", date(2026, 12, 21)))
    assert st.theme == DARK and st.next_switch is None


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        scheduler().evaluate(make_cfg(), datetime(2026, 9, 23, 12))


# --- ручной выбор ---

def test_manual_choice_holds_until_next_scheduled_switch():
    """Раньше ручная кнопка отменялась ближайшим tick (≤ 1 мин)."""
    s, cfg = scheduler(), make_cfg()
    s.set_manual(DARK, cfg, at("14:00"))
    st = s.evaluate(cfg, at("14:01"))
    assert (st.theme, st.auto_theme, st.manual) == (DARK, LIGHT, True)
    assert s.evaluate(cfg, at("17:00")).theme == DARK
    # вечерняя смена наступила — дальше снова расписание
    st = s.evaluate(cfg, at("18:30"))
    assert (st.theme, st.manual) == (DARK, False)
    assert s.evaluate(cfg, at("09:00", DAY + timedelta(days=1))).theme == LIGHT


def test_manual_choice_reports_when_schedule_resumes():
    s, cfg = scheduler(), make_cfg()
    s.set_manual(LIGHT, cfg, at("21:00"))
    st = s.evaluate(cfg, at("21:01"))
    assert st.theme == LIGHT and st.manual
    assert st.next_switch.astimezone(MSK).date() == DAY + timedelta(days=1)
    assert st.next_theme == LIGHT


def test_choosing_the_scheduled_theme_cancels_manual_mode():
    s, cfg = scheduler(), make_cfg()
    s.set_manual(DARK, cfg, at("14:00"))
    s.set_manual(LIGHT, cfg, at("14:05"))
    assert not s.manual_active
    assert s.evaluate(cfg, at("14:06")).manual is False


def test_manual_choice_expires_after_sleeping_through_switch():
    s, cfg = scheduler(), make_cfg()
    s.set_manual(DARK, cfg, at("14:00"))
    # компьютер проспал до следующего дня — выбор устарел
    st = s.evaluate(cfg, at("14:00", DAY + timedelta(days=1)))
    assert (st.theme, st.manual) == (LIGHT, False)


# --- погода и устойчивость к новым прогнозам ---

def test_overcast_forecast_shifts_switches():
    clear = FakeWeather(make_forecast(*MOSCOW, DAY, kc=1.0))
    grey = FakeWeather(make_forecast(*MOSCOW, DAY, kc=0.3))
    cfg = make_cfg(use_clouds=True)
    moment = at("07:05")                        # по астрономии уже светло
    assert scheduler(clear).evaluate(cfg, moment).theme == LIGHT
    assert scheduler(grey).evaluate(cfg, moment).theme == DARK
    assert scheduler(grey).evaluate(cfg, at("17:40")).theme == DARK


def test_new_forecast_does_not_flip_theme_back_in_the_morning():
    w = FakeWeather(make_forecast(*MOSCOW, DAY, kc=1.0))
    s, cfg = scheduler(w), make_cfg(use_clouds=True)
    assert s.evaluate(cfg, at("07:30")).theme == LIGHT
    w.current = make_forecast(*MOSCOW, DAY, kc=0.1)   # прогноз резко помрачнел
    assert s.evaluate(cfg, at("07:31")).theme == LIGHT
    # а вечерняя граница новому прогнозу следует
    assert s.evaluate(cfg, at("17:00")).theme == DARK


def test_new_forecast_does_not_flip_theme_back_in_the_evening():
    w = FakeWeather(make_forecast(*MOSCOW, DAY, kc=0.3))
    s, cfg = scheduler(w), make_cfg(use_clouds=True)
    assert s.evaluate(cfg, at("17:40")).theme == DARK
    w.current = make_forecast(*MOSCOW, DAY, kc=1.0)   # прояснилось
    assert s.evaluate(cfg, at("17:41")).theme == DARK


def test_changed_settings_reset_frozen_boundaries():
    w = FakeWeather(make_forecast(*MOSCOW, DAY, kc=0.3))
    s = scheduler(w)
    assert s.evaluate(make_cfg(use_clouds=True), at("17:40")).theme == DARK
    assert s.evaluate(make_cfg(use_clouds=False), at("17:41")).theme == LIGHT


def test_weather_is_requested_only_in_sun_mode_with_clouds():
    w = FakeWeather()
    scheduler(w).evaluate(make_cfg(use_clouds=False), at("12:00"))
    scheduler(w).evaluate(make_cfg(mode="time", use_clouds=True), at("12:00"))
    assert w.requests == []
    scheduler(w).evaluate(make_cfg(use_clouds=True), at("12:00"))
    assert w.requests == [MOSCOW]


def test_stale_forecast_is_ignored():
    old = FakeWeather(make_forecast(*MOSCOW, DAY - timedelta(days=5), kc=0.1))
    cfg = make_cfg(use_clouds=True)
    assert scheduler(old).evaluate(cfg, at("07:05")).theme == LIGHT
    assert scheduler(old).preview(cfg, at("12:00")).weather == "failed"


# --- подсказка в окне ---

def test_preview_reports_weather_state():
    cfg = make_cfg(use_clouds=True)
    assert scheduler().preview(make_cfg(), at("12:00")).weather == "off"
    assert scheduler(FakeWeather(status="loading")).preview(cfg, at("12:00")).weather == "loading"
    assert scheduler(FakeWeather(status="failed")).preview(cfg, at("12:00")).weather == "failed"
    p = scheduler(FakeWeather(make_forecast(*MOSCOW, DAY, kc=0.3, cloud=90))).preview(cfg, at("12:00"))
    assert (p.weather, p.cloud_cover) == ("ok", 90)
    assert p.plan.light_from > p.base.light_from and p.plan.dark_from < p.base.dark_from
    assert p.astro.light_from < p.base.light_from     # восход раньше порога 5°


# --- регрессии по ревью ---

def test_manual_choice_follows_a_switch_moved_by_new_forecast():
    """Ручной выбор держится до АКТУАЛЬНОЙ смены: прогноз прояснился —
    вечерняя смена сдвинулась позже, выбор не должен кончиться раньше неё."""
    w = FakeWeather(make_forecast(*MOSCOW, DAY, kc=0.3))
    s, cfg = scheduler(w), make_cfg(use_clouds=True)
    s.set_manual(DARK, cfg, at("14:00"))
    w.current = make_forecast(*MOSCOW, DAY, kc=1.0)
    assert s.evaluate(cfg, at("15:00")).theme == DARK
    st = s.evaluate(cfg, at("17:10"))          # по старому прогнозу смена была ~17:00
    assert (st.theme, st.manual, st.auto_theme) == (DARK, True, LIGHT)


def test_first_forecast_may_correct_a_guess_made_without_it():
    """Сеть поднялась позже старта: светлая «по астрономии» — догадка,
    первый прогноз её поправляет (а следующие уже нет)."""
    w = FakeWeather(None, status="loading")
    s, cfg = scheduler(w), make_cfg(use_clouds=True)
    assert s.evaluate(cfg, at("07:05")).theme == LIGHT
    w.current = make_forecast(*MOSCOW, DAY, kc=0.3)
    assert s.evaluate(cfg, at("07:06")).theme == DARK


def test_evening_stays_dark_after_window_collapsed(monkeypatch):
    """Светлая включилась, затем прогноз «съел» окно целиком — тема
    стала тёмной и больше не возвращается к светлой в эти сутки."""
    s, cfg = scheduler(), make_cfg()
    noon = suncalc.solar_day_noon(MOSCOW[1], at("12:00"))
    minutes = lambda m: noon + timedelta(minutes=m)  # noqa: E731
    plans = iter([
        suncalc.DayPlan(noon, minutes(10), minutes(300)),   # светлая с N+10
        suncalc.DayPlan.dark_all_day(noon),                  # окно исчезло
        suncalc.DayPlan(noon, minutes(15), minutes(180)),   # снова «светло»
    ])
    current = {}

    def fake_plan(cfg_, noon_):
        if noon_ != noon:
            return suncalc.DayPlan.dark_all_day(noon_)
        if "plan" not in current or current.get("advance"):
            current["plan"] = next(plans)
            current["advance"] = False
        return current["plan"]

    monkeypatch.setattr(s, "_plan", fake_plan)
    assert s.evaluate(cfg, minutes(20)).theme == LIGHT
    current["advance"] = True
    assert s.evaluate(cfg, minutes(21)).theme == DARK
    current["advance"] = True
    assert s.evaluate(cfg, minutes(22)).theme == DARK

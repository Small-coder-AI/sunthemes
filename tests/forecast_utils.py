"""Синтетический прогноз для тестов: радиация ясного неба × kc, усреднённая
за ПРЕДЫДУЩИЙ час — ровно в той форме, в какой её отдаёт Open-Meteo."""
from datetime import date, datetime, timedelta, timezone

from astral import Observer

from sunthemes import suncalc
from sunthemes.weather import Forecast

UTC = timezone.utc
MOSCOW = (55.7558, 37.6173)


def hourly_ghi(lat, lon, start: datetime, hours: int, kc=1.0):
    """[(конец часа, средняя GHI за час)]; kc — число или функция kc(t)."""
    observer = Observer(lat, lon)
    out = []
    for h in range(1, hours + 1):
        end = start + timedelta(hours=h)
        samples = [
            suncalc.clear_sky_ghi(suncalc.sun_elevation(
                observer, end - timedelta(minutes=60 - m - 0.5)))
            for m in range(60)
        ]
        k = kc(end - timedelta(minutes=30)) if callable(kc) else kc
        out.append((end, sum(samples) / 60 * k))
    return out


def make_forecast(lat, lon, day: date, kc=1.0, cloud=50) -> Forecast:
    """Как ответ API c past_days=1&forecast_days=2: сутки до и двое после
    начала `day` по UTC."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC) - timedelta(days=1)
    radiation = hourly_ghi(lat, lon, start, 72, kc)
    return Forecast(tuple(radiation), tuple((t, cloud) for t, _ in radiation))

"""Астрономия и модель дневного света: когда за окном «достаточно светло».

Правила модуля:
- Никакого Qt и сети: чистые функции, тестируются без GUI.
- Всё время — TZ-aware datetime; внутренние расчёты — в UTC.

Модель. Светлая тема держится, пока солнце выше порога — высоты над
горизонтом в градусах, отдельной для утра и для вечера. Порог по высоте
физичнее сдвига в минутах: одна и та же высота солнца даёт примерно одну
и ту же освещённость в любой сезон, а положительный порог сдвигает
утреннее переключение позже, а вечернее — раньше. Полярный день и ночь
получаются сами собой, без особых случаев.

Облачность (опционально) поднимает порог. Освещённость под облаками —
kc(t) × G(h(t)), где G — модель ясного неба Haurwitz, h — высота солнца,
kc — индекс ясности из прогноза (см. clearness_anchors). Тема светлая,
пока kc(t)·G(h(t)) ≥ G(порог). Облака только сокращают светлое окно и
не больше чем на max_shift с каждой стороны.
"""

import bisect
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from astral import Observer
from astral.sun import elevation as _astral_elevation

UTC = timezone.utc
HOUR = timedelta(hours=1)
HALF_DAY = timedelta(hours=12)
# Шаг сканирования суток; момент пересечения порога уточняется линейной
# интерполяцией между отсчётами — точность порядка секунд.
SCAN_STEP = timedelta(minutes=2)

# Геометрическая высота центра солнца на восходе/закате (рефракция у
# горизонта + радиус диска) — стандартное определение восхода.
SUNRISE_ELEVATION = -0.833

# Час, в котором ясное небо дало бы меньше этой средней радиации (Вт/м²),
# для kc не используем: у горизонта модели прогноза и ясного неба сильно
# расходятся, отношение превращается в шум.
MIN_CLEAR_SKY_W_M2 = 50.0
# Нижняя граница kc: даже в ливень облака пропускают несколько процентов.
MIN_CLEARNESS = 0.05


def sun_elevation(observer: Observer, when: datetime, refraction: bool = True) -> float:
    """Высота центра солнца над горизонтом, градусы (видимая — с рефракцией)."""
    return _astral_elevation(observer, when.astimezone(UTC), with_refraction=refraction)


def clear_sky_ghi(elevation_deg: float) -> float:
    """Радиация ясного неба на горизонтальную площадку, Вт/м² (модель Haurwitz)."""
    s = math.sin(math.radians(elevation_deg))
    return 1098.0 * s * math.exp(-0.059 / s) if s > 0 else 0.0


def solar_day_noon(lon: float, when: datetime) -> datetime:
    """Середина солнечных суток, в которые попадает `when` (UTC).

    Солнечные сутки — [полдень − 12 ч, полдень + 12 ч), где полдень —
    средний солнечный по долготе. Их граница — солнечная полночь, самое
    тёмное время: переход между сутками не рвёт ни ночь, ни полярный день.
    Соседние сутки стыкуются ровно, без щелей и перекрытий.
    """
    shift = timedelta(hours=lon / 15)
    solar_date = (when.astimezone(UTC) + shift).date()
    return datetime.combine(solar_date, time(12), tzinfo=UTC) - shift


@dataclass(frozen=True)
class DayPlan:
    """Светлое окно одних солнечных суток: светлая тема на [light_from, dark_from).

    Пустое окно (весь день тёмная) — light_from == dark_from == noon.
    Полярный день — окно совпадает с сутками целиком."""

    noon: datetime
    light_from: datetime
    dark_from: datetime

    @classmethod
    def dark_all_day(cls, noon: datetime) -> "DayPlan":
        return cls(noon, noon, noon)

    @property
    def start(self) -> datetime:
        return self.noon - HALF_DAY

    @property
    def end(self) -> datetime:
        return self.noon + HALF_DAY

    @property
    def has_light(self) -> bool:
        return self.light_from < self.dark_from

    @property
    def light_all_day(self) -> bool:
        return self.light_from <= self.start and self.dark_from >= self.end

    def is_light(self, when: datetime) -> bool:
        return self.light_from <= when < self.dark_from


def _scan(observer: Observer, noon: datetime, refraction: bool = True):
    """Отсчёты (время, высота солнца) по солнечным суткам с шагом SCAN_STEP."""
    start = noon - HALF_DAY
    n = int(2 * HALF_DAY / SCAN_STEP)
    times = [start + i * SCAN_STEP for i in range(n + 1)]
    return times, [sun_elevation(observer, t, refraction) for t in times]


def _zero_crossing(t0: datetime, m0: float, t1: datetime, m1: float) -> datetime:
    """Момент, где линейно интерполированный margin проходит через ноль."""
    return t0 + (t1 - t0) * (m0 / (m0 - m1))


def _light_window(times: list[datetime], margins: list[float]):
    """(начало, конец) светлого окна: от первого отсчёта с margin ≥ 0 до
    последнего. Провалы посреди дня окно не рвут — тема не мигает, если
    в полдень набежала туча. None — светлых отсчётов нет."""
    lit = [i for i, m in enumerate(margins) if m >= 0]
    if not lit:
        return None
    i, j = lit[0], lit[-1]
    last = len(times) - 1
    start = times[0] if i == 0 else _zero_crossing(
        times[i - 1], margins[i - 1], times[i], margins[i])
    end = times[last] if j == last else _zero_crossing(
        times[j], margins[j], times[j + 1], margins[j + 1])
    return start, end


def astronomical_day(lat: float, lon: float, noon: datetime) -> DayPlan:
    """Восход и закат (центр солнца на −0.833°) в форме DayPlan — для справки
    в интерфейсе. Пустой план — полярная ночь, окно на все сутки — день."""
    times, elev = _scan(Observer(lat, lon), noon, refraction=False)
    window = _light_window(times, [h - SUNRISE_ELEVATION for h in elev])
    return DayPlan(noon, *window) if window else DayPlan.dark_all_day(noon)


def day_plan(
    lat: float, lon: float, noon: datetime,
    morning_elevation: float, evening_elevation: float,
    clearness: Callable[[datetime], float] | None = None,
    max_shift: timedelta = timedelta(hours=2),
) -> DayPlan:
    """Светлое окно солнечных суток с серединой `noon`.

    До полудня действует утренний порог, после — вечерний. `clearness` —
    kc(t) из прогноза (None — только астрономия). Порог ≤ 0° облака не
    двигают: у горизонта и ниже модель ясного неба даёт ~0 Вт/м².
    """
    times, elev = _scan(Observer(lat, lon), noon)
    thresholds = [morning_elevation if t < noon else evening_elevation for t in times]
    base = _light_window(times, [h - thr for h, thr in zip(elev, thresholds, strict=True)])
    if base is None:
        return DayPlan.dark_all_day(noon)
    light_from, dark_from = base

    if clearness is not None:
        margins = [
            clearness(t) * clear_sky_ghi(h) - clear_sky_ghi(thr) if thr > 0 else h - thr
            for t, h, thr in zip(times, elev, thresholds, strict=True)
        ]
        # Совсем пасмурно (порог не достигнут ни разу) — предельный сдвиг.
        cloudy = _light_window(times, margins) or (
            base[0] + max_shift, base[1] - max_shift)
        light_from = min(max(cloudy[0], base[0]), base[0] + max_shift)
        dark_from = max(min(cloudy[1], base[1]), base[1] - max_shift)

    if light_from >= dark_from:
        return DayPlan.dark_all_day(noon)
    return DayPlan(noon, light_from, dark_from)


def clearness_anchors(
    lat: float, lon: float, hourly_ghi: Iterable[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    """Индекс ясности kc по часам: прогноз ÷ ясное небо за тот же час.

    Open-Meteo отдаёт shortwave_radiation как СРЕДНЕЕ за предыдущий час
    (значение с меткой 18:00 — это 17:00–18:00). Если считать его
    мгновенным, всё смещается на полчаса позже, и вечером тема темнеет
    с опозданием. Поэтому ясное небо усредняется по тому же часу, а kc
    относится к его середине. Часы у горизонта (см. MIN_CLEAR_SKY_W_M2)
    пропускаются. kc ≤ 1: облака не делают день длиннее астрономии.
    """
    observer = Observer(lat, lon)
    sub = HOUR / 12
    anchors: list[tuple[datetime, float]] = []
    for hour_end, ghi in hourly_ghi:
        hour_start = hour_end - HOUR
        clear = sum(
            clear_sky_ghi(sun_elevation(observer, hour_start + (k + 0.5) * sub))
            for k in range(12)
        ) / 12
        if clear < MIN_CLEAR_SKY_W_M2:
            continue
        kc = min(max(ghi / clear, MIN_CLEARNESS), 1.0)
        anchors.append((hour_start + HOUR / 2, kc))
    return anchors


def interpolator(anchors: list[tuple[datetime, float]]) -> Callable[[datetime], float] | None:
    """kc(t): линейно между опорными точками, за краями — ближайшее значение.
    None — если точек нет."""
    if not anchors:
        return None
    ts = [t.timestamp() for t, _ in anchors]
    ks = [k for _, k in anchors]

    def kc(when: datetime) -> float:
        x = when.timestamp()
        i = bisect.bisect_right(ts, x)
        if i == 0:
            return ks[0]
        if i == len(ts):
            return ks[-1]
        frac = (x - ts[i - 1]) / (ts[i] - ts[i - 1])
        return ks[i - 1] + (ks[i] - ks[i - 1]) * frac

    return kc

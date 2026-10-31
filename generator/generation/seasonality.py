"""Сезонные циклы спроса: чистые функции времени.

Интенсивность потока продаж раскладывается на компоненты:

    множитель = 1 + 0.6·суточная + 0.3·недельная + 0.15·годовая + 0.2·зарплатная

Каждая функция возвращает значение в диапазоне ``[-1, 1]``: 1 — максимум
активности, -1 — минимум. Чистые функции легко тестировать на фиксированных
моментах времени и переиспользовать в бэкфилле и в реальном потоке.
"""
from __future__ import annotations

import math
from datetime import datetime

# Доля выходных в недельном профиле: пик в субботу, минимум во вторник.
_WEEKLY = {
    0: -0.20,  # понедельник
    1: -0.25,  # вторник
    2: -0.15,  # среда
    3: -0.05,  # четверг
    4: 0.20,   # пятница: закупка на выходные
    5: 0.40,   # суббота
    6: 0.25,   # воскресенье
}


def diurnal_factor(at: datetime) -> float:
    """Суточный профиль: пик около 19:30, ночной провал около 03:30.

    Основная волна — косинус с максимумом вечером (после работы люди идут
    в магазин), плюс гауссов «провал» ночью, когда почти никто не покупает.
    """
    hour = at.hour + at.minute / 60.0 + at.second / 3600.0
    wave = math.cos(2.0 * math.pi * (hour - 19.5) / 24.0)
    night_dip = math.exp(-((hour - 3.5) ** 2) / 6.0)
    return _clamp(wave - 0.8 * night_dip)


def weekly_factor(at: datetime) -> float:
    """Недельный профиль: выходные активнее будней."""
    return _WEEKLY[at.weekday()]


def annual_factor(at: datetime) -> float:
    """Годовой профиль: максимум в декабре, минимум в июне.

    Для продуктовой сети пик — предновогодние закупки, спад — середина лета
    (часть покупателей на дачах и в отпусках).
    """
    day_of_year = float(at.timetuple().tm_yday)
    return _clamp(math.cos(2.0 * math.pi * (day_of_year - 355.0) / 365.25))


def payday_factor(at: datetime) -> float:
    """«Зарплатные» дни: всплеск в первые и во второй половине месяца."""
    if at.day <= 5 or 15 <= at.day <= 20:
        return 0.25
    return -0.05


def intensity_multiplier(at: datetime) -> float:
    """Итоговый множитель интенсивности потока (обычно 0.1…2.5)."""
    multiplier = (
        1.0
        + 0.60 * diurnal_factor(at)
        + 0.30 * weekly_factor(at)
        + 0.15 * annual_factor(at)
        + 0.20 * payday_factor(at)
    )
    return max(0.05, min(3.0, multiplier))


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))

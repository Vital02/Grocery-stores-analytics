"""Тесты сезонности: чистые функции времени на фиксированных моментах."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.generation.seasonality import (  # noqa: E402
    annual_factor,
    diurnal_factor,
    intensity_multiplier,
    payday_factor,
    weekly_factor,
)

MORNING_RUSH = datetime(2026, 3, 10, 19, 30)   # вечерний пик, вторник
NIGHT = datetime(2026, 3, 10, 3, 30)           # ночной провал
DECEMBER = datetime(2026, 12, 20, 12, 0)       # предновогодний пик
SUMMER = datetime(2026, 6, 20, 12, 0)          # летний спад
SATURDAY = datetime(2026, 3, 14, 12, 0)
MONDAY = datetime(2026, 3, 9, 12, 0)
PAYDAY = datetime(2026, 3, 3, 12, 0)           # первые дни месяца
MID_MONTH = datetime(2026, 3, 12, 12, 0)


class TestDiurnalFactor(unittest.TestCase):
    def test_evening_peak_above_night(self):
        self.assertGreater(diurnal_factor(MORNING_RUSH), diurnal_factor(NIGHT))

    def test_night_is_negative(self):
        self.assertLess(diurnal_factor(NIGHT), 0.0)

    def test_range(self):
        for hour in range(24):
            value = diurnal_factor(datetime(2026, 3, 10, hour))
            self.assertGreaterEqual(value, -1.0)
            self.assertLessEqual(value, 1.0)


class TestWeeklyFactor(unittest.TestCase):
    def test_weekend_above_monday(self):
        self.assertGreater(weekly_factor(SATURDAY), weekly_factor(MONDAY))


class TestAnnualFactor(unittest.TestCase):
    def test_december_above_summer(self):
        self.assertGreater(annual_factor(DECEMBER), annual_factor(SUMMER))


class TestPaydayFactor(unittest.TestCase):
    def test_payday_boost(self):
        self.assertGreater(payday_factor(PAYDAY), payday_factor(MID_MONTH))


class TestIntensityMultiplier(unittest.TestCase):
    def test_evening_above_night(self):
        self.assertGreater(
            intensity_multiplier(MORNING_RUSH), intensity_multiplier(NIGHT)
        )

    def test_saturday_above_monday(self):
        self.assertGreater(
            intensity_multiplier(SATURDAY), intensity_multiplier(MONDAY)
        )

    def test_stays_positive(self):
        for day in range(1, 28):
            for hour in range(24):
                value = intensity_multiplier(datetime(2026, 2, day, hour))
                self.assertGreaterEqual(value, 0.05)


if __name__ == "__main__":
    unittest.main()

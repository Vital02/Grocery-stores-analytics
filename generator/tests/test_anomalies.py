"""Тесты политики аномалий и детерминированного календаря промо."""
from __future__ import annotations

import random
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.generation.anomalies import (  # noqa: E402
    AnomalyKind,
    AnomalyPolicy,
    PromoCalendar,
)


class TestAnomalyPolicy(unittest.TestCase):
    def test_never_with_zero_probability(self):
        policy = AnomalyPolicy(probability=0.0, strength=3.0, rng=random.Random(1))
        for _ in range(200):
            self.assertIsNone(policy.decide())

    def test_always_with_full_probability(self):
        policy = AnomalyPolicy(probability=1.0, strength=3.0, rng=random.Random(1))
        kinds = {policy.decide() for _ in range(50)}
        self.assertNotIn(None, kinds)
        self.assertTrue(kinds.issubset(set(AnomalyKind)))

    def test_strength_is_exposed(self):
        policy = AnomalyPolicy(probability=0.1, strength=4.0, rng=random.Random(1))
        self.assertEqual(policy.strength, 4.0)


class TestPromoCalendar(unittest.TestCase):
    def test_deterministic_for_same_moment(self):
        calendar = PromoCalendar(["Молочные продукты", "Бакалея"], seed=7)
        moment = datetime(2026, 3, 10, 18, 15)
        self.assertEqual(calendar.at(moment), calendar.at(moment))

    def test_categories_are_valid(self):
        categories = ["Молочные продукты", "Бакалея", "Напитки"]
        calendar = PromoCalendar(categories, seed=7)
        base = datetime(2026, 3, 10, 0, 0)
        for minute in range(0, 60 * 24, 15):
            promo = calendar.at(base.replace(minute=minute % 60, hour=minute // 60))
            if promo is not None:
                self.assertIn(promo.category, categories)
                self.assertGreaterEqual(promo.discount, 0.12)
                self.assertLessEqual(promo.discount, 0.30)

    def test_seed_changes_calendar(self):
        moment = datetime(2026, 3, 10, 18, 15)
        a = PromoCalendar(["Категория"], seed=1).at(moment)
        b = PromoCalendar(["Категория"], seed=2).at(moment)
        # Очень маловероятно, что два разных seed'a совпадут и в наличии, и в скидке
        self.assertTrue(a is None or b is None or a.discount != b.discount)


if __name__ == "__main__":
    unittest.main()

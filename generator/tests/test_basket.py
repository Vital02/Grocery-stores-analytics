"""Тесты генератора чеков: детерминизм, структура батча, аномалии."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.config import GeneratorSettings  # noqa: E402
from generator.generation.anomalies import AnomalyKind  # noqa: E402
from generator.generation.basket import BatchGenerator  # noqa: E402
from generator.generation.catalog import ProductCatalog, StoreCatalog  # noqa: E402
from generator.models import SALES_COLUMNS  # noqa: E402


def make_settings(**overrides) -> GeneratorSettings:
    values = {
        "seed": 42,
        "store_count": 6,
        "product_count": 90,
        "orders_per_minute": 600.0,
        "interval_seconds": 2.0,
        "batch_size": 50,
        "anomaly_probability": 0.0,
        "_env_file": None,
    }
    values.update(overrides)
    return GeneratorSettings(**values)


AT = datetime(2026, 3, 10, 19, 30)


class TestCatalogs(unittest.TestCase):
    def test_store_catalog_count(self):
        stores = StoreCatalog(4).stores(AT)
        self.assertEqual(len(stores), 4)
        ids = [store.store_id for store in stores]
        self.assertEqual(ids, sorted(set(ids)))

    def test_store_catalog_rejects_too_many(self):
        with self.assertRaises(ValueError):
            StoreCatalog(99)

    def test_product_catalog_respects_count(self):
        products = ProductCatalog(30, random_like_rng(11)).products(AT)
        self.assertEqual(len(products), 30)
        ids = [p.product_id for p in products]
        self.assertEqual(ids, list(range(1, 31)))

    def test_category_weights_cover_all(self):
        weights = ProductCatalog.category_weights()
        self.assertGreater(len(weights), 0)


def random_like_rng(seed: int):
    import random

    return random.Random(seed)


class TestBatchGenerator(unittest.TestCase):
    def test_deterministic_by_seed(self):
        a = BatchGenerator(make_settings(seed=123)).generate_batch(AT, size=10)
        b = BatchGenerator(make_settings(seed=123)).generate_batch(AT, size=10)
        self.assertEqual(
            [line.as_row() for line in a], [line.as_row() for line in b]
        )

    def test_different_seed_gives_different_flow(self):
        a = BatchGenerator(make_settings(seed=1)).generate_batch(AT, size=10)
        b = BatchGenerator(make_settings(seed=2)).generate_batch(AT, size=10)
        self.assertNotEqual(
            [line.as_row() for line in a], [line.as_row() for line in b]
        )

    def test_batch_contains_network_dimensions(self):
        lines = BatchGenerator(make_settings()).generate_batch(AT, size=20)
        self.assertGreater(len(lines), 0)
        stores = {line.store_id for line in lines}
        categories = {line.category for line in lines}
        self.assertGreater(len(stores), 0)
        self.assertLessEqual(len(stores), 6)
        self.assertGreater(len(categories), 0)
        for line in lines:
            self.assertEqual(len(line.as_row()), len(SALES_COLUMNS))

    def test_orders_for_respects_seasonality(self):
        generator = BatchGenerator(make_settings(orders_per_minute=600.0))
        night = generator.orders_for(datetime(2026, 3, 10, 3, 30))
        evening = generator.orders_for(datetime(2026, 3, 10, 19, 30))
        self.assertGreaterEqual(evening, night)

    def test_orders_for_window_scales_with_duration(self):
        generator = BatchGenerator(make_settings(orders_per_minute=60.0))
        five_minutes = generator.orders_for_window(AT, 300)
        ten_minutes = generator.orders_for_window(AT, 600)
        self.assertGreater(five_minutes, 0)
        self.assertAlmostEqual(ten_minutes, five_minutes * 2, delta=2)

    def test_anomaly_is_marked_when_forced(self):
        settings = make_settings(anomaly_probability=1.0)
        generator = BatchGenerator(settings)
        lines = generator.generate_batch(AT, size=5)
        self.assertTrue(all(line.is_anomaly for line in lines))

    def test_no_anomalies_by_default(self):
        lines = BatchGenerator(make_settings(anomaly_probability=0.0)).generate_batch(
            AT, size=30
        )
        self.assertTrue(all(not line.is_anomaly for line in lines))

    def test_price_glitch_discounts_price(self):
        settings = make_settings(anomaly_probability=0.0)
        generator = BatchGenerator(settings)
        products = {p.product_id: p for p in generator.products}

        with mock.patch.object(
            generator._anomaly_policy, "decide", return_value=AnomalyKind.PRICE_GLITCH
        ):
            for line in generator.generate_batch(AT, size=1):
                expected = float(products[line.product_id].price) * 0.15
                self.assertLess(float(line.unit_price), expected * 1.10)


if __name__ == "__main__":
    unittest.main()

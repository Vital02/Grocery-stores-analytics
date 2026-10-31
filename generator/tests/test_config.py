"""Тесты конфигурации: значения по умолчанию и чтение из окружения."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.config import ClickHouseSettings, GeneratorSettings  # noqa: E402


class GeneratorSettingsTest(unittest.TestCase):
    def test_defaults(self):
        cfg = GeneratorSettings(_env_file=None)
        self.assertEqual(cfg.seed, 42)
        self.assertEqual(cfg.interval_seconds, 2.0)
        self.assertEqual(cfg.batch_size, 20)
        self.assertEqual(cfg.orders_per_minute, 60.0)
        self.assertEqual(cfg.store_count, 6)
        self.assertEqual(cfg.product_count, 90)
        self.assertEqual(cfg.backfill_hours, 24.0)
        self.assertEqual(cfg.anomaly_probability, 0.005)

    def test_env_override(self):
        env = {
            "GENERATOR_SEED": "1001",
            "GENERATOR_INTERVAL_SECONDS": "0.5",
            "GENERATOR_ORDERS_PER_MINUTE": "90",
            "GENERATOR_ANOMALY_PROBABILITY": "0.01",
            "GENERATOR_STORE_COUNT": "5",
            "GENERATOR_PRODUCT_COUNT": "120",
            "GENERATOR_BACKFILL_HOURS": "0",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            cfg = GeneratorSettings(_env_file=None)
        self.assertEqual(cfg.seed, 1001)
        self.assertEqual(cfg.interval_seconds, 0.5)
        self.assertEqual(cfg.orders_per_minute, 90.0)
        self.assertEqual(cfg.anomaly_probability, 0.01)
        self.assertEqual(cfg.store_count, 5)
        self.assertEqual(cfg.backfill_hours, 0.0)

    def test_anomaly_probability_out_of_range(self):
        with self.assertRaises(Exception):
            GeneratorSettings(_env_file=None, anomaly_probability="1.5")

    def test_interval_must_be_positive(self):
        with self.assertRaises(Exception):
            GeneratorSettings(_env_file=None, interval_seconds="0")

    def test_retry_block(self):
        cfg = GeneratorSettings(_env_file=None)
        self.assertEqual(cfg.retry_max_attempts, 5)
        self.assertEqual(cfg.retry_backoff_factor, 2.0)


class ClickHouseSettingsTest(unittest.TestCase):
    def test_defaults(self):
        cfg = ClickHouseSettings(_env_file=None)
        self.assertEqual(cfg.host, "localhost")
        self.assertEqual(cfg.port, 8123)
        self.assertEqual(cfg.database, "grocery")
        self.assertEqual(cfg.user, "default")
        self.assertEqual(cfg.password, "")

    def test_env_override_and_password_masked(self):
        env = {
            "CLICKHOUSE_HOST": "ch",
            "CLICKHOUSE_PORT": "9000",
            "CLICKHOUSE_PASSWORD": "super-secret",
            "CLICKHOUSE_SECURE": "true",
        }
        with mock.patch.dict("os.environ", env, clear=False):
            cfg = ClickHouseSettings(_env_file=None)
        self.assertEqual(cfg.host, "ch")
        self.assertEqual(cfg.port, 9000)
        self.assertTrue(cfg.secure)
        self.assertNotIn("super-secret", cfg.safe_repr())

    def test_invalid_port(self):
        with self.assertRaises(Exception):
            ClickHouseSettings(_env_file=None, port="70000")


if __name__ == "__main__":
    unittest.main()

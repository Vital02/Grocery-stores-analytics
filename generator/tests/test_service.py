"""Тесты сервиса генерации: run_once, backfill, счётчики — на in-memory БД."""
from __future__ import annotations

import sys
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.config import ClickHouseSettings, Settings  # noqa: E402
from generator.config import GeneratorSettings  # noqa: E402
from generator.generation.basket import BatchGenerator  # noqa: E402
from generator.repository.in_memory import InMemoryRepository  # noqa: E402
from generator.retry import RetryPolicy  # noqa: E402
from generator.service.generator import GeneratorService  # noqa: E402


def make_service(**overrides) -> tuple[GeneratorService, InMemoryRepository]:
    values = {
        "seed": 42,
        "store_count": 4,
        "product_count": 40,
        "orders_per_minute": 600.0,
        "interval_seconds": 2.0,
        "batch_size": 10,
        "anomaly_probability": 0.0,
        "backfill_hours": 0.0,
        "_env_file": None,
    }
    values.update(overrides)
    generator_settings = GeneratorSettings(**values)
    settings = Settings(
        generator=generator_settings, clickhouse=ClickHouseSettings(_env_file=None)
    )
    repository = InMemoryRepository()
    sleeps: list[float] = []

    service = GeneratorService(
        settings=settings,
        batch_generator=BatchGenerator(generator_settings),
        repository=repository,
        retry=RetryPolicy(max_attempts=3, base_delay=0.0, max_delay=1.0),
        stop_event=threading.Event(),
        clock=lambda: datetime(2026, 3, 10, 19, 30),
        sleep=sleeps.append,
    )
    return service, repository


class TestRunOnce(unittest.TestCase):
    def test_writes_dimensions_and_one_batch(self):
        service, repository = make_service()
        service.run_once()
        self.assertEqual(len(repository.stores), 4)
        self.assertEqual(len(repository.products), 40)
        self.assertGreater(len(repository.sales), 0)
        self.assertEqual(service.lines_written, len(repository.sales))


class TestBackfill(unittest.TestCase):
    def test_backfill_direct(self):
        service, repository = make_service(backfill_hours=0.02)
        service._backfill_if_needed()
        self.assertGreater(len(repository.sales), 0)
        # повторный вызов: данные уже есть — не дублирует
        before = len(repository.sales)
        service._backfill_if_needed()
        self.assertEqual(len(repository.sales), before)

    def test_backfill_skipped_when_disabled(self):
        service, repository = make_service(backfill_hours=0.0)
        service._backfill_if_needed()
        self.assertEqual(len(repository.sales), 0)


class TestLoop(unittest.TestCase):
    def test_stops_on_stop_event(self):
        service, repository = make_service()
        service._stop_event.set()
        service.run()
        self.assertEqual(len(repository.sales), 0, "остановленный сервис не пишет данные")


if __name__ == "__main__":
    unittest.main()

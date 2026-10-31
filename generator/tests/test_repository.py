"""Тесты in-memory репозитория (порт хранилища)."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.generation.basket import BatchGenerator  # noqa: E402
from generator.config import GeneratorSettings  # noqa: E402
from generator.repository.in_memory import InMemoryRepository  # noqa: E402


class TestInMemoryRepository(unittest.TestCase):
    def test_schema_counter(self):
        repo = InMemoryRepository()
        repo.ensure_schema()
        repo.ensure_schema()
        self.assertEqual(repo.schema_initialized, 2)

    def test_upsert_replaces_dimensions(self):
        repo = InMemoryRepository()
        generator = BatchGenerator(GeneratorSettings(_env_file=None, store_count=3))
        repo.upsert_stores(generator.stores[:2])
        repo.upsert_stores(generator.stores)
        self.assertEqual(len(repo.stores), 3)

    def test_insert_sales_returns_count(self):
        repo = InMemoryRepository()
        lines = BatchGenerator(
            GeneratorSettings(_env_file=None, store_count=3)
        ).generate_batch(datetime(2026, 3, 10, 12, 0), size=5)
        written = repo.insert_sales(lines)
        self.assertEqual(written, len(repo.sales))
        self.assertEqual(repo.sales_count(), len(lines))

    def test_empty_insert_is_noop(self):
        repo = InMemoryRepository()
        self.assertEqual(repo.insert_sales([]), 0)


if __name__ == "__main__":
    unittest.main()

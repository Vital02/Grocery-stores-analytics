"""In-memory реализация репозитория для тестов и запуска без ClickHouse."""
from __future__ import annotations

from generator.models import Product, SaleLine, Store

from .base import Repository


class InMemoryRepository(Repository):
    """Хранит всё в списках: удобно проверять генерацию без БД."""

    def __init__(self) -> None:
        self.schema_initialized = 0
        self.stores: list[Store] = []
        self.products: list[Product] = []
        self.sales: list[SaleLine] = []

    def ensure_schema(self) -> None:
        self.schema_initialized += 1

    def upsert_stores(self, stores: list[Store]) -> None:
        self.stores = list(stores)

    def upsert_products(self, products: list[Product]) -> None:
        self.products = list(products)

    def insert_sales(self, lines: list[SaleLine]) -> int:
        self.sales.extend(lines)
        return len(lines)

    def sales_count(self) -> int:
        return len(self.sales)

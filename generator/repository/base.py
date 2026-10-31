"""Порт хранилища: что генератор умеет делать с БД.

Сервис генерации зависит только от этого интерфейса, поэтому в тестах
подставляется ``InMemoryRepository``, а в проде — ``ClickHouseRepository``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from generator.models import Product, SaleLine, Store


class Repository(ABC):
    """Контракт хранилища справочников и событий потока."""

    @abstractmethod
    def ensure_schema(self) -> None:
        """Создать базу и таблицы, если их ещё нет (идемпотентно)."""

    @abstractmethod
    def upsert_stores(self, stores: list[Store]) -> None:
        """Записать справочник магазинов."""

    @abstractmethod
    def upsert_products(self, products: list[Product]) -> None:
        """Записать справочник товаров."""

    @abstractmethod
    def insert_sales(self, lines: list[SaleLine]) -> int:
        """Записать пачку строк чеков; вернуть число записанных строк."""

    @abstractmethod
    def sales_count(self) -> int:
        """Сколько строк уже в таблице продаж (для решения о backfill)."""

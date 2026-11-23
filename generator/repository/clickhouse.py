"""ClickHouse-реализация репозитория.

Батчевая вставка одним ``INSERT`` (а не построчно), идемпотентная инициализация
схемы при первом запуске и ленивое переиспользуемое соединение — так же, как
в эталонной платформе.
"""
from __future__ import annotations

import logging
from typing import Any

from generator.config import ClickHouseSettings
from generator.models import (
    PRODUCT_COLUMNS,
    SALES_COLUMNS,
    STORE_COLUMNS,
    Product,
    SaleLine,
    Store,
)

from .base import Repository

logger = logging.getLogger(__name__)


class ClickHouseRepository(Repository):
    """Пишет данные в ClickHouse через HTTP-интерфейс (clickhouse-connect)."""

    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: Any | None = None

    # --- Соединение -----------------------------------------------------------

    def _conn(self) -> Any:
        if self._client is None:
            import clickhouse_connect  # импорт ленивый: тесты идут без драйвера

            self._client = clickhouse_connect.get_client(
                host=self._settings.host,
                port=self._settings.port,
                username=self._settings.user,
                password=self._settings.password,
                database=self._settings.database,
                secure=self._settings.secure,
                connect_timeout=self._settings.connect_timeout,
                send_receive_timeout=self._settings.send_receive_timeout,
                query_limit=0,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001 - закрытие не должно ронять процесс
                logger.debug("Ошибка закрытия клиента ClickHouse", exc_info=True)
            self._client = None

    # --- Схема ----------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Создаёт базу и таблицы, если их ещё нет (идемпотентно).

        Материализованные представления и агрегирующие витрины создаются
        init-скриптами ClickHouse — генератор отвечает только за источники.
        """
        db = self._settings.database
        client = self._conn()
        client.command(f"CREATE DATABASE IF NOT EXISTS {db}")
        client.command(
            f"""
            CREATE TABLE IF NOT EXISTS {db}.stores (
                store_id UInt16,
                store_name String,
                city LowCardinality(String),
                district String,
                store_format LowCardinality(String),
                opened_at Date,
                updated_at DateTime
            ) ENGINE = ReplacingMergeTree(updated_at)
            PARTITION BY tuple()
            ORDER BY store_id
            """
        )
        client.command(
            f"""
            CREATE TABLE IF NOT EXISTS {db}.products (
                product_id UInt32,
                sku String,
                product_name String,
                category LowCardinality(String),
                subcategory LowCardinality(String),
                supplier LowCardinality(String),
                unit LowCardinality(String),
                price Decimal(10, 2),
                cost Decimal(10, 2),
                is_organic UInt8,
                is_available UInt8,
                updated_at DateTime
            ) ENGINE = ReplacingMergeTree(updated_at)
            PARTITION BY tuple()
            ORDER BY product_id
            """
        )
        client.command(
            f"""
            CREATE TABLE IF NOT EXISTS {db}.sales (
                event_time DateTime,
                order_id UUID,
                line_no UInt8,
                store_id UInt16,
                city LowCardinality(String),
                store_format LowCardinality(String),
                customer_id UInt32,
                product_id UInt32,
                product_name String,
                category LowCardinality(String),
                quantity Decimal(10, 3),
                unit_price Decimal(10, 2),
                discount_rate Decimal(5, 4),
                revenue Decimal(12, 2),
                cost_amount Decimal(12, 2),
                margin Decimal(12, 2),
                payment_method LowCardinality(String),
                channel LowCardinality(String),
                is_promo UInt8,
                is_anomaly UInt8,
                ingest_time DateTime DEFAULT now()
            ) ENGINE = MergeTree
            PARTITION BY toYYYYMMDD(event_time)
            ORDER BY (city, category, event_time)
            TTL event_time + INTERVAL 180 DAY
            SETTINGS index_granularity = 8192
            """
        )

    # --- Запись ---------------------------------------------------------------

    def upsert_stores(self, stores: list[Store]) -> None:
        if not stores:
            return
        rows = [store.as_row() for store in stores]
        self._conn().insert(
            f"{self._settings.database}.stores", rows, column_names=list(STORE_COLUMNS)
        )

    def upsert_products(self, products: list[Product]) -> None:
        if not products:
            return
        rows = [product.as_row() for product in products]
        self._conn().insert(
            f"{self._settings.database}.products",
            rows,
            column_names=list(PRODUCT_COLUMNS),
        )

    def insert_sales(self, lines: list[SaleLine]) -> int:
        if not lines:
            return 0
        rows = [line.as_row() for line in lines]
        self._conn().insert(
            f"{self._settings.database}.sales",
            rows,
            column_names=list(SALES_COLUMNS),
        )
        return len(rows)

    def sales_count(self) -> int:
        result = self._conn().query(
            f"SELECT count() FROM {self._settings.database}.sales"
        )
        return int(result.first_row[0]) if result.first_row else 0

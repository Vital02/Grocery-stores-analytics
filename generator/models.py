"""Доменные модели предметной области «сеть продуктовых магазинов».

Модели — «чистые» объекты без знания о БД и способе генерации: это ядро
домена, вокруг которого строятся слои генерации, репозиториев и сервиса.
Такое разделение повторяет структуру эталонной платформы и позволяет
тестировать логику без ClickHouse.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


class StoreFormat(enum.StrEnum):
    """Формат магазина — поле-размерность для аналитики."""

    SUPERMARKET = "супермаркет"
    MINIMARKET = "минимаркет"
    DARKSTORE = "даркстор"


class PaymentMethod(enum.StrEnum):
    """Способ оплаты — поле-размерность."""

    CARD = "card"
    SBP = "sbp"
    CASH = "cash"
    ONLINE = "online"


class Channel(enum.StrEnum):
    """Канал продажи — поле-размерность."""

    MOBILE_APP = "mobile_app"
    WEB = "web"
    PICKUP = "pickup"


def money(value: float) -> Decimal:
    """Округление до копеек без сюрпризов двоичной арифметики."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class Store:
    """Справочная запись магазина (справочник/измерение)."""

    store_id: int
    name: str
    city: str
    district: str
    store_format: StoreFormat
    opened_at: date
    updated_at: datetime

    def as_row(self) -> tuple:
        return (
            self.store_id,
            self.name,
            self.city,
            self.district,
            str(self.store_format),
            self.opened_at,
            self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class Product:
    """Справочная запись товара (справочник/измерение)."""

    product_id: int
    sku: str
    name: str
    category: str
    subcategory: str
    supplier: str
    unit: str
    price: Decimal
    cost: Decimal
    is_organic: bool
    is_available: bool
    updated_at: datetime

    def as_row(self) -> tuple:
        return (
            self.product_id,
            self.sku,
            self.name,
            self.category,
            self.subcategory,
            self.supplier,
            self.unit,
            self.price,
            self.cost,
            int(self.is_organic),
            int(self.is_available),
            self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class SaleLine:
    """Строка чека — событие потока продаж.

    Поля:
      * размерности — ``city``, ``category``, ``payment_method``, ``channel``;
      * метрики     — ``quantity``, ``unit_price``, ``revenue``, ``margin``;
      * флаг ``is_anomaly`` помечает редкие выбросы для анализа в Jupyter.
    """

    event_time: datetime
    order_id: uuid.UUID
    line_no: int
    store_id: int
    city: str
    store_format: StoreFormat
    customer_id: int
    product_id: int
    product_name: str
    category: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: float
    revenue: Decimal
    cost_amount: Decimal
    margin: Decimal
    payment_method: PaymentMethod
    channel: Channel
    is_promo: bool
    is_anomaly: bool

    def as_row(self) -> tuple:
        return (
            self.event_time,
            self.order_id,
            self.line_no,
            self.store_id,
            self.city,
            str(self.store_format),
            self.customer_id,
            self.product_id,
            self.product_name,
            self.category,
            self.quantity,
            self.unit_price,
            self.discount_pct,
            self.revenue,
            self.cost_amount,
            self.margin,
            str(self.payment_method),
            str(self.channel),
            int(self.is_promo),
            int(self.is_anomaly),
        )


# Порядок колонок в таблицах ClickHouse (совпадает с clickhouse/init/*.sql).
STORE_COLUMNS = (
    "store_id",
    "store_name",
    "city",
    "district",
    "store_format",
    "opened_at",
    "updated_at",
)

PRODUCT_COLUMNS = (
    "product_id",
    "sku",
    "product_name",
    "category",
    "subcategory",
    "supplier",
    "unit",
    "price",
    "cost",
    "is_organic",
    "is_available",
    "updated_at",
)

SALES_COLUMNS = (
    "event_time",
    "order_id",
    "line_no",
    "store_id",
    "city",
    "store_format",
    "customer_id",
    "product_id",
    "product_name",
    "category",
    "quantity",
    "unit_price",
    "discount_pct",
    "revenue",
    "cost_amount",
    "margin",
    "payment_method",
    "channel",
    "is_promo",
    "is_anomaly",
)

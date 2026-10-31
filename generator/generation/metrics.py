"""Самплеры метрик чека (паттерн Strategy).

Каждая характеристика заказа — отдельная стратегия с единым контрактом
``sample(ctx, rng) -> value``. Генератор чеков комбинирует стратегии, поэтому
добавить новую метрику (например, вес упаковки) можно одним классом, не меняя
остальные — принцип открытости/закрытости, как в эталонной платформе.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from generator.models import Channel, PaymentMethod, Product, Store, money


@dataclass(frozen=True, slots=True)
class StoreProfile:
    """Профиль магазина — «характер» точки, влияющий на генерацию.

    * ``order_rate_per_min`` — базовая частота чеков в минуту;
    * ``basket_mean`` / ``basket_sigma`` — средний размер чека и разброс;
    * ``promo_affinity`` — как охотно магазин участвует в акциях;
    * ``price_index`` — наценка формата (даркстор дешевле супермаркета).
    """

    order_rate_per_min: float
    basket_mean: float
    basket_sigma: float
    promo_affinity: float
    price_index: float


@dataclass(frozen=True, slots=True)
class LineContext:
    """Контекст, общий для самплеров одной строки чека."""

    at: datetime
    store: Store
    product: Product
    promo_category: str | None
    promo_discount: float


class MetricSampler(ABC):
    """Базовый контракт стратегии: вернуть значение метрики для контекста."""

    @abstractmethod
    def sample(self, ctx: LineContext, rng: random.Random) -> Decimal: ...


class BasketSizeSampler:
    """Размер чека: нормальное распределение вокруг среднего по формату."""

    def __init__(self, profile: StoreProfile) -> None:
        self._profile = profile

    def sample(self, rng: random.Random) -> int:
        value = rng.gauss(self._profile.basket_mean, self._profile.basket_sigma)
        return max(1, min(12, int(round(value))))


class UnitPriceSampler(MetricSampler):
    """Цена за единицу: базовая цена каталога × индекс формата + шум."""

    def __init__(self, profile: StoreProfile, noise: float = 0.01) -> None:
        self._profile = profile
        self._noise = noise

    def sample(self, ctx: LineContext, rng: random.Random) -> Decimal:
        price = float(ctx.product.price) * self._profile.price_index
        return money(price * (1.0 + rng.gauss(0.0, self._noise)))


class QuantitySampler(MetricSampler):
    """Количество: для весовых товаров — дробное, для штучных — 1–3."""

    KG_WEIGHTS = (0.4, 0.5, 0.62, 0.75, 1.0, 1.25, 1.5)
    PIECE_WEIGHTS = (0.72, 0.20, 0.08)

    def sample(self, ctx: LineContext, rng: random.Random) -> Decimal:
        if ctx.product.unit == "кг":
            value = rng.choice(self.KG_WEIGHTS)
            return Decimal(str(value)).quantize(Decimal("0.001"))
        pieces = rng.choices((1, 2, 3), weights=self.PIECE_WEIGHTS, k=1)[0]
        return Decimal(pieces).quantize(Decimal("0.001"))


class DiscountSampler(MetricSampler):
    """Скидка: акция категории, случайная промо-цена или без скидки."""

    def __init__(self, profile: StoreProfile, regular_chance: float = 0.07) -> None:
        self._profile = profile
        self._regular_chance = regular_chance

    def sample(self, ctx: LineContext, rng: random.Random) -> Decimal:
        if (
            ctx.promo_category == ctx.product.category
            and rng.random() < 0.75 * self._profile.promo_affinity + 0.2
        ):
            value = ctx.promo_discount
        elif rng.random() < self._regular_chance:
            value = rng.uniform(0.05, 0.15)
        else:
            value = 0.0
        return Decimal(str(round(value, 4)))


_PAYMENT_WEIGHTS = (
    (PaymentMethod.CARD, 0.50),
    (PaymentMethod.SBP, 0.32),
    (PaymentMethod.CASH, 0.10),
    (PaymentMethod.ONLINE, 0.08),
)

_CHANNEL_WEIGHTS = (
    (Channel.MOBILE_APP, 0.46),
    (Channel.PICKUP, 0.32),
    (Channel.WEB, 0.22),
)


def pick_payment_method(rng: random.Random) -> PaymentMethod:
    """Способ оплаты по реалистичным долям (карта и СБП доминируют)."""
    values = [item[0] for item in _PAYMENT_WEIGHTS]
    weights = [item[1] for item in _PAYMENT_WEIGHTS]
    return rng.choices(values, weights=weights, k=1)[0]


def pick_channel(rng: random.Random) -> Channel:
    """Канал продажи: приложение, самовывоз, сайт."""
    values = [item[0] for item in _CHANNEL_WEIGHTS]
    weights = [item[1] for item in _CHANNEL_WEIGHTS]
    return rng.choices(values, weights=weights, k=1)[0]

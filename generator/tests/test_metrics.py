"""Тесты самплеров метрик чека (паттерн Strategy)."""
from __future__ import annotations

import random
import sys
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from generator.generation.metrics import (  # noqa: E402
    BasketSizeSampler,
    DiscountSampler,
    LineContext,
    QuantitySampler,
    StoreProfile,
    UnitPriceSampler,
    pick_channel,
    pick_payment_method,
)
from generator.models import Product, Store, StoreFormat, money  # noqa: E402


def make_product(unit: str = "шт") -> Product:
    return Product(
        product_id=1,
        sku="SKU-TEST-0001",
        name="Тестовый товар",
        category="Бакалея",
        subcategory="Крупы",
        supplier="Поставщик",
        unit=unit,
        price=money(99.0),
        cost=money(79.0),
        is_organic=False,
        is_available=True,
        updated_at=datetime(2026, 3, 10, 12, 0),
    )


def make_store() -> Store:
    return Store(
        store_id=1,
        name="Магазин",
        city="Владивосток",
        district="Центральный",
        store_format=StoreFormat.SUPERMARKET,
        opened_at=datetime(2026, 3, 10).date(),
        updated_at=datetime(2026, 3, 10, 12, 0),
    )


PROFILE = StoreProfile(
    order_rate_per_min=1.0,
    basket_mean=5.0,
    basket_sigma=1.0,
    promo_affinity=1.0,
    price_index=1.0,
)


def make_ctx(product: Product, promo_category: str | None = None) -> LineContext:
    return LineContext(
        at=datetime(2026, 3, 10, 19, 30),
        store=make_store(),
        product=product,
        promo_category=promo_category,
        promo_discount=0.2,
    )


class TestBasketSizeSampler(unittest.TestCase):
    def test_stays_in_bounds(self):
        sampler = BasketSizeSampler(PROFILE)
        rng = random.Random(1)
        for _ in range(100):
            size = sampler.sample(rng)
            self.assertGreaterEqual(size, 1)
            self.assertLessEqual(size, 12)

    def test_around_mean(self):
        sampler = BasketSizeSampler(PROFILE)
        rng = random.Random(2)
        values = [sampler.sample(rng) for _ in range(200)]
        self.assertLess(abs(sum(values) / len(values) - PROFILE.basket_mean), 1.0)


class TestQuantitySampler(unittest.TestCase):
    def test_kg_is_fractional(self):
        sampler = QuantitySampler()
        rng = random.Random(3)
        allowed = {Decimal(str(w)).quantize(Decimal("0.001")) for w in QuantitySampler.KG_WEIGHTS}
        for _ in range(20):
            qty = sampler.sample(make_ctx(make_product("кг")), rng)
            self.assertIn(qty, allowed)

    def test_piece_is_integer(self):
        sampler = QuantitySampler()
        rng = random.Random(4)
        for _ in range(20):
            qty = sampler.sample(make_ctx(make_product("шт")), rng)
            self.assertEqual(qty, qty.quantize(Decimal("1")))


class TestDiscountSampler(unittest.TestCase):
    def test_promo_category_gets_promo_discount(self):
        sampler = DiscountSampler(PROFILE)
        rng = random.Random(5)
        ctx = make_ctx(make_product(), promo_category="Бакалея")
        discounts = {float(sampler.sample(ctx, rng)) for _ in range(50)}
        self.assertIn(0.2, discounts)

    def test_no_discount_without_promo(self):
        sampler = DiscountSampler(PROFILE, regular_chance=0.0)
        rng = random.Random(6)
        ctx = make_ctx(make_product(), promo_category=None)
        for _ in range(20):
            self.assertEqual(float(sampler.sample(ctx, rng)), 0.0)


class TestUnitPriceSampler(unittest.TestCase):
    def test_price_index_scales_price(self):
        expensive = StoreProfile(1.0, 5.0, 1.0, 1.0, 1.05)
        rng = random.Random(7)
        ctx = make_ctx(make_product())
        base = float(UnitPriceSampler(PROFILE).sample(ctx, rng))
        shifted = float(UnitPriceSampler(expensive).sample(ctx, rng))
        self.assertGreater(shifted, base * 1.02)


class TestPickers(unittest.TestCase):
    def test_payment_and_channel_are_valid(self):
        rng = random.Random(8)
        for _ in range(100):
            self.assertIsNotNone(pick_payment_method(rng))
            self.assertIsNotNone(pick_channel(rng))


if __name__ == "__main__":
    unittest.main()

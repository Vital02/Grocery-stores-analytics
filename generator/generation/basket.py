"""Генератор чеков: собирает заказы из позиций по всем магазинам сети.

``OrderGenerator`` — фасад над самплерами: выбирает товары, применяет акцию,
рассчитывает выручку/маржу и при необходимости «ломает» чек аномалией.
``BatchGenerator`` распределяет заказы между магазинами пропорционально
их профилям, поэтому в одном батче присутствуют все точки сети.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from generator.config import GeneratorSettings
from generator.models import (
    Channel,
    PaymentMethod,
    Product,
    SaleLine,
    Store,
    money,
)

from .anomalies import AnomalyKind, AnomalyPolicy, Promo, PromoCalendar
from .catalog import ProductCatalog, StoreCatalog
from .metrics import (
    BasketSizeSampler,
    DiscountSampler,
    LineContext,
    QuantitySampler,
    StoreProfile,
    UnitPriceSampler,
    pick_channel,
    pick_payment_method,
)
from .seasonality import intensity_multiplier

# Во сколько раз «раздувается» чек и позиция при аномалии (при strength=3).
_PANIC_BASKET_MULTIPLIER = (3, 6)
_BULK_QUANTITY_MULTIPLIER = (8, 15)


@dataclass(frozen=True, slots=True)
class _BasketPlan:
    """План чека, подготовленный до генерации строк."""

    store: Store
    order_id: uuid.UUID
    customer_id: int
    payment: PaymentMethod
    channel: Channel
    size: int
    anomaly: AnomalyKind | None


class OrderGenerator:
    """Генерирует один чек магазина в заданный момент времени."""

    def __init__(
        self,
        store: Store,
        profile: StoreProfile,
        products_by_category: dict[str, list[Product]],
        category_weights: dict[str, float],
        promo_calendar: PromoCalendar,
        anomaly_policy: AnomalyPolicy,
        rng: random.Random,
    ) -> None:
        self.store = store
        self._rng = rng
        self._profile = profile
        self._products = products_by_category
        self._category_weights = category_weights
        self._promo_calendar = promo_calendar
        self._anomaly_policy = anomaly_policy

        self._basket = BasketSizeSampler(profile)
        self._price = UnitPriceSampler(profile)
        self._quantity = QuantitySampler()
        self._discount = DiscountSampler(profile)

    def generate(self, at: datetime) -> list[SaleLine]:
        anomaly = self._anomaly_policy.decide()
        promo = self._promo_calendar.at(at)
        plan = self._plan(at, anomaly)

        lines: list[SaleLine] = []
        for line_no in range(1, plan.size + 1):
            lines.append(self._make_line(at, line_no, plan, promo))
        return lines

    # --- Внутренние шаги ------------------------------------------------------

    def _plan(self, at: datetime, anomaly: AnomalyKind | None) -> _BasketPlan:
        rng = self._rng
        size = self._basket.sample(rng)
        if anomaly == AnomalyKind.PANIC_BUYING:
            size *= rng.randint(*_PANIC_BASKET_MULTIPLIER)
            # Сила аномалии масштабирует всплеск (strength=3 — базовый сценарий).
            size = min(int(size * self._anomaly_policy.strength / 3.0), 40)

        return _BasketPlan(
            store=self.store,
            order_id=uuid.UUID(int=rng.getrandbits(128), version=4),
            customer_id=rng.randint(1, 50_000),
            payment=pick_payment_method(rng),
            channel=pick_channel(rng),
            size=max(1, size),
            anomaly=anomaly,
        )

    def _pick_product(self, promo: Promo | None) -> Product:
        rng = self._rng
        weights = dict(self._category_weights)
        if promo is not None:
            weights[promo.category] = weights.get(promo.category, 0.5) * 3.0
        category = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
        return rng.choice(self._products[category])

    def _make_line(
        self,
        at: datetime,
        line_no: int,
        plan: _BasketPlan,
        promo: Promo | None,
    ) -> SaleLine:
        rng = self._rng
        product = self._pick_product(promo)

        ctx = LineContext(
            at=at,
            store=plan.store,
            product=product,
            promo_category=promo.category if promo else None,
            promo_discount=promo.discount if promo else 0.0,
        )

        unit_price = self._price.sample(ctx, rng)
        quantity = self._quantity.sample(ctx, rng)
        discount = float(self._discount.sample(ctx, rng))
        is_promo = promo is not None and product.category == promo.category

        # Аномалии: оптовая закупка одной позиции или сбой ценника.
        if plan.anomaly == AnomalyKind.BULK_PURCHASE:
            factor = max(1.0, self._anomaly_policy.strength / 3.0)
            low, high = _BULK_QUANTITY_MULTIPLIER
            quantity *= Decimal(rng.randint(int(low * factor), int(high * factor)))
            quantity = quantity.quantize(Decimal("0.001"))
        elif plan.anomaly == AnomalyKind.PRICE_GLITCH:
            # «Сбой ценника»: цена падает до доли номинала (strength=3 → 15 %).
            unit_price = money(float(unit_price) * (0.45 / max(self._anomaly_policy.strength, 1.0)))

        revenue = money(float(unit_price) * float(quantity) * (1.0 - discount))
        cost_amount = money(float(product.cost) * float(quantity))

        return SaleLine(
            event_time=at,
            order_id=plan.order_id,
            line_no=line_no,
            store_id=plan.store.store_id,
            city=plan.store.city,
            store_format=plan.store.store_format,
            customer_id=plan.customer_id,
            product_id=product.product_id,
            product_name=product.name,
            category=product.category,
            quantity=quantity,
            unit_price=unit_price,
            discount_pct=round(discount, 4),
            revenue=revenue,
            cost_amount=cost_amount,
            margin=money(float(revenue) - float(cost_amount)),
            payment_method=plan.payment,
            channel=plan.channel,
            is_promo=is_promo,
            is_anomaly=plan.anomaly is not None,
        )


class BatchGenerator:
    """Производит пачку чеков по сети на текущий момент времени.

    Количество чеков в пачке зависит от сезонности: днём и в выходные поток
    больше, ночью — меньше. Это та же логика, что и в эталонной платформе
    (сезонные множители), но применённая к интенсивности заказов.
    """

    def __init__(
        self,
        settings: GeneratorSettings,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings
        self._rng = rng or random.Random(settings.seed)

        store_catalog = StoreCatalog(settings.store_count)
        self._stores = store_catalog.stores(datetime.now())
        product_catalog = ProductCatalog(settings.product_count, self._rng)
        self._products = product_catalog.products(datetime.now())
        self._category_weights = ProductCatalog.category_weights()

        products_by_category: dict[str, list[Product]] = {}
        for product in self._products:
            products_by_category.setdefault(product.category, []).append(product)
        self._products_by_category = products_by_category

        self._promo_calendar = PromoCalendar(
            list(products_by_category), settings.seed
        )
        self._anomaly_policy = AnomalyPolicy(
            probability=settings.anomaly_probability,
            strength=settings.anomaly_strength,
            rng=self._rng,
        )

        self._generators = [
            OrderGenerator(
                store=store,
                profile=store_catalog.profile_for(store),
                products_by_category=products_by_category,
                category_weights=self._category_weights,
                promo_calendar=self._promo_calendar,
                anomaly_policy=self._anomaly_policy,
                rng=self._rng,
            )
            for store in self._stores
        ]
        self._store_weights = [
            store_catalog.profile_for(store).order_rate_per_min for store in self._stores
        ]

    @property
    def stores(self) -> list[Store]:
        return list(self._stores)

    @property
    def products(self) -> list[Product]:
        return list(self._products)

    def orders_for(self, at: datetime) -> int:
        """Сколько чеков сгенерировать за один тик с учётом сезонности."""
        base = (
            self._settings.orders_per_minute / 60.0
            * self._settings.interval_seconds
        )
        count = int(round(base * intensity_multiplier(at)))
        return max(1, min(self._settings.batch_size, count))

    def orders_for_window(self, at: datetime, window_sec: float) -> int:
        """Сколько чеков сгенерировать для исторического окна (backfill).

        Живой тик и backfill используют одну и ту же интенсивность:
        чеков в окне = orders_per_minute * длительность окна * сезонность.
        """
        if window_sec <= 0:
            return 0
        base = self._settings.orders_per_minute / 60.0 * window_sec
        count = int(round(base * intensity_multiplier(at)))
        return max(0, count)

    def generate_batch(self, at: datetime, size: int | None = None) -> list[SaleLine]:
        """Сгенерировать пачку чеков и вернуть плоский список строк."""
        orders = self.orders_for(at) if size is None else size
        lines: list[SaleLine] = []
        for _ in range(orders):
            generator = self._rng.choices(
                self._generators, weights=self._store_weights, k=1
            )[0]
            lines.extend(generator.generate(at))
        return lines

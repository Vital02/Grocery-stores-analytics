"""Политика редких аномалий и акций.

Аномалии нужны как «дрожжи» для последующего анализа: их ищут в Jupyter
статистикой (z-score), поэтому в потоке должны встречаться редкие, но заметные
отклонения. Здесь аномалия — это **тип** отклонения, а конкретная величина
(сила) вычисляется генератором чека на основе ``strength``.

Промо-акции — не аномалия, а плановая механика: в каждом 30-минутном окне
одна категория получает скидку, и это детерминированно воспроизводится
(одинаково при бэкфилле и в реальном потоке).
"""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass
from datetime import datetime

PROMO_WINDOW_SEC = 1800
PROMO_PROBABILITY = 0.45
PROMO_DISCOUNT_RANGE = (0.12, 0.30)


class AnomalyKind(enum.StrEnum):
    """Типы аномалий, которые может генерировать система."""

    PANIC_BUYING = "panic_buying"  # аномально крупный чек (закупка впрок)
    PRICE_GLITCH = "price_glitch"  # сбой ценника: огромная скидка
    BULK_PURCHASE = "bulk_purchase"  # оптовая закупка одной позиции


class AnomalyPolicy:
    """Решает, случится ли аномалия в чеке и какая именно."""

    def __init__(self, probability: float, strength: float, rng: random.Random) -> None:
        self._probability = probability
        self._strength = strength
        self._rng = rng

    @property
    def strength(self) -> float:
        """Сила аномалии (множитель), настраивается извне."""
        return self._strength

    def decide(self) -> AnomalyKind | None:
        """Возвращает тип аномалии для текущего чека или ``None``."""
        if self._rng.random() >= self._probability:
            return None
        return self._rng.choice(list(AnomalyKind))


@dataclass(frozen=True, slots=True)
class Promo:
    """Действующая акция: категория и размер скидки."""

    category: str
    discount: float


class PromoCalendar:
    """Детерминированный календарь промо-акций по 30-минутным окнам.

    Одинаковое окно времени всегда даёт одну и ту же акцию, поэтому бэкфилл
    истории и живой поток согласованы между собой и воспроизводимы.
    """

    def __init__(self, categories: list[str], seed: int) -> None:
        self._categories = sorted(categories)
        self._seed = seed
        self._cache: dict[int, Promo | None] = {}

    def at(self, moment: datetime) -> Promo | None:
        bucket = int(moment.timestamp()) // PROMO_WINDOW_SEC
        if bucket in self._cache:
            return self._cache[bucket]

        local_rng = random.Random((bucket * 2_654_435_761 + self._seed) & 0x7FFFFFFF)
        promo: Promo | None = None
        if local_rng.random() < PROMO_PROBABILITY and self._categories:
            promo = Promo(
                category=local_rng.choice(self._categories),
                discount=local_rng.uniform(*PROMO_DISCOUNT_RANGE),
            )

        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[bucket] = promo
        return promo

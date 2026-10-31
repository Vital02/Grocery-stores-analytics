"""Retry с экспоненциальным backoff для устойчивости к отказам БД.

``RetryPolicy`` оборачивает вызов, который может упасть (например, запись
в ClickHouse), и повторяет его с нарастающей паузой и случайным джиттером.
После исчерпания попыток перевыбрасывается ``RetryError``.
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryError(Exception):
    """Все попытки исчерпаны."""


class RetryPolicy:
    """Настраиваемая политика повторных попыток."""

    def __init__(
        self,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
        backoff_factor: float = 2.0,
        jitter: float = 0.1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._backoff_factor = backoff_factor
        self._jitter = jitter
        self._sleep = sleep

    def execute(self, fn: Callable[[], T]) -> T:
        """Выполняет ``fn`` с повторами. Возвращает результат или бросает ошибку."""
        attempt = 0
        while True:
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - драйвер кидает разные типы
                attempt += 1
                if attempt >= self._max_attempts:
                    raise RetryError(
                        f"действие не удалось после {self._max_attempts} попыток"
                    ) from exc
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "Сбой попытки %d/%d (%s); повтор через %.2fs",
                    attempt,
                    self._max_attempts,
                    exc,
                    delay,
                )
                self._sleep(delay)

    def _backoff_delay(self, attempt: int) -> float:
        base = self._base_delay * (self._backoff_factor ** (attempt - 1))
        capped = min(base, self._max_delay)
        return capped * (1.0 + random.uniform(-self._jitter, self._jitter))

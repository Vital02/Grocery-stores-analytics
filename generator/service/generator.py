"""Сервис генерации: оркестрирует цикл «произвести чеки → записать в БД».

Сервис ничего не знает о конкретной БД и о том, как именно генерируются данные
— он зависит от абстракций (порт ``Repository``, ``BatchGenerator``,
``RetryPolicy``). Это даёт возможность подменять реализации в тестах и
запускать генератор без ClickHouse (in-memory репозиторий).
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from generator.config import Settings
from generator.generation.basket import BatchGenerator
from generator.repository.base import Repository
from generator.retry import RetryError, RetryPolicy

Clock = Callable[[], datetime]

logger = logging.getLogger(__name__)

# Шаг backfill — 1 минута: совпадает с гранулой минутной витрины
# sales_per_minute. Все чеки окна получают event_time на границе минуты,
# поэтому история ложится на минутный график равномерно — без «ступенек»,
# как было бы при более крупном шаге (все чеки окна склеивались бы в одну
# точку графика).
BACKFILL_STEP_SEC = 60
BACKFILL_CHUNK_ROWS = 50_000     # размер батча вставки при backfill


def utc_now() -> datetime:
    return datetime.now()


class GeneratorService:
    """Основной цикл генератора данных продуктовой сети."""

    def __init__(
        self,
        *,
        settings: Settings,
        batch_generator: BatchGenerator,
        repository: Repository,
        retry: RetryPolicy,
        stop_event: threading.Event,
        clock: Clock = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._batch_generator = batch_generator
        self._repository = repository
        self._retry = retry
        self._stop_event = stop_event
        self._clock = clock
        self._sleep = sleep

        # Счётчики для health-эндпоинта и финального отчёта.
        self.lines_generated = 0
        self.anomalies_generated = 0
        self.lines_written = 0
        self.last_insert_at: float | None = None

    # ------------------------------------------------------------------ запуск
    def run(self) -> None:
        """Запускает цикл генерации до сигнала остановки."""
        logger.info("Инициализация схемы и справочников сети...")
        self._retry.execute(self._repository.ensure_schema)
        self._write_dimensions()
        logger.info(
            "Магазинов: %d, SKU: %d. Запуск генерации "
            "(до %d чеков за тик, интервал %.2fs)",
            len(self._batch_generator.stores),
            len(self._batch_generator.products),
            self._settings.generator.batch_size,
            self._settings.generator.interval_seconds,
        )

        try:
            self._backfill_if_needed()
            while not self._stop_event.is_set():
                self._produce_and_store_batch()
        except RetryError as exc:
            logger.error("Запись данных не удалась: %s", exc)
        finally:
            logger.info(
                "Генератор остановлен: сгенерировано %d строк чеков "
                "(аномалий %d), записано %d",
                self.lines_generated,
                self.anomalies_generated,
                self.lines_written,
            )

    def run_once(self) -> None:
        """Инициализирует схему, пишет справочники и один батч чеков."""
        logger.info("Инициализация схемы и справочников сети...")
        self._retry.execute(self._repository.ensure_schema)
        self._write_dimensions()
        self._produce_and_store_batch()
        logger.info("Один батч записан, завершение.")

    # ----------------------------------------------------------- внутреннее
    def _write_dimensions(self) -> None:
        stores = self._batch_generator.stores
        products = self._batch_generator.products
        self._retry.execute(lambda: self._repository.upsert_stores(stores))
        self._retry.execute(lambda: self._repository.upsert_products(products))
        logger.info(
            "Справочники записаны: магазинов %d, товаров %d",
            len(stores),
            len(products),
        )

    def _backfill_if_needed(self) -> None:
        """Одноразовая генерация истории, чтобы дашборд был осмысленным сразу."""
        hours = self._settings.generator.backfill_hours
        if hours <= 0:
            return
        if self._retry.execute(self._repository.sales_count) > 0:
            logger.info("В grocery.sales уже есть данные — backfill не нужен")
            return

        logger.info("БД пуста: генерирую %.1f ч истории...", hours)
        now = self._clock()
        cursor = now - timedelta(hours=hours)
        total = 0
        anomalies = 0
        started = time.monotonic()

        chunk: list = []
        while cursor < now:
            step_end = min(cursor + timedelta(seconds=BACKFILL_STEP_SEC), now)
            size = self._batch_generator.orders_for_window(
                step_end, (step_end - cursor).total_seconds()
            )
            batch = (
                self._batch_generator.generate_batch(step_end, size=size)
                if size
                else []
            )
            chunk.extend(batch)
            anomalies += sum(1 for line in batch if line.is_anomaly)
            cursor = step_end

            if len(chunk) >= BACKFILL_CHUNK_ROWS:
                total += self._retry.execute(
                    lambda rows=chunk: self._repository.insert_sales(rows)
                )
                self.last_insert_at = time.time()
                chunk = []

        if chunk:
            total += self._retry.execute(
                lambda rows=chunk: self._repository.insert_sales(rows)
            )
            self.last_insert_at = time.time()

        self.lines_generated += total
        self.lines_written += total
        self.anomalies_generated += anomalies
        logger.info(
            "Backfill за %.1f ч: %d строк за %.1f с",
            hours,
            total,
            time.monotonic() - started,
        )

    def _produce_and_store_batch(self) -> None:
        started = time.monotonic()
        batch = self._batch_generator.generate_batch(self._clock())
        written = self._retry.execute(
            lambda: self._repository.insert_sales(batch)
        )
        self.lines_generated += len(batch)
        self.lines_written += written
        self.anomalies_generated += sum(1 for line in batch if line.is_anomaly)
        self.last_insert_at = time.time()
        logger.debug("Записано %d строк (аномалий: %d)", written, sum(1 for l in batch if l.is_anomaly))
        self._sleep(self._remaining(started))

    def _remaining(self, started: float) -> float:
        elapsed = time.monotonic() - started
        return max(0.0, self._settings.generator.interval_seconds - elapsed)


def build_service(
    *,
    settings: Settings,
    batch_generator: BatchGenerator,
    repository: Repository,
    stop_event: threading.Event,
) -> GeneratorService:
    """Композиционный корень: собирает сервис с политикой retry из настроек."""
    retry = RetryPolicy(
        max_attempts=settings.generator.retry_max_attempts,
        base_delay=settings.generator.retry_base_delay_seconds,
        max_delay=settings.generator.retry_max_delay_seconds,
        backoff_factor=settings.generator.retry_backoff_factor,
    )
    return GeneratorService(
        settings=settings,
        batch_generator=batch_generator,
        repository=repository,
        retry=retry,
        stop_event=stop_event,
    )

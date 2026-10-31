"""CLI генератора.

Запуск:
    python -m generator              # обычный режим (docker-compose)
    python -m generator --once       # схемы + справочники + один батч, и выход
    python -m generator --dry-run 3  # показать чеки без записи в БД
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from datetime import datetime
from typing import Sequence

from generator.config import GeneratorSettings, get_settings
from generator.generation.basket import BatchGenerator
from generator.health import HealthServer, HealthState
from generator.repository.in_memory import InMemoryRepository
from generator.service.generator import GeneratorService, build_service

logger = logging.getLogger("generator")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


def run_forever(service: GeneratorService, health: HealthServer, stop_event: threading.Event) -> int:
    """Обычный режим: цикл генерации до SIGTERM/SIGINT."""
    def handle_signal(signum: int, _frame: object) -> None:
        logger.info("Получен сигнал %s — завершаю работу корректно", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    health.start()
    try:
        service.run()
        return 0
    finally:
        health.stop()


def dry_run(settings: GeneratorSettings, orders: int) -> int:
    """Проверка модели без БД: печает статистику по сгенерированным чекам."""
    generator = BatchGenerator(settings)
    at = datetime.now()
    lines = generator.generate_batch(at, size=orders)

    revenue = sum(float(line.revenue) for line in lines)
    anomalies = sum(1 for line in lines if line.is_anomaly)
    promo = sum(1 for line in lines if line.is_promo)
    stores = {line.store_id for line in lines}
    categories = {line.category for line in lines}

    print(f"чеков: {orders}, строк чеков: {len(lines)}")
    print(f"выручка: {revenue:,.2f} ₽")
    print(f"аномалий: {anomalies}, промо-строк: {promo}")
    print(f"магазинов: {len(stores)}, категорий: {len(categories)}")
    for line in lines[:3]:
        print("пример:", line.as_row())
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m generator",
        description="Генератор потока продаж продуктовой сети",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="инициализировать схему, записать справочники и один батч, затем выйти",
    )
    parser.add_argument(
        "--dry-run",
        type=int,
        metavar="N",
        help="сгенерировать N чеков без записи в ClickHouse и вывести статистику",
    )
    parser.add_argument("--log-level", default=None, help="переопределить GENERATOR_LOG_LEVEL")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    setup_logging(args.log_level or settings.generator.log_level)

    if args.dry_run:
        return dry_run(settings.generator, args.dry_run)

    batch_generator = BatchGenerator(settings.generator)
    if args.once:
        repository = InMemoryRepository()
    else:
        # ClickHouse-репозиторий появляется вместе с хранилищем: генератор
        # первого этапа умеет работать и без него (in-memory / --once).
        from generator.repository.clickhouse import ClickHouseRepository

        logger.info("ClickHouse: %s", settings.clickhouse.safe_repr())
        repository = ClickHouseRepository(settings.clickhouse)

    stop_event = threading.Event()
    service = build_service(
        settings=settings,
        batch_generator=batch_generator,
        repository=repository,
        stop_event=stop_event,
    )
    health = HealthServer(settings.generator.health_port, HealthState(repository, service))

    if args.once:
        service.run_once()
        return 0
    return run_forever(service, health, stop_event)


if __name__ == "__main__":
    sys.exit(main())

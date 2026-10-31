# Продуктовая сеть: аналитика продаж

Учебный проект: end-to-end система сбора и анализа потока продаж продуктовой
сети. Генератор событий → ClickHouse → BI (Apache Superset) и Jupyter.

**Статус:** в работе. Первый этап — генератор потока продаж. Архитектура
повторяет эталонную платформу потоковой генерации: домен отделён от генерации,
генерация — от хранилища (порт `Repository`), оркестрация — в сервисе.

---

## Что уже сделано

- [x] Доменные модели: `Store`, `Product`, `SaleLine` — «чистые» объекты без
      знания о БД (`generator/models.py`)
- [x] Справочники сети: магазины с профилями формата, каталог SKU с ценами и
      маржой (`generator/generation/catalog.py`)
- [x] Сезонность чистыми функциями времени: суточная волна, день недели,
      годовой цикл, «зарплатные» дни (`generation/seasonality.py`)
- [x] Аномалии как типы: `PANIC_BUYING` / `BULK_PURCHASE` / `PRICE_GLITCH`,
      детерминированный промо-календарь (`generation/anomalies.py`)
- [x] Самплеры чека — паттерн Strategy: размер корзины, цена, количество,
      скидка (`generation/metrics.py`)
- [x] Сборка чеков и батчей с учётом сезонности (`generation/basket.py`)
- [x] Сервис генерации «произвести батч → записать» с инъекцией часов и сна
      (`service/generator.py`)
- [x] Retry с экспоненциальным backoff (`retry.py`)
- [x] In-memory репозиторий: генератор работает без какой-либо БД
      (`repository/in_memory.py`)
- [x] Конфигурация из env с префиксом `GENERATOR_*` (`config.py`)
- [x] 55 юнит-тестов (`generator/tests/`, unittest)

## Быстрый старт (генератор без Docker)

```bash
pip install -r generator/requirements.txt

# чеки без записи в БД: статистика по выручке, аномалиям, промо
python -m generator --dry-run 5

# справочники + один батч в in-memory хранилище
python -m generator --once

# юнит-тесты
cd generator && python -m unittest discover -s tests -v
```

## Структура

```
.
├── README.md
├── .gitignore / .gitattributes
└── generator/
    ├── cli.py               # точка входа: python -m generator
    ├── config.py            # pydantic-settings, GENERATOR_*
    ├── models.py            # домен: Store, Product, SaleLine
    ├── retry.py             # RetryPolicy (экспоненциальный backoff)
    ├── health.py            # /healthz, /readyz, /metrics
    ├── Dockerfile
    ├── generation/          # «как генерировать»: seasonality, anomalies,
    │                        #  metrics (Strategy), catalog, basket
    ├── repository/          # порт Repository + in_memory реализация
    ├── service/             # оркестратор цикла генерации
    └── tests/               # 55 юнит-тестов
```

## Дальше по плану

1. Хранилище ClickHouse: схема `grocery`, витрины и Materialized View;
   ClickHouse-реализация репозитория и docker-compose.
2. Superset: подключение к ClickHouse, датасеты, дашборд и фильтры.
3. Jupyter: аналитические запросы и графики.
4. Документация, проверки и runbook.

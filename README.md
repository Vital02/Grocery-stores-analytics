# Продуктовая сеть: аналитика продаж

Учебный проект: end-to-end система сбора и анализа потока продаж продуктовой
сети. Генератор событий → ClickHouse → BI (Apache Superset) и Jupyter.

**Статус:** в работе. Хранилище готово и подключено к генератору: ClickHouse
хранит поток позиций чеков, витрины считают агрегаты, Materialized View
наполняются при каждой вставке — в реальном времени.

---

## Что уже сделано

- [x] Генератор потока продаж: сезонность, промо, аномалии, батчи, retry
- [x] Схема БД `grocery`: справочники `stores` / `products` и поток `sales`
- [x] Витрины `sales_per_minute` (`SummingMergeTree`) и `category_hourly`
      (`AggregatingMergeTree`)
- [x] Materialized View, которые наполняют витрины при вставке
- [x] ClickHouse-репозиторий: батчевый `INSERT`, идемпотентное создание схемы,
      backfill истории при пустой БД (`generator/repository/clickhouse.py`)
- [x] docker-compose: сервисы ClickHouse и генератора с healthcheck
- [ ] Дашборд Superset
- [ ] Ноутбук с анализом

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d

# поток пошёл: количество строк растёт каждые пару секунд
docker compose exec clickhouse clickhouse-client \
  --user=default --password=clickhouse_secret \
  -q "SELECT count() AS rows, max(event_time) FROM grocery.sales"
```

Проверка витрин и Materialized View:

```sql
SHOW TABLES FROM grocery;
SELECT name FROM system.tables WHERE name LIKE 'mv_%';
SELECT category, sumMerge(revenue_state) AS revenue
FROM grocery.category_hourly GROUP BY category ORDER BY revenue DESC;
```

## Структура

```
.
├── docker-compose.yml     # ClickHouse + генератор
├── .env.example
├── clickhouse/init/       # схема, витрины, Materialized View
│   ├── 01_schema.sql
│   ├── 02_aggregates.sql
│   └── 03_materialized_views.sql
└── generator/             # генератор потока (см. generator/README-описание
                           # в предыдущем этапе) + repository/clickhouse.py
```

## Дальше по плану

1. Superset: подключение к ClickHouse, датасеты, дашборд и фильтры.
2. Jupyter: аналитические запросы и графики.
3. Документация, проверки и runbook.

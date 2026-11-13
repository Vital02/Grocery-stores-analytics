-- =============================================================================
--  Агрегирующие таблицы (real-time витрины)
--
--  Здесь намеренно использованы два разных движка, чтобы показать оба подхода:
--    * sales_per_minute — SummingMergeTree (простые суммы по минутам);
--    * category_hourly  — AggregatingMergeTree + -State/-Merge (уникальные
--      заказы, суммы в широкой точности).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Продажи по минутам в разрезе «город × категория».
-- Неключевые числовые колонки при merge складываются — это ровно то, что нужно.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grocery.sales_per_minute
(
    minute        DateTime,
    city          LowCardinality(String),
    category      LowCardinality(String),
    items         Decimal(18, 3),
    revenue       Decimal(18, 2),
    margin        Decimal(18, 2),
    promo_revenue Decimal(18, 2),
    events_count  UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMM(minute)
ORDER BY (minute, city, category);

-- -----------------------------------------------------------------------------
-- Часовые агрегаты по категориям.
-- Хранятся состояния агрегатных функций, читаются через *Merge().
-- Уникальные заказы считаем через uniqState(UUID) — суммировать их нельзя.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grocery.category_hourly
(
    hour          DateTime,
    category      LowCardinality(String),
    revenue_state AggregateFunction(sum, Decimal(38, 2)),
    margin_state  AggregateFunction(sum, Decimal(38, 2)),
    items_state   AggregateFunction(sum, Decimal(38, 3)),
    orders_state  AggregateFunction(uniq, UUID),
    events_state  AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
PARTITION BY toYYYYMM(hour)
ORDER BY (hour, category);

-- =============================================================================
--  Схема БД grocery (предметная область: сеть продуктовых магазинов)
--  Скрипт выполняется автоматически при первом старте контейнера ClickHouse
--  (каталог /docker-entrypoint-initdb.d).
--
--  Состав:
--    stores   — справочник магазинов            (измерения: город, формат)
--    products — справочник товаров              (измерения: категория, поставщик, цена)
--    sales    — поток позиций чеков             (факт, партиционирование по дате)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS grocery;

-- -----------------------------------------------------------------------------
-- Справочник магазинов.
-- ReplacingMergeTree: при повторной вставке строки с тем же store_id побеждает
-- версия с максимальным updated_at (цены/формат могут меняться).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grocery.stores
(
    store_id     UInt16,
    store_name   String,
    city         LowCardinality(String),
    district     String,
    store_format LowCardinality(String), -- супермаркет / минимаркет / даркстор
    opened_at    Date,
    updated_at   DateTime
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY tuple()
ORDER BY store_id;

-- -----------------------------------------------------------------------------
-- Справочник товаров.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grocery.products
(
    product_id   UInt32,
    sku          String,
    product_name String,
    category     LowCardinality(String),
    subcategory  LowCardinality(String),
    supplier     LowCardinality(String),
    unit         LowCardinality(String), -- шт / кг / л / упак
    price        Decimal(10, 2),
    cost         Decimal(10, 2),
    is_organic   UInt8,
    is_available UInt8,
    updated_at   DateTime
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY tuple()
ORDER BY product_id;

-- -----------------------------------------------------------------------------
-- Поток продаж: одна строка = одна позиция чека.
--
-- * партиционирование по дню — типовой паттерн для event-таблиц,
--   позволяет быстро удалять/архивировать старые партиции;
-- * ORDER BY (city, category, event_time) — под самые частые срезы
--   «город + категория + время» (дашборд и ноутбук);
-- * TTL — демо-данные старше 180 дней автоматически удаляются.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grocery.sales
(
    event_time     DateTime,
    order_id       UUID,
    line_no        UInt8,
    store_id       UInt16,
    city           LowCardinality(String),
    store_format   LowCardinality(String),
    customer_id    UInt32,
    product_id     UInt32,
    product_name   String,
    category       LowCardinality(String),
    quantity       Decimal(10, 3),
    unit_price     Decimal(10, 2),
    discount_pct   Float32,
    revenue        Decimal(12, 2),
    cost_amount    Decimal(12, 2),
    margin         Decimal(12, 2),
    payment_method LowCardinality(String), -- card / sbp / cash / online
    channel        LowCardinality(String), -- mobile_app / web / pickup
    is_promo       UInt8,
    is_anomaly     UInt8,                  -- «заложенный» выброс (ground truth для анализа)
    ingest_time    DateTime DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (city, category, event_time)
TTL event_time + INTERVAL 180 DAY
SETTINGS index_granularity = 8192;

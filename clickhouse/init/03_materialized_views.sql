-- =============================================================================
--  Материализованные представления — считают агрегаты в момент вставки,
--  поэтому витрины обновляются в реальном времени (без планировщика).
--
--  Важно: MV срабатывает на каждый INSERT в grocery.sales, т.е. генератор
--  пишет только в sales, а витрины наполняются сами.
--
--
--  ДВА ПРАВИЛА, без которых MV молча пишет нули:
--
--  1) Имена выходных колонок SELECT обязаны совпадать с именами колонок
--     целевой таблицы. Для MV "TO <table>" ClickHouse сопоставляет результат
--     с таблицей ПО ИМЕНИ, а не по позиции. Если назвать колонку иначе
--     (например, revenue_sum при колонке revenue), она не попадёт в таблицу
--     и останется нулём по умолчанию — без единой ошибки в логах.
--
--  2) Псевдоним не должен затенять колонку, которую читают другие агрегаты
--     в том же SELECT. После "sum(revenue) AS revenue" выражение
--     sumIf(revenue, ...) разворачивается в агрегат внутри агрегата и падает
--     с ILLEGAL_AGGREGATION. Поэтому колонки таблицы дополнительно
--     квалифицируются алиасом источника (s.revenue) — это снимает затенение
--     и позволяет сохранить правильные имена.
-- =============================================================================

-- 1) Минутная витрина по городам и категориям (SummingMergeTree).
CREATE MATERIALIZED VIEW IF NOT EXISTS grocery.mv_sales_per_minute
TO grocery.sales_per_minute
AS
SELECT
    toStartOfMinute(s.event_time)      AS minute,
    s.city                             AS city,
    s.category                         AS category,
    sum(s.quantity)                    AS items,
    sum(s.revenue)                     AS revenue,
    sum(s.margin)                      AS margin,
    sumIf(s.revenue, s.is_promo = 1)   AS promo_revenue,
    count()                            AS events_count
FROM grocery.sales AS s
GROUP BY minute, city, category;

-- 2) Часовая витрина по категориям (AggregatingMergeTree, -State функции).
--    toDecimal128(...) защищает суммы от переполнения Decimal(12,2).
--    Здесь имена *_state уже совпадают с целевой таблицей category_hourly.
CREATE MATERIALIZED VIEW IF NOT EXISTS grocery.mv_category_hourly
TO grocery.category_hourly
AS
SELECT
    toStartOfHour(s.event_time)                  AS hour,
    s.category                                   AS category,
    sumState(toDecimal128(s.revenue, 2))         AS revenue_state,
    sumState(toDecimal128(s.margin, 2))          AS margin_state,
    sumState(toDecimal128(s.quantity, 3))        AS items_state,
    uniqState(s.order_id)                        AS orders_state,
    countState()                                 AS events_state
FROM grocery.sales AS s
GROUP BY hour, category;

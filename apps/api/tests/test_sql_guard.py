import pytest

from xiaoma.agent.sql import validate_sql

CONTEXT = {
    "tables": {
        "orders": ["order_id", "paid_at", "paid_amount"],
        "refunds": ["order_id", "refund_id", "completed_at"],
    }
}


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT order_id FROM orders",
        "SELECT count(*) AS n FROM orders WHERE paid_at IS NOT NULL",
        "WITH p AS (SELECT order_id FROM orders) SELECT count(*) FROM p",
        "SELECT o.order_id,count(r.refund_id) AS n FROM orders o "
        "LEFT JOIN refunds r ON o.order_id=r.order_id GROUP BY o.order_id",
    ],
)
def test_selected_tables_aliases_aggregations_and_ctes(sql):
    assert validate_sql(sql, CONTEXT, "business_v1")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT 1; SELECT order_id FROM orders",
        "SELECT * FROM orders",
        "SELECT customer_id FROM orders",
        "SELECT c.customer_name FROM customers c",
        "SELECT order_id FROM public.orders",
        "SELECT pg_sleep(10) FROM orders",
        "SELECT set_config('role','postgres',false) FROM orders",
        "WITH x AS (DELETE FROM orders RETURNING order_id) SELECT order_id FROM x",
        "SELECT order_id INTO hacked FROM orders",
        "SELECT order_id FROM orders FOR UPDATE",
        "SELECT * FROM generate_series(1,100000000)",
    ],
)
def test_write_system_unlinked_and_external_queries_rejected(sql):
    with pytest.raises(ValueError):
        validate_sql(sql, CONTEXT, "business_v1")

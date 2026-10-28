"""Refresh the static Text2SQL walkthrough with a real SELECT-only execution.

Requires the local API .env and imported synthetic business dataset. No model is
called; all schema discovery, linking and execution use production SqlSession.
"""

import asyncio
import json
from pathlib import Path

import sqlglot

from xiaoma.agent.sql import SqlSession
from xiaoma.business import LABELS, BusinessDatabase
from xiaoma.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
QUESTION = "按品类统计成功退款金额，并画柱状图，不限制日期。"
TABLES = {
    "refunds": ["refund_id", "refund_status"],
    "refund_items": ["refund_id", "order_item_id", "amount"],
    "order_items": ["order_item_id", "category_id"],
    "categories": ["category_id", "category_name"],
}
JOINS = [
    "refunds.refund_id = refund_items.refund_id",
    "refund_items.order_item_id = order_items.order_item_id",
    "order_items.category_id = categories.category_id",
]
SQL = """SELECT c.category_name AS category,
       SUM(ri.amount) AS refund_amount
FROM refunds AS r
JOIN refund_items AS ri ON ri.refund_id = r.refund_id
JOIN order_items AS oi ON oi.order_item_id = ri.order_item_id
JOIN categories AS c ON c.category_id = oi.category_id
WHERE r.refund_status = 'completed'
GROUP BY c.category_id, c.category_name
ORDER BY refund_amount DESC, c.category_id"""


async def main():
    business = BusinessDatabase(Settings())
    try:
        session = SqlSession(business)
        catalog = await session.list_tables()
        inspected = await session.inspect(["refunds", "refund_items", "order_items"])
        inspected += await session.inspect(["categories"])
        grain = "以退款商品分配明细计金额，关联成交时品类快照，再按品类汇总"
        context = await session.link(TABLES, QUESTION, JOINS, grain)
        result = await session.execute(context["context_id"], SQL)
        value = {
            "question": QUESTION,
            "catalog": catalog,
            "inspected": [
                dict(table, title=LABELS[table["table"]]["title"]) for table in inspected
            ],
            "linked": {"tables": TABLES, "joins": JOINS, "grain": grain},
            "sql": sqlglot.parse_one(result["sql"], read="postgres").sql(
                pretty=True, dialect="postgres"
            ),
            "result": {key: result[key] for key in ("rows", "row_count", "truncated", "executed")},
            "provenance": "合成数据包 · 独立只读 PostgreSQL 实测快照",
        }
        path = ROOT / "apps/web/src/features/project/fixtures/sql-walkthrough.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        print(f"Updated {path.relative_to(ROOT)}")
        print(
            f"Catalog: {len(catalog)} tables; inspected: {len(inspected)}; "
            f"linked: {sum(map(len, TABLES.values()))} fields; result: {result['row_count']} rows."
        )
    finally:
        if business.engine:
            await business.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

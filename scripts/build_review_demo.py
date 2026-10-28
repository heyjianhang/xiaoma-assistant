"""Build evidence-review examples from canonical documents and read-only SQL.

No model calls or chat-history writes. Requires imported synthetic business data.
"""

import asyncio
import json
import re
from pathlib import Path

import sqlglot

from xiaoma.agent.sql import SqlSession
from xiaoma.business import BusinessDatabase
from xiaoma.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data/examples/markdown"
RATE_TABLES = {
    "orders": ["order_id", "region_id", "paid_at"],
    "order_items": ["order_item_id", "order_id", "category_id"],
    "refunds": ["refund_id", "refund_status", "completed_at"],
    "refund_items": ["refund_id", "order_item_id"],
    "categories": ["category_id", "category_name"],
    "regions": ["region_id", "region_name"],
}
RATE_JOINS = [
    "orders.order_id = order_items.order_id",
    "orders.region_id = regions.region_id",
    "order_items.category_id = categories.category_id",
    "refund_items.order_item_id = order_items.order_item_id",
    "refund_items.refund_id = refunds.refund_id",
]
RECORD_TABLES = {
    "refunds": [
        "order_id",
        "refund_no",
        "refund_status",
        "payment_channel",
        "applied_at",
        "accepted_at",
        "completed_at",
    ]
}


def section(filename, start, end=None):
    text = (DOCS / filename).read_text()
    left = text.index(start)
    right = text.index(end, left) if end else len(text)
    return text[left:right].replace("<!-- page break -->", "").strip()


def source(filename, title, clause, excerpt):
    return {"file": filename, "title": title, "clause": clause, "excerpt": excerpt}


def rate_sql(region, category):
    # Inputs are fixed synthetic-case constants, never user-provided SQL fragments.
    return f"""WITH cohort AS (
  SELECT DISTINCT o.order_id
  FROM orders AS o
  JOIN order_items AS oi ON oi.order_id = o.order_id
  JOIN categories AS c ON c.category_id = oi.category_id
  JOIN regions AS g ON g.region_id = o.region_id
  WHERE o.paid_at >= '2026-09-01T00:00:00+08:00'
    AND o.paid_at < '2026-10-01T00:00:00+08:00'
    AND g.region_name = '{region}' AND c.category_name = '{category}'
), successful AS (
  SELECT DISTINCT oi.order_id, r.refund_id
  FROM refunds AS r
  JOIN refund_items AS ri ON ri.refund_id = r.refund_id
  JOIN order_items AS oi ON oi.order_item_id = ri.order_item_id
  JOIN categories AS c ON c.category_id = oi.category_id
  JOIN cohort AS p ON p.order_id = oi.order_id
  WHERE r.refund_status = 'completed'
    AND r.completed_at < '2026-10-01T00:00:00+08:00'
    AND c.category_name = '{category}'
)
SELECT COUNT(DISTINCT p.order_id) AS paid_orders,
       COUNT(DISTINCT s.order_id) AS refunded_orders,
       COUNT(DISTINCT s.refund_id) AS refund_sheets,
       ROUND(100.0 * COUNT(DISTINCT s.order_id)
         / NULLIF(COUNT(DISTINCT p.order_id), 0), 2) AS refund_rate_percent
FROM cohort AS p LEFT JOIN successful AS s ON s.order_id = p.order_id"""


def record_sql(order_id):
    return f"""SELECT r.order_id, r.refund_no, r.refund_status, r.payment_channel,
       TO_CHAR(r.applied_at, 'YYYY-MM-DD HH24:MI') AS applied_at,
       TO_CHAR(r.accepted_at, 'YYYY-MM-DD HH24:MI') AS accepted_at,
       TO_CHAR(r.completed_at, 'YYYY-MM-DD HH24:MI') AS completed_at,
       ROUND(EXTRACT(EPOCH FROM (r.completed_at - r.accepted_at)) / 3600.0, 2)
         AS elapsed_hours
FROM refunds AS r WHERE r.order_id = {order_id} ORDER BY r.refund_no"""


async def snapshot(business, key, question_id, tables, joins, grain, scope, sql):
    session = SqlSession(business)
    await session.list_tables()
    names = list(tables)
    for index in range(0, len(names), 3):
        await session.inspect(names[index : index + 3])
    context = await session.link(tables, scope, joins, grain)
    result = await session.execute(context["context_id"], sql)
    return {
        "id": "snapshot-" + key,
        "questionId": question_id,
        "sql": sqlglot.parse_one(result["sql"], read="postgres").sql(
            pretty=True, dialect="postgres"
        ),
        "rows": result["rows"],
        "schema": result["schema"],
        "scope": scope,
        "provenance": "合成数据包 · 独立只读 PostgreSQL 实测快照",
        "executed": True,
        "truncated": result["truncated"],
    }


async def main():
    cases = json.loads((ROOT / "tests/acceptance/cases.json").read_text())["cases"]
    questions = {case["id"]: case["question"] for case in cases}
    business = BusinessDatabase(Settings())
    try:
        queries = {}
        for key, case_id, region, category in [
            ("conflict", "A06", "华东", "生鲜果蔬"),
            ("small", "A07", "西北", "滋补礼盒"),
            ("zero", "A13", "东北", "茗茶饮品"),
        ]:
            scope = f"2026年9月支付队列；{region} / {category}；成功退款截止10月1日前；北京时间"
            queries[key] = await snapshot(
                business,
                key,
                case_id,
                RATE_TABLES,
                RATE_JOINS,
                "按支付订单去重，退款沿原购买行匹配品类；同一订单多次退款仅计一笔退款订单",
                scope,
                rate_sql(region, category),
            )
        for key, case_id, order in [("version", "A12", 104), ("missing", "A04", 110)]:
            queries[key] = await snapshot(
                business,
                key,
                case_id,
                RECORD_TABLES,
                [],
                "逐张退款单核对业务时间",
                f"订单{order}的退款记录；全部时间为北京时间，不用申请时间替代验收时间",
                record_sql(order),
            )
        assert queries["conflict"]["rows"][0] == {
            "paid_orders": 100,
            "refunded_orders": 8,
            "refund_sheets": 10,
            "refund_rate_percent": 8.0,
        }
        assert queries["small"]["rows"][0]["paid_orders"] == 3
        assert queries["small"]["rows"][0]["refunded_orders"] == 3
        assert queries["zero"]["rows"][0]["refund_rate_percent"] is None
        assert queries["zero"]["rows"][0]["paid_orders"] == 0
        assert queries["version"]["rows"][0]["elapsed_hours"] == 48
        assert queries["missing"]["rows"][0]["accepted_at"] is None
        assert queries["missing"]["rows"][0]["elapsed_hours"] is None
        monthly = section("monthly-report.md", "## 1 月度", "## 3 管理")
        reported_rate = float(re.search(r"REP-2.1[^\n]*?为(\d+(?:\.\d+)?)%", monthly)[1])
        metric_intro = section("metric-definitions.md", "## 1 统计", "## 3 金额")
        sources = {
            "monthly": source(
                "monthly-report.md",
                "2026年9月运营月报",
                "REP-1.1 / REP-T1 / REP-2.1",
                monthly,
            ),
            "metrics": source(
                "metric-definitions.md",
                "运营指标口径说明",
                "MET-1.1 / MET-F1 / MET-2.1",
                metric_intro,
            ),
            "display": source(
                "metric-definitions.md",
                "运营指标口径说明",
                "MET-T1",
                section("metric-definitions.md", "表MET-T1", "## 4 "),
            ),
            "boundaries": source(
                "metric-definitions.md",
                "运营指标口径说明",
                "MET-F5 / MET-4.1 / MET-4.2",
                section("metric-definitions.md", "## 4 ", "## 5 "),
            ),
        }
        for key, filename, title in [
            ("old_policy", "refund-policy-v1.md", "售后退款制度（旧版）"),
            ("new_policy", "refund-policy-v2.md", "售后退款制度（新版）"),
        ]:
            prefix = "AS1" if key == "old_policy" else "AS2"
            excerpt = section(filename, "## 1 总则", "## 2 品类")
            excerpt += "\n\n" + section(filename, "## 3 材料", "## 4 审批")
            sources[key] = source(
                filename, title, f"{prefix}-1.2 / {prefix}-T2 / {prefix}-3.3", excerpt
            )
        data = {
            "questions": {key: questions[key] for key in ("A06", "A12", "A04", "A07", "A05")},
            "reported_rate": reported_rate,
            "queries": queries,
            "sources": sources,
        }
        path = ROOT / "apps/web/src/features/project/fixtures/review-walkthrough.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"Updated {path.relative_to(ROOT)}; 5 real read-only query snapshots verified.")
    finally:
        if business.engine:
            await business.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

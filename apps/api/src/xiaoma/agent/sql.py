"""Explicit schema contexts and a parsed, bounded SELECT-only executor."""

import json
import time
from uuid import uuid4

import sqlglot
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

from .resilience import is_transient

ALLOWED_ANONYMOUS = {
    "date_trunc",
    "to_char",
    "to_date",
    "make_date",
    "make_interval",
    "round",
    "abs",
    "ceil",
    "ceiling",
    "floor",
}
FORBIDDEN = {
    "Insert",
    "Update",
    "Delete",
    "Create",
    "Drop",
    "Alter",
    "Copy",
    "Command",
    "Transaction",
    "Commit",
    "Rollback",
    "Grant",
    "Revoke",
    "Into",
    "Lock",
    "Set",
    "Execute",
    "Use",
}


def validate_sql(sql, context, schema):
    if not 1 <= len(sql) <= 16000:
        raise ValueError("SQL长度不合法")
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as exc:
        raise ValueError("SQL语法不合法，请修正后重试") from exc
    if len(statements) != 1 or not isinstance(
        statements[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
    ):
        raise ValueError("仅允许单条SELECT查询")
    tree = statements[0]
    if any(type(node).__name__ in FORBIDDEN for node in tree.walk()):
        raise ValueError("SQL包含禁止的写入或控制语句")
    ctes = {cte.alias for cte in tree.find_all(exp.CTE)}
    physical = []
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ValueError("不允许表函数或外部数据源")
        if not table.db and table.name in ctes:
            continue
        if (
            table.catalog
            or (table.db and table.db != schema)
            or table.name not in context["tables"]
        ):
            raise ValueError(f"表 {table.name} 未被本轮Schema Linking授权")
        table.set("db", exp.to_identifier(schema))
        physical.append(table.name)
    if not physical:
        raise ValueError("SQL必须查询已链接的业务表")
    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            raise ValueError("请显式选择字段，不能SELECT *")
    for function in tree.find_all(exp.Anonymous):
        if function.name.lower() not in ALLOWED_ANONYMOUS:
            raise ValueError(f"不允许函数 {function.name}")
    # Qualifier resolves aliases, CTEs and subqueries against ONLY linked columns.
    column_schema = {
        schema: {
            table: {c: "UNKNOWN" for c in columns} for table, columns in context["tables"].items()
        }
    }
    try:
        tree = qualify(
            tree,
            dialect="postgres",
            schema=column_schema,
            expand_stars=False,
            allow_partial_qualification=False,
            validate_qualify_columns=True,
        )
    except Exception as exc:
        raise ValueError("SQL字段未链接或存在歧义，请重新检查选表选字段") from exc
    return tree.sql(dialect="postgres")


class SqlSession:
    def __init__(self, business):
        self.business = business
        self.inspected = {}
        self.contexts = {}
        self.results = {}
        self.catalog_cache = None

    async def catalog(self):
        if self.catalog_cache is None:
            self.catalog_cache = (await self.business.catalog())["items"]
        return self.catalog_cache

    async def list_tables(self):
        return [{"name": t["name"], "description": t["description"]} for t in await self.catalog()]

    async def inspect(self, names):
        if not 1 <= len(names) <= 3:
            raise ValueError("每次按需读取1至3张候选表")
        catalog = {t["name"]: t for t in await self.catalog()}
        result = []
        for name in names:
            if name not in catalog:
                raise ValueError(f"未知业务表 {name}")
            table = catalog[name]
            self.inspected[name] = table
            result.append(
                {
                    "table": name,
                    "description": table["description"],
                    "primary_key": table["primaryKey"],
                    "columns": table["columns"],
                }
            )
        return result

    async def link(self, tables, question, joins, grain):
        if not tables or len(tables) > 8:
            raise ValueError("请选出本问题实际需要的表和字段")
        selected = {}
        for name, columns in tables.items():
            if name not in self.inspected:
                raise ValueError(f"请先调用get_table_schema读取 {name}")
            available = {c["name"]: c for c in self.inspected[name]["columns"]}
            if not columns or not set(columns).issubset(available):
                raise ValueError(f"{name}包含不存在的字段")
            selected[name] = [available[c] for c in dict.fromkeys(columns)]
        id = str(uuid4())
        context = {
            "context_id": id,
            "question": question,
            "tables": {t: [c["name"] for c in cols] for t, cols in selected.items()},
            "columns": selected,
            "joins": joins,
            "grain": grain,
        }
        self.contexts[id] = context
        return context

    async def execute(self, context_id, sql):
        if context_id not in self.contexts:
            raise ValueError("缺少本轮有效的context_id，请先显式调用link_schema")
        context = self.contexts[context_id]
        validated = validate_sql(sql, context, self.business.schema)
        start = time.perf_counter()
        try:
            async with self.business.connection() as conn:
                # The outer limit is independent of any LIMIT requested by the model.
                result = await conn.execute(
                    text(f"SELECT * FROM ({validated}) AS xiaoma_result LIMIT 201")
                )
                columns = list(result.keys())
                rows = [dict(row) for row in result.mappings().all()]
        except SQLAlchemyError as exc:
            if is_transient(exc):
                raise  # Retry only transient failures; never repeat malformed SQL.
            original = getattr(exc, "orig", None)
            code = getattr(original, "sqlstate", "")
            if code == "57014":
                message = "查询超过5秒，请缩小时间范围或简化关联"
            else:
                message = "只读SQL执行失败，请核对字段、聚合、类型及运算，修正后重试"
            raise ValueError(message) from exc
        from fastapi.encoders import jsonable_encoder

        truncated = len(rows) > 200
        rows = jsonable_encoder(rows[:200])
        # Also bound payload size when a single text field is unusually large.
        while len(json.dumps(rows, ensure_ascii=False)) > 120000 and rows:
            rows.pop()
            truncated = True
        id = str(uuid4())
        value = {
            "id": id,
            "questionId": "",
            "sql": validated,
            "rows": rows,
            "schema": {
                "tables": context["tables"],
                "joins": context["joins"],
                "grain": context["grain"],
            },
            "scope": context["question"],
            "provenance": "真实只读 PostgreSQL 查询",
            "executed": True,
            "columns": columns,
            "truncated": truncated,
            "row_count": len(rows),
            "elapsed_ms": round((time.perf_counter() - start) * 1000),
        }
        self.results[id] = value
        return value

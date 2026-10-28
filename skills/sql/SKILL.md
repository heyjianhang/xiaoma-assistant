---
{
  "name": "sql",
  "description": "统计订单、退款、金额、时效或维度分布；实际执行只读 SQL。",
  "metadata": {
    "xiaoma-display-name": "业务查询与显式 Schema Linking",
    "xiaoma-required-tools": "list_tables get_table_schema link_schema execute_readonly_sql"
  }
}
---

必须按顺序执行：list_tables 读取精简目录 →
 get_table_schema 按需读取候选表 →
 link_schema 显式记录问题、选中的表字段、关联与统计粒度 →
 直接生成 SQL 并调用 execute_readonly_sql。
不能以猜测字段、全量DDL或另一个SQL生成Agent代替。
在执行工具参数中提交返回的 context_id，不放入面向用户的答复；
SQL只能使用选中的表字段，不能 SELECT *（COUNT(*)允许）。
相对日期先查 demo_context 参考日期，而不是服务器今天。
用 paid_at 确定支付订单cohort；
退款成功 completed，未支付不入分母。
品类口径用 order_items.category_id；
退款品类需 refund_items 回到原购买行。
避免多对多JOIN重复累计，订单率按distinct order_id去重。
accepted_at为空不使用其他时间补算。
执行成功后才能报告数值，回答应说明时间范围、分母和限制，空结果也应说明。
SQL失败可更正后重试，不能声称成功。
复杂核对可按需读取 [查询清单](references/query-checklist.md)。

# 食品电商合成业务数据

为企业运营知识助手作业准备的虚构数据，不含真实客户信息。Schema 为 `business_v1`，中文业务注释、主外键和校验规则随导入保留。

```bash
uv run --project apps/api python scripts/import_business.py
```

导入器按依赖顺序导入，在事务提交前校验约束和行数，配置独立只读账号。同一数据包重复执行不会追加，内容不同的既存 Schema 拒绝覆盖。

| 表 | 行数 |
| --- | ---: |
| `regions` | 6 |
| `customers` | 600 |
| `categories` | 5 |
| `suppliers` | 5 |
| `products` | 30 |
| `orders` | 5,000 |
| `order_items` | 15,027 |
| `refunds` | 474 |
| `refund_items` | 477 |
| `demo_context` | 1 |

`demo_context` 保存演示参考日期和统计窗口；相对时间问题应读取此表。验收集优先使用明确的2026年9月，避免随系统日期变化。

数据包含多品类订单、部分退款、一单多退款、缺失验收时间与小样本等边界。配套制度与月报见 [文档目录](../examples/README.md)，预期见 [验收用例](../../tests/acceptance/cases.json)。

DDL / CSV 仅作为业务数据库导入源，不会整份发送给模型或自动进入 RAG。Agent 通过目录和候选表逐步查看结构，必须显式链接后才能实际执行查询。预期答案不进入知识库。

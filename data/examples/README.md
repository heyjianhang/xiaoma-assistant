# 合成中文演示文档

本目录为食品电商“禾序食集”的虚构制度与报表，用于展示表格/公式/附注完整性、版本判断和跨来源核对。与 [业务数据](../business/README.md) 配套，不含真实企业或客户资料。

| 文件 | 内容与用途 |
| --- | --- |
| `refund-policy-v1.pdf` | 旧版退款制度；电子钱包验收后48自然小时 |
| `refund-policy-v2.pdf` | 新版退款制度；电子钱包24自然小时、银行卡48自然小时，含表格、计时公式和附注 |
| `metric-definitions.pdf` | 订单、退款、金额、时效与统计粒度定义 |
| `monthly-report.pdf` | 2026年9月月报，刻意保留华东生鲜2%的报表值供冲突核对 |
| `monthly-reconciliation.pdf` | 报表与明细的核对流程 |
| `supplier-admission.pdf` | 供应商准入及跨页清单 |
| `fulfillment-standard.pdf` | 订单履约、发货与时效要求 |
| `cold-chain-evidence.pdf` | 生鲜冷链证据与责任界定 |
| `refund-record-archive.pdf` | 历史退款凭证及缺失记录处理 |
| `product-master-data.pdf` | 商品主数据、历史快照和口径 |

`markdown/` 保存对应 UTF-8 Markdown 源文件，另有仅 Markdown 的 `customer-service-handoff.md`。PDF 用于真实解析与区域高亮；Markdown 适合快速验证入库和段落/行号定位，不具备 PDF 坐标。

管理员通过知识库多选上传即可。最小版本/冲突语料为两版退款制度、指标定义和月报。选择 PDF 或对应 Markdown 其中一种，避免同一文档重复入库。新增资料不会因文件进入仓库而自动变成可检索状态，需要上传并等待处理完成。

预期答案在 [验收集](../../tests/acceptance/cases.json)，不要上传到知识库。CSV、DDL、生成器和验收答案也不属于 RAG 语料。

数据包原始 PDF 与 Markdown 保留内容，包括表格中的故意冲突。这里的2%是测试事实冲突的输入，不能当作数据库真值。

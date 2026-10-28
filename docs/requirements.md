# 作业需求对照

依据《全栈 AI 开发作业：企业运营知识助手》整理。表中“实现”表示代码具备该路径，不等于所有真实模型场景都已通过；验证范围见 [验证记录](validation.md)。

## 必做项

| 要求 | 实现位置 / 评审入口 | 验证方式 |
| --- | --- | --- |
| PDF / Markdown 解析、分块、向量入库 | [入库设计](ingestion.md)，`ingestion/` | 结构单元测试、真实 PGVectorStore 集成测试；10份PDF已真实MinerU解析、分块与入库验证 |
| 引用定位到文档标题与段落/条款 | [引用工具](../apps/api/src/xiaoma/agent/tools.py)，[前端引用](../apps/web/src/features/chat/chat-citation.tsx) | 来源元数据与 Markdown AST 测试；浏览器原文定位/高亮；引用是否支持结论还需语义验收 |
| 多张相关业务表 | [10 表数据](../data/business/README.md) | 实际导入并校验行数、约束，真实 PostgreSQL 测试 |
| 显式 Schema Linking | [SQL 工具](../apps/api/src/xiaoma/agent/sql.py)，[SQL Skill](../skills/sql/SKILL.md) | 目录 → 查看候选结构 → `link_schema` → 执行；未查看或未链接字段被拒绝 |
| 不把全量 DDL 放入提示词 | [最终组装](../apps/api/src/xiaoma/agent/builder.py) | 初始仅有工具及 Skill 简介；目录与结构按需加载 |
| SQL 实际执行、只读连接、自然语言摘要 | [业务连接](../apps/api/src/xiaoma/business.py)，[执行工具](../apps/api/src/xiaoma/agent/tools.py) | 独立 SELECT-only 账号、只读事务与 AST；真实模型查询 5,000 条订单已验证 |
| Web Chat 自动选择 RAG / SQL / BOTH | [Agent](../apps/api/src/xiaoma/agent/builder.py)，[聊天页](../apps/web/src/features/chat/chat-workspace.tsx) | 单 Agent 工具调用；真实 RAG、SQL、HYBRID 路径已观察，完整路由准确率未测 |
| 歧义 / 跨域问题与路由失败解释 | [DECISIONS 第1问](../DECISIONS.md)，[验收用例](../tests/acceptance/cases.json) | 缺定义先澄清，跨来源先对齐口径；保留因果判断限制 |

工具开关用于禁止某类工具，不要求用户手选 RAG / SQL / HYBRID 路径。正常验收时两类工具均开启。

## 加分项

| 要求 | 实现与边界 |
| --- | --- |
| 可配置 Skill / 结构化工具映射 UI | 标准 ZIP、版本、按需读取；Pydantic JSON Schema 对应图表、核对与澄清组件。没有任意代码执行或自动生成 React 的能力 |
| 流式过程 | SSE 文本、真实工具状态、原生 TodoList；前端代理关闭变换与缓冲，无模拟打字 |
| 冲突处理 | 核对卡展示两份来源、口径与差异；真实月报冲突用例已准备，完整语料真实回归待做 |
| 缺失处理 | 指标未定义请求澄清；缺验收时间不替填，订单110 HYBRID 已真实联调 |
| 数据异常处理 | 展示分子分母、样本量、限制；3/3 的 100% 用例纳入人工验收 |

## 交付项

- [README](../README.md)：依赖、初始化、启动、架构图、演示问题和范围。
- [DECISIONS](../DECISIONS.md)：路由失效、RAG 衡量、冲突展示三个问题。
- [测试说明](testing.md) 和 [验收用例](../tests/acceptance/cases.json)：纯 RAG、纯 SQL、HYBRID、歧义、冲突及补充边界。
- [部署说明](deployment.md)：当前为本地运行，列明服务器发布条件，不宣称已经上线。

过程规划、密钥、会话快照和调试结果不在交付仓库中；合成数据、可复现测试与必要说明保留。

# 提示词、Skill 与工具协作

Agent 使用 LangChain `create_agent`。系统提示词负责通用行为，Skill 提供按需加载的业务处理方法，工具负责取得证据、执行查询与输出结构化结果。业务数值、制度期限和验收答案不写入提示词。

## 分层与入口

| 层 | 责任 | 源码 |
| --- | --- | --- |
| 系统提示词 | 当前任务、自动路由、能力开关、证据纪律、回答边界 | `apps/api/src/xiaoma/agent/skills.py` |
| 最终组装 | 技能目录、用户选中正文、Todo、总结和容错中间件 | `apps/api/src/xiaoma/agent/builder.py` |
| 业务 Skill | 文档检索、SQL、跨来源核对、结果可视化的处理方法 | `skills/*/SKILL.md` |
| 工具契约 | 参数 Schema、依赖、返回值、来源归属与结构化组件 | `apps/api/src/xiaoma/agent/tools.py` |
| SQL 约束 | 已查看结构、显式选列、只读 SQL 校验和真实执行 | `apps/api/src/xiaoma/agent/sql.py` |
| 调试证据 | 正式 API、运行快照、实际提示词和 Skill 修订 | [调试 CLI](debug-cli.md) |

最初只提供技能名称与简介；Agent 根据任务调用 `load_skill`。用户用 `/` 选中的正文直接注入，不重复加载。`references/` 和 `assets/` 通过 `read_skill_resource` 读取本次固定修订；不自动执行技能中的脚本。

## 自动选择与组合

| 问题 | Skill 与工具 |
| --- | --- |
| 政策、审批步骤、表格或公式 | `knowledge` → `search_knowledge` → 条款引用 |
| 全部订单数、状态分布 | `sql` → 表目录 → 候选结构 → `link_schema` → 真实只读执行 |
| 指标按定义计算、制度执行或月报核对 | `knowledge` + `sql`；双方证据取得后由 `evidence-review` 判断可比性 |
| 图表、指标卡、明细表 | `sql` + `visualize` → 实际结果 `id` → `render_chart` |
| 口径歧义 | 先检索定义；未解决时 `ask_clarification`，等待下一条消息 |

“核对合计”不自动触发知识库；规则查询与业务记录查询按实际需要组合。用户关闭某类工具时，服务端不注册该能力，也过滤依赖它的 Skill。已取得证据足以回答时收敛，不把每个问题扩展为全面审计。

## 检索与引用

首次全库检索发现文档；需要补查版本、表格或例外时，可使用已返回的 `document_id` 定向检索。相同分块在同一轮中复用证据 ID 与引用编号，避免重复检索改变角标含义。

返回的 `revision` 是入库修订号。业务政策版本、生效条件、期限与例外必须读取正文。结论引用工具提供的 `citation_markdown` 短角标（如 `[1]`），由前端依据本轮证据目录生成原文入口，模型不拼接长ID链接。同时指出实际条款或表号；没有召回证据不等于资料不存在。

## 核对卡的语义

| 类型 | 判断 | 前端状态 |
| --- | --- | --- |
| `conflict` | 同口径的文档事实与查询事实不一致 | 存在差异 |
| `execution_deviation` | 完整业务记录违反适用制度要求 | 存在执行偏差 |
| `consistent` | 规则与完整记录可对齐，核验符合要求 | 核验一致 |
| `missing_data` | 缺少判断必需字段 | 无法判定 |
| `missing_definition` | 已核对资料，指标仍未定义 | 待明确口径 |
| `small_sample` | 比例可计算，但样本不足以外推 | 样本不足 |

`comparable` 只表示来源与口径可对齐，不表示统计显著或因果成立。缺数据、缺定义必须为 false；其他情况尚未对齐时显示“不可直接比较”。核验一致必须为 true。除未定义口径可不执行 SQL 外，核对卡需要本轮真实查询结果和原文证据；未知或历史结果 ID 被拒绝。

工具验证来源归属和结构，不自动证明语义结论。规范上限与实际耗时不同，首先属于执行核验；缺时间不能换用其他字段补算。对高比例只作观察描述，不根据差异猜测录入错误或质量原因。

## 结果与任务状态

查询结果自动先显示表格。`render_chart` 将同一结果视图升级为柱状图、折线图、表格或指标卡；指标卡要求单行数值聚合，保留 0 与 NULL 的区别。SQL 中文别名用于展示名称与单位，数值保持数值类型。分类图不混入合计柱，截断结果不冒充全量统计。

多阶段任务使用原生 `write_todos` 管理业务阶段。简单计数和单次事实问答不强制建清单；缺证或等待澄清不标记事实核验完成。最终仍给自然语言结论，避免把卡片数据整段复写。

## 更新与验证

修改磁盘文件不会覆盖数据库中的现有 Skill。通过管理员标准 ZIP 上传接口发布新修订，保留原包、启停状态与运行快照；后续运行使用新版本，已启动运行固定原版本。

验证分两部分：工具/权限/来源等可确定的约束使用自动测试；真实模型回答对照 [典型用例](../tests/acceptance/cases.json) 检查路由、口径、数值、原文支持和组件。单次模型运行完成不等于语义验收通过，性能对比也需说明样本量。

参考：[LangChain Skills](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)、[Tool 定义与 Schema](https://docs.langchain.com/oss/python/langchain/tools)、[Agent Skills 规范](https://agentskills.io/specification)。

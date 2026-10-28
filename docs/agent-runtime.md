# Agent 预算与标准 Skill 实现

本文说明基于 Model Profile 的比例预算和标准 Skill 包实现。

## 最终组装入口

`apps/api/src/xiaoma/agent/builder.py`

`build_agent(...)` 集中组装模型、按开关注册的工具、系统提示词、用户选中的 Skill 和全部中间件。`service.py` 负责认证、运行快照、SSE、标题与保存结果；模型资料位于 `models.py`，预算和容错位于 `resilience.py`。

内置技能位于 `skills/`，包含 `knowledge`、`sql`、`evidence-review`、`visualize`。每份都是标准 `SKILL.md` 目录，SQL 技能还带查询核对清单。首次启动注册为版本化包；已有后台版本不会被重启覆盖。更新已有技能可下载包、修改并从该技能上传新版本。

## 预算随模型资料变化

优先使用 LangChain `model.profile`，当前百炼网关的缺失资料由 models.dev 的 `alibaba-cn` 精确型号补齐。网关 `/models` 仍用来确认账号实际可调用的模型。公共资料在本地缓存一天，刷新失败可使用上次资料；不向公共资料服务发送模型 Key。

LangChain 原生支持比例阈值。本项目在模型窗口已知时使用：

```python
SummarizationMiddleware(
    model=model,
    trigger=("fraction", 0.75),
    keep=("fraction", 0.25),
    # 自定义摘要提示词、计数与有界重试
)
```

| 参数 | 当前值 |
| --- | --- |
| `CHAT_MAX_STEPS` | 512 图步骤 |
| `CHAT_MODEL_CALL_LIMIT` | 每轮 64 次逻辑模型调用 |
| `CHAT_TOOL_CALL_LIMIT` | 每轮 128 次逻辑工具调用 |
| `CHAT_TIMEOUT_SECONDS` | 每轮 900 秒 |
| `CHAT_MODEL_TIMEOUT_SECONDS` | 模型请求及流片段等待预算 180 秒 |
| `CHAT_MAX_OUTPUT_TOKENS` | 0，自动跟随 Profile 输出上限 |
| `CHAT_SUMMARY_TRIGGER_FRACTION` | 0.75 |
| `CHAT_SUMMARY_KEEP_FRACTION` | 0.25 |
| `CHAT_CONTEXT_WINDOW_TOKENS` | 0，使用模型资料；可指定较小的网关实际窗口 |
| `CHAT_CONTEXT_FALLBACK_TOKENS` | 128000，资料未知时的应用回退预算 |
| `CHAT_SUMMARY_MAX_OUTPUT_TOKENS` | 16384，内部总结任务的独立上限 |
| `CHAT_SUMMARY_TRIGGER_TOKENS` / `CHAT_SUMMARY_KEEP_TOKENS` | 0，默认使用比例；保留绝对值覆盖入口 |
| `CHAT_REPEATED_TOOL_FAILURE_LIMIT` | 同工具同参数连续失败 3 次后停止空转 |

温度继续默认不传。配置写在 `.env`；默认值与范围见同项目的 `apps/api/src/xiaoma/settings.py`，模板为 `.env.example`。修改环境变量后重启 API。

实际读取到的公共资料：

| 模型 | 窗口声明 | 输出声明 | 默认触发 / 保留 |
| --- | ---: | ---: | ---: |
| qwen3.8-flash | 1,000,000 | 131,072 | 750,000 / 250,000 |
| glm-5.3 | 1,000,000 | 131,072 | 750,000 / 250,000 |
| deepseek-v4.1-flash | 1,000,000 | 384,000 | 750,000 / 250,000 |

这些是公共能力声明，不代表已经对网关跑满百万 tokens 的容量测试。Qwen 已实际接受新输出参数并完成业务查询。若某网关有更小配额，可通过窗口覆盖和输出覆盖收紧。

每次真正请求模型前，`OutputBudgetMiddleware` 计算系统提示、消息和工具 Schema 的近似占用，再预留至少 2048 或窗口 2% 的余量，将输出预算收紧为“模型输出上限”和“本次剩余空间”的较小值。输出上限是允许生成的最大值，不会要求模型每次写满。

未知 Profile 时不伪造模型能力；总结使用 128k 应用预算计算出的 96k / 32k，未指定输出覆盖时遵循服务默认。计数仍为近似值；资料缺失或服务窗口不准确时需要配置真实上限。

完整聊天历史仍保留，摘要和近期上下文单独存储并按访客隔离。摘要内部输出不会混进回答。模型/工具瞬时错误仍最多额外重试两次；已产生流片段的模型调用不重放；SQL 参数错误交回模型修正；相同失败参数三次会停止循环。前端代理超时同步放宽至 960 秒。

## 标准 Skill 包

```text
report-template/
├── SKILL.md
├── references/
│   └── format.md
└── assets/
    └── report.md
```

`SKILL.md` 使用 YAML frontmatter，至少包含 `name`、`description`。可保留标准 `license`、`compatibility`、`metadata`、`allowed-tools` 信息。名称遵循小写英文、数字、单连字符及目录匹配规则。小马的中文展示名和工具依赖放在标准扩展区：

```yaml
---
name: refund-review
description: 核对退款规则与实际记录时使用。
metadata:
  xiaoma-display-name: 退款核对
  xiaoma-required-tools: search_knowledge execute_readonly_sql
---
先读取 references/rules.md，再核对真实查询结果。
```

ZIP 可直接包含文件，也可包含一个与 name 相同的顶层目录。每次上传一份 Skill，压缩包最多 5MB、展开最多 10MB、最多 200 个文件，单文件最多 2MB。校验路径、链接、重复文件、YAML 和体积后保存到私有数据库版本包，不解压进应用代码目录。脚本和二进制资源可以保存在包中；Agent 当前只支持按需读取不超过 100KB 的文本资源。

本版实现标准包的说明与资源加载。`scripts/` 不会自动执行，ZIP 也不能自行注册 Shell、MCP 或数据库写工具；需要脚本执行的外部技能仍需额外的受控执行环境。`allowed-tools` 元信息不扩大现有权限。

## 两种调用方式

1. 自动选择：系统上下文先提供技能名称与简介，模型调用 `load_skill` 获取正文与资源目录，再通过 `read_skill_resource` 读取必要文件。
2. 用户选择：输入框输入 `/`，可以按名称筛选，用方向键、回车或点击选择，显示可移除的技能标签。发送时传递 `skills` ID，服务端验证后把所选正文装入本轮提示词；最多选 5 份，仅作用于本次发送。也支持直接输入 `/sql 问题`。

知识库和业务查询开关继续生效。依赖关闭工具的技能在菜单中不可选；服务端也会拒绝，不能靠手写技能 ID 绕过。已选择的技能与普通问题都保留在聊天记录中。

每次运行固定 Skill 修订；后续上传或启停产生新版本。`agent_skill_packages` 保存各修订文件，`agent_skills` 记录当前版本和启用状态。运行中读取的资源使用启动时版本，避免中途变更；共享技能不会混合不同访客的聊天内容。

## 管理与接口

助手主导航的“Agent 配置”（`/agents`）下设“技能”标签页，可上传 ZIP、查看说明和资源、下载包、上传新版本、启停技能；该页面仅管理员可访问。覆盖同名包需从对应行上传新版本并提供当前 revision；版本冲突会返回 409，不静默覆盖。

邀请管理独立位于 `/admin`，使用单独页面，不出现在助手侧边栏。Agent 配置以标签页组织扩展能力，后续远程 MCP 配置可作为独立标签加入；当前尚未开放远程 MCP 地址配置或执行入口。

文件查看使用目录树，文件夹可折叠；弹窗尺寸固定，目录与内容各自滚动。下载和上传新版本收在行尾更多菜单。自上传技能可删除并通过撤销或“最近删除”恢复，恢复时还原此前启用状态。内置技能按原始来源保护，即使上传过新版本也不能删除；服务端同步校验。删除后不再出现在后续运行的技能目录中，历史版本仍供已启动运行读取。

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/agent/skills` | 已启用技能目录，访客可读取 |
| `POST /api/v1/agent/serve` | `skills: ["report-template"]` 选择本轮技能 |
| `POST /api/v1/admin/skills/upload` | 管理员上传 ZIP |
| `GET /api/v1/admin/skills/{id}/package` | 管理员下载当前标准包 |
| `GET /api/v1/admin/skills/{id}/resource` | 管理员查看指定版本资源 |
| `PATCH /api/v1/admin/skills/{id}/enabled` | 带 revision 的启停操作 |
| `DELETE /api/v1/admin/skills/{id}?revision=N` | 删除上传技能，保留恢复数据 |
| `POST /api/v1/admin/skills/{id}/restore` | 带 revision 的恢复操作 |
| `GET /api/v1/admin/skills?include_deleted=true` | 管理员目录，包含最近删除 |

所有写接口继续使用现有管理员认证和设备请求签名。访客可使用启用的技能，不能上传或管理包。

## 已验证

- 80 项后端测试通过，包括删除恢复与内置来源保护、ZIP 边界、权限、修订冲突、老版本资源固定、显式技能注入、关闭工具不可绕过、比例预算与剩余输出空间，以及原有数据库/检索/访问控制回归。
- 前端类型检查、ESLint 和生产构建通过。
- 页面实际上传了 `report-template.zip`，识别为 3 个文件、版本 1、来源“已上传”。
- 页面实际验证目录展开收起、切换文件时弹窗等宽等高、上传技能删除恢复与内置技能菜单保护。
- `/` 菜单及回车选择通过；实际读取上传包的参考资料和模板，再查得订单总数 5000，并以“结论 / 依据 / 范围与限制”回答。
- 未指定 Skill 的真实任务也能按需加载内置 SQL 技能和查询清单，完成订单分组图及合计核对；一次出现的 SQL 错误已由模型修正后完成。

参考：[LangChain Model profiles](https://docs.langchain.com/oss/python/langchain/models#model-profiles)、[原生总结比例阈值](https://docs.langchain.com/oss/python/langchain/middleware/built-in#summarization)、[LangChain Skills 模式](https://docs.langchain.com/oss/python/langchain/multi-agent/skills)、[Agent Skills 规范](https://agentskills.io/specification)。

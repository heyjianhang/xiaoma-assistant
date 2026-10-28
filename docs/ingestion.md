# 文档入库与索引发布

## 处理边界

PDF 使用 MinerU precision v4：申请上传地址、上传文件、轮询结果、下载结构化 ZIP。API Key 只发送到 MinerU API，不发送到上传和下载的签名地址。ZIP 不直接解压到文件系统，限制成员数量、总解压大小和结构化 JSON 大小。缺少结构化内容或表格正文时明确失败，不以纯 Markdown 代替并声称结构得到保留。

Markdown 使用 markdown-it 解析标题、段落、表格、代码与行范围；额外识别独立 `$$` 公式。表格、公式后紧随的“注、说明、式中”等段落并入对应结构单元。结构分块器按完整单元分组，标题与后续正文优先同块；长度是组合目标，完整结构单元允许超长。

最终每块转换为 `langchain_core.documents.Document`，转换后不再调用通用字符分块器。

| Document 字段 | 内容 |
| --- | --- |
| `id` | 基于本次索引 ID、序号、内容 hash、分块器版本生成的 UUID |
| `page_content` | 完整 Markdown；MinerU 表格可保留 HTML 表格 |
| `metadata.document_id` | 原文档 UUID，与分块 UUID 分开 |
| `revision` / `index_id` | 处理版本 / 本次执行的索引标识 |
| `source` / `section_path` | 文件名与章节路径 |
| `block_ids` / `source_refs` | 来源内容块、原页索引或 Markdown 行范围 |
| `parser` / `chunker_version` | 解析器与分块器版本 |
| `content_hash` / `oversized_atom` | 内容摘要和超长完整单元标记 |

同一索引内 ID 稳定。过期任务被接管时分配新的 `index_id`，防止旧执行过程覆盖新索引；不同执行尝试不承诺相同分块 ID。

PDF 保存 MinerU Content List V1 的原始 bbox，并标记其为左上原点的 0–1000 归一化坐标（与 layout.json 的 PDF 点坐标区分）。适配器校验页索引、有限数值、坐标边界和正面积；有效区域通过 source_refs 传到 PDF.js 覆盖层，随页宽与缩放同步定位高亮，点击原文区域可反向选中分块。缺少有效 bbox 的文档保留页级定位。表格、附注各自保留来源区域。Markdown 保留 1-based 行范围。正文使用统一 Markdown / HTML 表格渲染器，长块仅在显示层折叠，不截断入库或模型上下文。

## 数据与状态

PostgreSQL 的独立知识 schema 包含：

- `documents`：原文件 hash、大小、处理配置、最新版本及已发布版本。
- `ingestion_jobs`：任务状态、阶段、尝试次数、租约、错误信息。
- `chunks`：已发布版本的正文、来源元数据、启用状态。
- `vectors`：LangChain 管理的正文、向量、元数据与过滤列。
- `index_config`：Embedding 模型、维度、地址指纹，避免混用向量空间。

```text
queued → parsing → chunking → indexing → ready
                                  └──→ failed
```

上传返回 202，任务存入 PostgreSQL，由应用后台 worker 领取。领取使用 `FOR UPDATE SKIP LOCKED`；心跳续租，进程退出后过期任务可被接管。HTTP 请求不等待 MinerU 完成长解析。

LangChain 当前版本逐条提交向量写入，整批不是一个事务。因此所有新向量先设 `active=false`。全部写入成功后，在同一个数据库事务中：校验当前执行权、保存规范分块、关闭旧索引、打开新索引、更新文档与任务状态。部分写入失败不进入检索，旧索引仍可用。

每次尝试拥有独立索引 ID，发布前校验任务状态及当前索引 ID。取消、删除或租约接管后的旧执行不能发布。未发布向量与历史产物暂时保留供调试，尚未提供定期清理任务。删除为软删除，原文件不会立即物理擦除。

重处理可以更改结构分块长度；成功后分块启用状态初始化为启用，不自动继承旧版本的手工禁用。查看分块始终返回已发布版本；同时返回当前处理状态，避免把“重处理失败”误认为“旧数据已丢失”。

## 检索与观测

检索用 LangChain Retriever，强制过滤 `active=true`、`enabled=true`。开启重排时先召回候选，再通过 LangChain `RunnableLambda` 调用百炼重排；重排只调整顺序并增加分数，不改写分块，不删除来源元数据。分数表示本次查询的相关性，不代表答案正确概率。

入库向量写入仅使用 `PGVectorStore.aadd_documents()`，应用不自行 INSERT 向量。应用事务只管理业务状态和发布过滤列。

配置 `LANGSMITH_TRACING=true` 和 Key 后，记录入库处理链和安全错误，以及 Retriever / 重排运行。真实 LangSmith 远端追踪尚待配置验证；默认关闭，不影响本地处理。生成式回答与 ReAct Agent 已接入，运行与权限设计见 [Agent 与访问控制](agent-and-access.md)。

模型连接统一来自 `MODEL_BASE_URL`、`MODEL_API_KEY`，聊天、Embedding 与重排按模型名区分。百炼重排原生接口地址从同一网关 URL 推导；其他兼容服务不保证支持该接口，可关闭重排。

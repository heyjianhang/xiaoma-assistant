# 部署与配置边界

仓库已验证本地运行，尚未发布公网或完成生产负载测试。Compose 当前只管理 PostgreSQL；Python 与 Next.js 按 [README](../README.md) 启动，不是完整容器化部署。

## 服务拓扑

```text
浏览器 ─ HTTPS ─ 反向代理 ─ Next.js ─ 同源 API 代理 ─ FastAPI ─ PostgreSQL
                                                   ├─ 私有原文件 / MinerU 产物
                                                   └─ 模型 / MinerU / 可选 LangSmith
```

只开放 HTTPS 入口，API 和数据库保留回环/内网访问。Python 入口为 `xiaoma.app:app`，开发脚本监听 `127.0.0.1:2025`。生产可用进程管理器运行同一入口；不要额外暴露绕过认证的图执行服务。Next.js 构建后以 `pnpm --dir apps/web start --hostname 127.0.0.1 --port 3002` 启动。

## 必要配置

| 配置 | 用途 |
| --- | --- |
| `WEB_ORIGIN` | 实际前端 HTTPS origin，须与签名请求来源一致 |
| `AUTH_COOKIE_SECURE=true` | HTTPS 下使用 Secure 会话 Cookie |
| `MODEL_BASE_URL` / `MODEL_API_KEY` | 只保存在服务端的模型连接 |
| `MINERU_API_KEY` | 只用于 PDF 解析服务 |
| `DATABASE_URL` | 应用状态与入库连接 |
| `BUSINESS_DATABASE_URL` | 导入脚本创建的独立只读业务连接，不与写连接混用 |
| `STORAGE_ROOT` | 持久化、非公开的文档存储目录 |
| `BACKEND_URL` | Next.js 服务端的 API 地址 |

默认会话 24 小时。邀请有效期、撤销和设备绑定在服务端验证；浏览器环境不是硬件身份。详情见 [访问控制](agent-and-access.md)。管理员初始化凭据仅保存本机私有文件，不放进镜像、Git 或网页静态目录。

## 反向代理与持久化

- SSE 关闭缓冲/压缩变换，允许流式输出，连接超时覆盖 Agent 总预算（默认 900 秒，应用前端代理为 960 秒）。
- 保留请求路径、查询参数和正文，不重写已签名内容；配置合理的请求体限制和入口限流。
- PostgreSQL 卷与 `STORAGE_ROOT` 分别备份；仅备份向量不能恢复原文高亮。Skill、身份与会话也在应用数据库中。
- `.env`、管理员凭据、CLI 密钥和运行报告保持私有文件权限；数据库和原文件备份也不提交。
- 变更 Embedding 模型/维度/地址时使用新的 `KNOWLEDGE_SCHEMA` 重新入库；不混用向量空间。修改环境变量后重启。

聊天和解析通过 PGMQ 队列消费，先执行 `uv run --project apps/api python scripts/init_queue.py` 安装固定版本的官方 SQL-only 分发。默认 API 内启动后台池；独立部署时将 API 的 `BACKGROUND_WORKERS_ENABLED=false`，另用 `sh scripts/worker.sh` 启动消费进程。Worker 与 API 使用同一数据库、配置和持久文件目录。

停止请求通过数据库撤销执行令牌，能够阻止另一进程的旧 Worker 继续发布结果。排队任务可跨重启继续；聊天执行中进程故障则保存部分结果、标记中断并要求重新发送，不自动重放模型与工具。解析任务过期可接管。跨主机仍需共享文档存储，尚未实现对象存储、事件/历史文件自动清理或生产高可用验证。详见 [后台任务](background-jobs.md)。

## 发布后验收

检查健康接口、管理员登录、邀请首次绑定/过期/撤销、跨身份聊天隔离、多文件上传和原文访问；实际发送一条 RAG、一条 SQL 和一条 HYBRID，确认 SSE 在结束前持续到达；同时开启两个会话，切换页面并刷新，确认任务继续且输出不重复；显式停止其中一个不影响另一个。按 [测试说明](testing.md) 核对工具与结果，不能只检查页面可打开。

LangSmith 为独立可选外部服务。只有配置并开启 `LANGSMITH_TRACING` 才上传追踪数据；其中可能包含问题、文档与结果，应按部署的数据范围决定是否启用。当前远端追踪未验证。

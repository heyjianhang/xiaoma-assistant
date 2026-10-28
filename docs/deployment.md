# 部署与配置

已在 Linux amd64 服务器完成 Web、API、Worker、PostgreSQL 四容器部署与公网 HTTPS 功能验收，见 [验证记录](validation.md)。下方提供独立服务器的可复现配置；不分发作者的私有配置、证书、会话或数据库快照。首次本地体验使用 [README](../README.md) 的开发启动步骤。

## 服务拓扑

```text
浏览器 → HTTPS / Nginx → Web → FastAPI → PostgreSQL / PGMQ
                                       ↑               ↓
                                       └──── Worker ────┘
                                             ├─ LangChain Agent / 模型
                                             └─ MinerU / 分块 / 向量化
```

Web 仅绑定宿主机回环地址，API 与数据库只在 Compose 网络中访问。原文件和解析产物位于私有目录，向量、规范分块、身份、Skill、消息、运行快照和队列分别持久化；关闭浏览器不停止后台任务。

## 生产初始化

需要 Docker Compose 和 Python 3。以下命令在仓库根目录执行，使用单独的 `xiaoma-assistant-production` 项目及数据卷，不复用本地开发库。

```bash
python3 scripts/init_local.py
mkdir -p var/documents
chmod 700 var var/documents
```

编辑自动生成的 `.env`，保留随机生成的数据库密码，并填写实际服务配置：

| 配置 | 生产取值 |
| --- | --- |
| `DATABASE_URL` | 将本机地址改为 `postgres:5432`，保留 `.env` 中相同的数据库用户名、密码和库名 |
| `POSTGRES_PASSWORD` | 与上述连接相同的随机密码，不使用示例占位值 |
| `STORAGE_ROOT` | `/app/var/documents` |
| `WEB_ORIGIN` | 实际 HTTPS origin，如 `https://assistant.example.com`，含非默认端口时必须保留端口 |
| `AUTH_COOKIE_SECURE` | `true` |
| `APP_UID` / `APP_GID` | 在 `.env` 追加 `id -u` / `id -g` 的数值，默认1000；使 API、Worker、初始化器与配置/文档目录的所有者一致 |
| `BACKGROUND_WORKERS_ENABLED` | `false`，API 不启动消费池，独立 Worker 消费 |
| `MODEL_BASE_URL` / `MODEL_API_KEY` | 模型网关，只留在服务端 |
| `CHAT_MODEL_IDS`、Embedding 与重排模型 | 选择网关实际开放的模型及正确向量维度 |
| `MINERU_API_KEY` | 真实 PDF 解析密钥；Markdown 不需要 |

`BUSINESS_DATABASE_URL` 与 `ADMIN_PASSWORD_HASH` 留空，由初始化生成；已有值不会被静默替换。不要把开发库地址或已有数据库密码改成示例值。已有部署升级时先备份，不把下面的新部署初始化过程当作数据库迁移工具。

```bash
docker compose --env-file .env -f deploy/compose.yaml build api web
docker compose --env-file .env -f deploy/compose.yaml up -d --wait postgres
docker compose --env-file .env -f deploy/compose.yaml --profile setup run --rm setup
docker compose --env-file .env -f deploy/compose.yaml up -d --wait api worker web
docker compose --env-file .env -f deploy/compose.yaml ps
```

一次性 `setup` 容器以当前操作用户运行，挂载源码目录，让初始化器能原子更新私有 `.env`：安装固定且校验 SHA-256 的 PGMQ SQL-only 分发，导入合成业务表并创建独立只读账号，生成管理员密码。其余服务只读挂载 `.env`。管理员初始凭据在 `var/admin-credentials.json`（0600）；首次登录后到知识库上传 [演示 PDF](../data/examples/README.md)，等待入库完成。

应用镜像默认 UID 1000；Compose 按 `.env` 中 `APP_UID` / `APP_GID` 覆盖 API、Worker 与初始化器的运行身份。配置与文档目录须归该用户所有，不使用全局可写权限。`var/documents` 必须在 API 和 Worker 中指向同一持久目录。

前端使用 Next.js standalone，构建时已包含锁定的 PDF.js 与用例资源。`BACKEND_URL=http://api:2025` 同时在构建和运行时设置；Next.js rewrites 的目的地由构建产物决定，修改后需要重建 Web 镜像。API 镜像保留固定源码路径，以正确找到根目录的配置和内置 Skill。

若本机 Docker 报默认地址池已耗尽，先检查已有网络及 VPN 网段，给本项目的 Compose override 指定确认未占用的子网；不要通过删除其他项目网络或全局清理绕过。此类宿主机环境调整与应用数据初始化分开处理。

## HTTPS 入口

在宿主机 Nginx 为已授权的域名添加独立站点，参考 [配置示例](../deploy/nginx.conf.example)。替换域名与证书路径，使用已签发且自动续期的可信证书；先检查和备份已有配置，`nginx -t` 通过后再平滑 reload。按服务器现有规范发布，不覆盖全局配置或其他业务站点。

- 公网只开放 HTTPS 入口；Web 回环端口默认48940，API 与 PostgreSQL 不映射宿主机端口。
- SSE 关闭请求/响应缓冲，保留 `no-transform` 与 `X-Accel-Buffering: no`，超时覆盖 Agent 总预算。不要额外开启代理压缩攒住小事件。
- 保留原始路径、查询参数、请求体与 Host，避免破坏设备签名；覆盖客户端伪造的转发协议/IP头。
- 上传上限24 MiB，应用单文件上限20 MiB。确认云端安全组/防火墙允许实际 HTTPS 端口。
- 使用有有效续期部署钩子的证书管理方式，并从外部网络验证证书、登录、上传和 SSE；不以本机可访问或跳过证书校验代替公网验收。

## 数据与运行维护

PostgreSQL 命名卷与 `var/documents` 分别备份，保持同一时间点；只有向量无法恢复原文与高亮。初始化完成后的 `.env` 也要独立受控保管。升级前停接新任务，等待或显式停止执行中的任务，再制作数据库与文件快照。

```bash
docker compose --env-file .env -f deploy/compose.yaml logs --tail 100 api worker web
docker compose --env-file .env -f deploy/compose.yaml stop
docker compose --env-file .env -f deploy/compose.yaml up -d --wait
```

上述停止命令保留容器与数据。正常更新重建镜像后 `up -d --wait`；不要删除数据库卷或把作者本地快照导入评审者已有数据库。变更 Embedding 模型/维度时使用新的 `KNOWLEDGE_SCHEMA` 并重新入库，不混用向量空间。

服务设置自动重启与日志轮转。排队任务可跨重启继续；执行中的聊天进程故障会保存部分结果、标记中断并要求重发，不自动重放模型与工具；解析任务过期可接管。详见 [后台任务](background-jobs.md)。尚未提供对象存储、高可用、自动备份或事件保留期清理，未完成生产压力测试。

## 发布后验收

管理员登录；匿名文档接口返回401；邀请首次绑定、另一设备拒绝、聊天隔离、撤销失效；上传文档并查看 PDF 与分块；实际发送 RAG、SQL 和 HYBRID 问题；确认 SSE 在结束前到达、两个会话并发、断线后可补读、显式停止不影响另一会话。用 [验收目录](../tests/acceptance/cases.json) 对照实际依据与结论，不能只检查页面可打开。

LangSmith 默认关闭，只有显式配置 `LANGSMITH_TRACING=true` 才上传追踪数据，可能包含问题、文档与结果。当前未验证远端追踪，不作为部署的必要依赖。

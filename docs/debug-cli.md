# Agent 调试 CLI

CLI 通过正式 HTTP API 登录、签名请求和消费 SSE，执行的模型、Skill、工具开关、访问控制、上下文总结及持久化与网页一致。没有跳过认证或直接调用模型的调试后门，也不会因为断流自动重发问题。

## 启动与登录

在仓库根目录运行：

```bash
sh scripts/dev.sh
# 另一个终端，交互输入现有管理员密码，密码不进入命令历史
sh scripts/xiaoma.sh login
sh scripts/xiaoma.sh whoami
sh scripts/xiaoma.sh models
sh scripts/xiaoma.sh skills
```

也可使用 `uv run --directory apps/api xiaoma`。自动化可以使用 `login --password-stdin`，从受保护的输入流传入密码。不要把密码放在命令参数中。CLI 不读取管理员凭据文件，也不提供免认证模式。

默认服务地址为 `http://127.0.0.1:2025`，可通过 `--url` 或 `XIAOMA_API_URL` 指定。远程地址必须使用 HTTPS；HTTP 仅允许 localhost 或回环 IP。客户端不跟随重定向，不使用环境代理。身份文件按 origin 隔离，不能借另一服务的会话登录。

CLI 创建独立 P-256 设备密钥，采用与网页相同的登录挑战及逐请求签名协议。身份与会话保存到被 Git 忽略的 `var/debug-cli/`：目录权限 0700、文件权限 0600。此目录包含私钥和登录会话，不要分享。默认会话仍遵循服务端 24 小时设置，过期后重新登录；不会修改浏览器的设备密钥或使浏览器退出。

## 发送与追问

```bash
# 默认新对话，默认两类查询工具都开
sh scripts/xiaoma.sh chat '请查询全部订单总数，不限制日期。'

# 指定 Skill 与本轮工具范围（可以重复 --skill，最多 5 个）
sh scripts/xiaoma.sh chat '新版电子钱包退款到账最长期限是多少？' --skill knowledge --no-data
sh scripts/xiaoma.sh chat '请按订单状态统计数量。' --skill sql --no-knowledge

# 使用 models 返回的真实模型 ID
sh scripts/xiaoma.sh chat '请核对报表与明细的差异。' --model qwen3.8-flash

# 从上一次 result.json 取 conversation_id，继续同一对话
sh scripts/xiaoma.sh chat '这些状态合计与刚才总数一致吗？' --thread CONVERSATION_UUID --no-knowledge

# 长测试输入或机器可读结果；全局参数放在 chat 前面
sh scripts/xiaoma.sh --json chat --input tests/prompt.txt --skill sql --no-knowledge
sh scripts/xiaoma.sh --json chat --input -
```

默认流式回答写 stdout，进度和工具状态写 stderr。`--json` 时 stdout 只输出一个完整结果 JSON，便于脚本读取；进度仍在 stderr。成功收到完成事件退出码为 0；服务错误、断流或参数错误为 1；Ctrl+C 为 130。完成表示本次执行完成，不等于答案已经通过语义验收。失败时保留部分回答，不把半截输出当作成功。聊天由后台队列执行，断流或 CLI 退出不会隐式取消；Ctrl+C 会尝试发送停止请求，若网络不可达，应重新登录后用 `stop RUN_UUID` 确认停止。`inspect` 可以读取后台保存的进度和结果，不能以订阅结束判断任务成功。

每次发送保存一份 `var/debug-runs/北京时间-随机ID/`：

| 文件 | 内容 |
| --- | --- |
| `request.json` | 问题、会话 ID、模型选择、工具开关和 Skill 选择 |
| `events.jsonl` | 按收到顺序记录 SSE 事件及相对接收时间 |
| `answer.md` | 原始 Markdown 回答，失败时为已收到的部分 |
| `result.json` | 完成状态、错误、工具最终状态、Todo、引用、结果卡和客户端耗时 |
| `runtime.json` | 服务端运行状态、配置快照及持久化的用户/助手消息 |

目录和文件同样使用 0700 / 0600。不会自动保存登录密码、Cookie 或模型 API Key 到运行报告。工具输出和问题可能包含业务数据，因此整个 `var/` 保持 Git 忽略。首字耗时及工具耗时来自客户端事件接收时间；不冒充模型服务的精确 Token 用量、费用或内部思考过程。

服务端快照保留本次模型 Profile、生成与执行预算、上下文策略、Skill 正文与版本，以及 Agent 组装时的系统提示词和 SHA-256。该系统提示词是 `create_agent` 的入参，不是每一次调用经中间件处理后的完整模型请求；Todo 与总结提示词见下方源码位置。旧运行没有新增字段时保持缺失，不用当前提示词回填历史。

## 查看与清理

```bash
sh scripts/xiaoma.sh threads list
sh scripts/xiaoma.sh threads show CONVERSATION_UUID
sh scripts/xiaoma.sh inspect RUN_UUID
sh scripts/xiaoma.sh stop RUN_UUID
sh scripts/xiaoma.sh threads archive CONVERSATION_UUID
sh scripts/xiaoma.sh threads restore CONVERSATION_UUID

# 先导出清单，再软删除当前身份的可见对话，跳过正在运行的对话
sh scripts/xiaoma.sh threads clear --yes
sh scripts/xiaoma.sh logout
```

`threads clear` 在第一次归档前将会话及消息导出为 `var/debug-runs/archive-*.json`，并逐条记录已归档和跳过的 ID。通过 `threads restore ID` 恢复；原数据库中的消息、运行和上下文不会物理删除。它不修改知识库、业务表、邀请、Skill 或其他访客的对话。

调试读取接口为 `GET /api/v1/admin/debug/runs/{id}` 与 `GET /api/v1/admin/debug/conversations/{id}`：要求管理员身份且记录属于该身份。访客不能访问；管理员也不能凭 ID 读取另一访客的运行。会话详情中的 `latest_context` 是该会话当前最新的压缩/近期上下文，不应当成任意历史运行当时的输入。

## 优化顺序

1. 固定基线输入：普通 RAG、单独 SQL、文档与数据核对、歧义/缺失/小样本。默认新对话，只有多轮用例复用 `--thread`。
2. 一次只改一个层次，保留每次运行报告；核对实际工具顺序、SQL 口径、引用及事实，不能只比较文案是否流畅。
3. 系统规则在 `apps/api/src/xiaoma/agent/skills.py`；最终组装、Todo/总结提示词在 `apps/api/src/xiaoma/agent/builder.py`；预算与重试在 `resilience.py` 和 `settings.py`。修改 Python 后重启 API。
4. 内置 Skill 源码位于 `skills/*/SKILL.md`，数据库保存启用版本。单改磁盘文件不会覆盖已存在的数据库版本；通过 Agent 配置页上传标准 ZIP 更新版本，随后用 `skills` 和 `inspect` 核对本轮实际版本。
5. 基线稳定后再增加成批回归及 LangSmith 评估。当前 CLI 不带未验证的自动判分，也不自动改提示词。

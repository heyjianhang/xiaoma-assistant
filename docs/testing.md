# 测试与场景验收

## 自动化检查

按 [README](../README.md) 安装依赖、初始化环境和导入业务数据后：

```bash
make check-backend
make check-web
python3 scripts/check_repository.py
```

后端检查 Ruff、格式和 Pytest。集成测试连接真实 PostgreSQL / pgvector，在随机 `test_*` Schema 中创建并清理测试状态；业务查询只读访问导入的合成业务表，不删除应用知识库或聊天。

Embedding、MinerU、重排及部分模型采用受控 HTTP / 模型响应，用于检查请求契约、结构完整性、工具循环、权限、持久化和错误恢复，不用于衡量语义质量。SSE 有客户端在生成完成前必须收到首段的 TCP 测试。

前端检查 TypeScript、ESLint、5 项引用 AST/Streamdown 回归及 Next.js 生产构建。`check_repository.py` 检查公开候选文件中的本机路径、常见密钥特征、禁止提交的产物、Markdown 相对链接和验收集覆盖；这是仓库卫生检查，不是完整安全审计。

[CI](../.github/workflows/ci.yml) 使用独立 pgvector 服务与测试凭据导入合成数据，不需要真实模型密钥。本地通过不等于远端 CI 已执行，最新状态见 [验证记录](validation.md)。

## 真实模型验收

输入与预期保存在 [cases.json](../tests/acceptance/cases.json)。它是可复查的验收清单，不会作为模型上下文或知识库文档，也没有把预期输出伪装成真实调用。

准备：

1. 配置真实模型、Embedding 与可选重排；PDF 路径还需 MinerU。
2. 导入业务表，上传 [演示语料](../data/examples/README.md) 中各用例所需文档，等待状态为可检索。
3. 使用新对话，两类查询工具开启；固定模型与 Skill 版本。
4. 用 CLI 或网页发送用例，保留实际工具序列、答案、引用、SQL、结果卡与失败原因。

示例：

```bash
sh scripts/xiaoma.sh login
sh scripts/xiaoma.sh chat '订单110有申请和到账时间，能否判断退款是否超时？'
sh scripts/xiaoma.sh inspect RUN_ID
```

默认一次 `chat` 创建新对话；多轮用例显式使用 `--thread`。运行产物在私有 `var/debug-runs/`，详见 [CLI](debug-cli.md)。完成事件只说明运行结束，不能作为答案通过判分。

逐项检查：

- RAG：有实际检索，引用到文档及章节/条款，表格与注释支持结论。
- SQL：先目录、再候选结构、再显式链接、再只读执行；摘要与结果一致，不偷用静态答案。
- HYBRID：文档和 SQL 都取证；核对时间、范围、粒度及版本。
- 歧义：不自创“异常率”定义；允许先查资料，但定义不明时停止计算并澄清。
- 冲突：同口径 2% 与 8% 同时呈现，分子分母与两份来源可查，不静默取一方。
- 异常：3/3 显示样本量；缺 `accepted_at` 不替填；零分母和空结果不编造比率。

用例使用明确的2026年9月窗口，避免“上个月”随日期改变。页面预设问题中的相对日期按业务 `demo_context` 解释。

## 效果评估边界

单元测试通过、一次真实模型成功、引用 ID 有效和高重排分数是不同证据。当前没有成套 Recall@k、引用支持度、冲突判断准确率或路由准确率。后续按 [DECISIONS](../DECISIONS.md) 固定问题集做消融，先记录失败再调整提示词/Skill，避免边测边改而丢失基线。

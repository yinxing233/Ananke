# Ananke

基于存续检验（persistence-based）的三层记忆 MVP。实现严格遵循
[`Memory_Architecture_设计文档_MVP.md`](docs/Memory_Architecture_设计文档_MVP.md)：工作记忆只能经由存续得分迁入巩固层，巩固层只能经由局部重组迁入核心层。

## 运行

```bash
uv run python run.py
```

默认使用 mock LLM，因此无需 API 密钥；首次运行会下载 sentence-transformers 的本地嵌入模型。数据保存在 `data/*.jsonl`，审计事件保存在 `logs/events.jsonl`。

## 配置 LLM（接入真实模型）

密钥只来自环境变量 / `.env`，代码中不硬编码，且 `.env` 已被 `.gitignore` 忽略，不会上传到 git。

```bash
cp .env.example .env      # 然后填入你的 LLM_API_KEY
```

在 `.env` 中：

- `USE_MOCK_LLM=true`：离线 Mock，无需密钥（调试用）。
- `USE_MOCK_LLM=false`：接入真实 LLM，按 `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 切换服务商。

内置 `OpenAICompatibleClient`，覆盖 OpenAI / DeepSeek / OpenRouter / Groq / Ollama / **Gemini** 等——它们都走 OpenAI 兼容接口，仅靠 `.env` 里的 `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` 区分，**切换服务商无需改代码**。Gemini 使用其官方 OpenAI 兼容接口（不填 `LLM_BASE_URL` 时自动使用默认值）。需要 Anthropic 等其它后端时，在 `ananke/llm_client.py` 增加对应子类并注册到 `create_llm_client()` 工厂即可。

## 当前实现

- 三层 JSONL 存储、慢层优先检索与工作层容量淘汰
- 内部激活、非系统引导的外部验证、persistence score 与逐级迁移
- 仅在快→中迁移后触发的合并/矛盾局部重组检查
- 全链路 JSONL 操作日志
- 用 fake embedding/LLM 编写的确定性场景测试，覆盖迁移、重组、淘汰和重启恢复

## 测试与实验组

```bash
uv run pytest -q
```

默认实验组为 `Config.WORKING_PROMOTION_STRATEGY = "persistence"`：外部验证权重高于内部激活。设置为 `"frequency"` 可运行对照组；对照组只按内部激活次数（默认 3 次）将工作记忆迁入巩固层。两组共用提取、检索、容量淘汰与中→慢局部重组逻辑，以隔离快→中迁移准则的影响。

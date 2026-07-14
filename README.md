# Ananke

基于存续检验（persistence-based）的三层记忆 MVP。实现的权威定义来自
[`00_THEORY.md`](docs/00_THEORY.md)（理论层）与 [`01_PROTOCOL_v3.md`](docs/01_PROTOCOL_v3.md)（实验协议，唯一合法映射层）：工作记忆只能经由存续得分迁入巩固层，巩固层只能经由局部重组迁入核心层。初版设计稿 [`Memory_Architecture_设计文档_MVP.md`](docs/Memory_Architecture_设计文档_MVP.md) 已标记为历史文档（部分参数与现行实现相反，见其头部声明）。

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

在 `.env` 中（所有项均可缺省，缺省取括号内默认值）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `USE_MOCK_LLM` | `true` | `true`=离线 Mock（无需密钥）；`false`=接入真实 LLM |
| `LLM_PROVIDER` | `openai-compatible` | 服务商：openai / deepseek / openrouter / groq / ollama / openai-compatible |
| `LLM_BASE_URL` | （空） | 留空则使用 provider 默认接口 |
| `LLM_API_KEY` | （空） | 真实 LLM 密钥；绝不硬编码进代码 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `LLM_TEMPERATURE` | `0.0` | 固定 0.0 保证可复现（与协议控制变量一致） |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | 本地嵌入模型路径/名称 |
| `WORKING_PROMOTION_STRATEGY` | `persistence` | `persistence`=实验组（External Selection）；`frequency`=对照组（Internal Selection） |

> 切换服务商只需改 `.env`，无需改代码；所有 provider 走 OpenAI 兼容接口。

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

默认实验组为 `Config.WORKING_PROMOTION_STRATEGY = "persistence"`：外部验证权重高于内部激活。设置为 `"frequency"` 可运行对照组；对照组只按 `total_activation`（每次语义命中 cosine ≥ 0.60 即 +1，不区分来源，默认阈值 3 次）将工作记忆迁入巩固层，不复用 `internal_activation`。两组共用提取、检索、容量淘汰与中→慢局部重组逻辑，以隔离快→中迁移准则（选择压力来源）的影响。

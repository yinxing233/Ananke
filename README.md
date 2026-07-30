# Ananke

基于存续检验（persistence-based）的三层记忆实验仪器。当前权威层级为：

1. [`00_THEORY.md`](docs/00_THEORY.md)：稳定理论约束；
2. [`01_PROTOCOL_v4.md`](docs/01_PROTOCOL_v4.md)：当前协议草案；
3. [`DECISIONS_v0.2_freeze.md`](docs/DECISIONS_v0.2_freeze.md)：2026-07-30 经 PI 验收的
   B1–B7 冻结裁决集；
4. [`02_IMPLEMENTATION.md`](docs/02_IMPLEMENTATION.md)：当前实现事实与未完成项。

裁决集已经冻结且 B1–B7 已实现（`70 passed`），但协议 v4 **尚未正式冻结**，当前数据只属探索阶段。冻结历史协议 v3 与初版
[`Memory_Architecture_设计文档_MVP.md`](docs/Memory_Architecture_设计文档_MVP.md) 保留供审计，
不作为本轮代码修改依据。

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

## 当前实现边界

- pre-audit 代码包含三层 JSONL、召回—五分类、P/F 策略、缓存和事件日志；
- 2026-07-28 基线测试为 43/43；
- 2026-07-30 B1–B7 实现后为 70/70；
- 已闭合评估解析、轮级原子性、distinct-session EV、来源元数据和 CORE 召回；
- `system_guided` 是未启用接口，v0.2 runner 中恒为 False；
- 当前旧 253 轮没有可用 LLM 缓存，不能作为续跑检查点；
- 正式验证前仍须完成独立复核、冒烟校准、验证集锁定和 `PREREGISTRATION.md`。

## 测试与实验组

```bash
uv run pytest -q
```

默认制度为 `persistence`，可切换为 `frequency`。协议 v4 将两者定义为**两套完整选择制度**：
差异从计分出发，经晋升、容量淘汰与后续召回路径传播；本实验比较制度整体的沉淀质量，
不声称隔离了计分函数的单因子效应。

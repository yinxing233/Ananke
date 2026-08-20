# Ananke

[![CI](https://github.com/yinxing233/Ananke/actions/workflows/ci.yml/badge.svg)](https://github.com/yinxing233/Ananke/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

用于比较长期记忆选择制度的三层记忆实验仪器。

长期记忆系统会不断写入信息，但「哪些记忆应该进入更稳定的层级」通常隐含在实现里，难以单独检查。Ananke 把这个问题改写成可重复实验：同一输入流分别经过 Persistence（外部验证参与选择）和 Frequency（内部重复参与选择）两套制度，在 `WORKING → CONSOLIDATED → CORE` 三层中演化，并记录每次提取、召回、晋升、冲突和评估事件。

它不是面向终端用户的记忆产品，也不以回答质量作为当前主指标。项目要交付的是一套可运行、可审计、允许结论为假的评测仪器：冻结操作定义，控制两遍运行的非实验变量，再根据必要比较组是否存在，将推测判为 `held`、`not_held` 或 `not_testable`。

## 当前结果与边界

2026-08-18，`conv-26` 在两套制度下各完成 419 轮、19 个 sessions 的探索性运行：

| 观测量 | Persistence | Frequency |
| --- | ---: | ---: |
| 第一闸升层记忆 | 14 | 62 |
| 最终 WORKING / CONSOLIDATED / CORE | 50 / 8 / 6 | 50 / 45 / 17 |

归一化后的升层集合为 P-only=0、F-only=48、D=48，说明两套制度确实产生了不同轨迹。但两侧终态记忆的外部验证信号总和都是 EV=0，关键比较组不存在，因此目前不能把差异归因于 External Selection；两项推测都必须保持 `not_testable`。这次运行验证的是仪器能够完整执行并暴露不可检验条件，不是理论命题已经成立。协议 v4 也尚未正式冻结。

仓库提供三类可以直接检查的材料：

- **评测设计**：操作定义、P/F 对照制度、三态判定函数和主张边界；
- **工程实现**：三层 JSONL、内容寻址缓存、只读 preflight、轮级原子性和审计事件；
- **研究治理**：冻结裁决、声明层级和三个 agent 漂移案例，记录设计如何在审查中被修正。

## 快速检查

```bash
uv sync --locked
uv run pytest -q -p no:cacheprovider
uv run python run.py
```

测试不需要 API 密钥。`run.py` 默认使用 mock LLM；第一次运行交互示例时会下载本地 embedding 模型。探索性点火报告见 [`REPORT.md`](REPORT.md)，设计漂移案例见 [`CASE_STUDIES.md`](docs/CASE_STUDIES.md)。

## 文档地图（新会话先读这里，不用扫全部 docs）

| 文档 | 一句话 | 何时读 |
|---|---|---|
| [`REPORT.md`](REPORT.md) | 探索性点火报告：两个观察→仪器→结果→EV=0 三解释→not_testable | 想了解这个项目做了什么 |
| [`CASE_STUDIES.md`](docs/CASE_STUDIES.md) | 治理案卷：3 个漂移事件如何被抓住与制度化 | 想了解"如何治理 AI 执行者" |
| `00_THEORY.md` | 理论公理（几年不变） | 讨论理论时 |
| `01_PROTOCOL_v4.md` | 当前协议草案（操作定义+判定函数） | 改代码/跑实验前 |
| `01_PROTOCOL_v3.md` | v0.1 冻结协议（审计锚点） | 审计历史轮次 |
| `DECISIONS_v0.2_freeze.md` | B1–B7 冻结裁决 + 后续修订（§12–§14） | 改动受裁决约束的行为前 |
| `02_IMPLEMENTATION.md` | 实现事实 + 语义债 + 待办 | 实现 agent 必读 |
| `03_RESEARCH_LOG.md` | 研究过程日志（讨论脉络/审查/漂移纠正） | 复盘决策演进 |
| `RESEARCH_CONJECTURES.md` | 推测 1/2/3（not_testable 现状） | 看实验主张时 |
| `IGNITION_RECEIPT_v0.2.md` | conv-26 点火回执（指纹/计量/产物哈希） | 审计运行真实性 |
| `00_Claim_Chain.md` | 声明层级链 + 当前状态 | 了解主张边界 |
| `docs/memos/` | 协作约定 + 归档索引 | 会话开始 |
| `docs/archive/` | 历史归档（v0.1 轮次 + v0.2 过期文档） | 审计历史 |
| `docs/calibration/` | 判例集 + 冻结清单 | 校准相关工作 |

**按角色必读**：
- **PI / 求职读者**：`README` → `REPORT` → `CASE_STUDIES`（3 份看完即可）；
- **实现类 agent**：`README` → `02_IMPLEMENTATION` → `DECISIONS` → 当前协议（4 份）；
- **审查类 agent**：全量（一次性审计场景才需要）。

文档的权威层级依次是：[`00_THEORY.md`](docs/00_THEORY.md) 的稳定理论约束、[`01_PROTOCOL_v4.md`](docs/01_PROTOCOL_v4.md) 的当前协议草案、[`DECISIONS_v0.2_freeze.md`](docs/DECISIONS_v0.2_freeze.md) 的冻结裁决，以及 [`02_IMPLEMENTATION.md`](docs/02_IMPLEMENTATION.md) 的实现事实与未完成项。B1–B7 裁决已经冻结并实现；历史协议 v3 与初版 [`Memory_Architecture_设计文档_MVP.md`](docs/Memory_Architecture_设计文档_MVP.md) 只用于审计，不作为当前代码修改依据。

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
| `LLM_PROVIDER` | `openai-compatible` | 服务商：openai / deepseek / gemini / openrouter / groq / ollama / openai-compatible |
| `LLM_BASE_URL` | （空） | 留空则使用 provider 默认接口 |
| `LLM_API_KEY` | （空） | 真实 LLM 密钥；绝不硬编码进代码 |
| `LLM_MODEL` | `deepseek-chat` | 模型名 |
| `LLM_FAMILY` | （自动推断） | 模型家族；模型名不透明时显式填写，供 judge 家族分离检查 |
| `LLM_TEMPERATURE` | `0.0` | 固定 0.0 保证可复现（与协议控制变量一致） |
| `LLM_RPM` | `30` | 驱动端预防性 RPM 节流；429 重试仍逐请求计量 |
| `CACHE_ENABLED` | `true` | 提取/分类内容寻址缓存；正式模式强制开启 |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | 本地嵌入模型路径/名称 |
| `WORKING_PROMOTION_STRATEGY` | `persistence` | `persistence`=实验组（External Selection）；`frequency`=对照组（Internal Selection） |

> 切换服务商只需改 `.env`，无需改代码；所有 provider 走 OpenAI 兼容接口。

内置 `OpenAICompatibleClient`，覆盖 OpenAI / DeepSeek / OpenRouter / Groq / Ollama / **Gemini** 等——它们都走 OpenAI 兼容接口，仅靠 `.env` 里的 `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` 区分，**切换服务商无需改代码**。Gemini 使用其官方 OpenAI 兼容接口（不填 `LLM_BASE_URL` 时自动使用默认值）。需要 Anthropic 等其它后端时，在 `ananke/llm_client.py` 增加对应子类并注册到 `create_llm_client()` 工厂即可。

## 当前实现边界

- pre-audit 代码包含三层 JSONL、召回—五分类、P/F 策略、缓存和事件日志；
- 2026-07-28 基线测试为 43/43；
- 2026-07-30 B1–B7 实现后为 70/70；2026-08-02 来源上下文保真修复后为 73/73；
- 2026-08-08 路径 A 保护批次后为 90/90：请求级 token/HTTP 计量、只读 preflight、
  normalized exact duplicate、B7 异常边界、6-token 上限、judge family 分离与 P/F 串行锁；
- 2026-08-18 空集降级回归测试加入后为 92/92；
- 已闭合评估解析、轮级原子性、distinct-session EV、来源元数据和 CORE 召回；
- `system_guided` 是未启用接口，v0.2 runner 中恒为 False；
- 旧 253 轮没有可用 LLM 缓存，不能作为续跑检查点；新的 `conv-26` P/F 运行已产生两级缓存并验证跨制度复用；
- 正式验证前仍须完成 `R_RECALL` 定值、关系分类器独立验收、验证集锁定和
  `PREREGISTRATION.md`；探索性全链路冒烟本身已经完成。

## `conv-26` 探索性点火（2026-08-18）

P/F 两遍均完成 419 轮、19 sessions。Persistence 第一闸升层 14 条、最终
WORKING/CONSOLIDATED/CORE = 50/8/6；Frequency 第一闸升层 62 条、最终 50/45/17。
归一化后 P-only=0、F-only=48、D=48，两侧 EV 总和都是 0。所以这是真实的制度分叉，
但不能被识别为 External Selection 对 Internal Selection 的效果。全量 judge evaluate 因结构性缺组被否决。

完整解读见 [`REPORT.md`](REPORT.md)，运行指纹与计量回执见
[`IGNITION_RECEIPT_v0.2.md`](docs/IGNITION_RECEIPT_v0.2.md)。

## 测试与实验组

```bash
uv run pytest -q
```

默认制度为 `persistence`，可切换为 `frequency`。协议 v4 将两者定义为**两套完整选择制度**：
差异从计分出发，经晋升、容量淘汰与后续召回路径传播；本实验比较制度整体的沉淀质量，
不声称隔离了计分函数的单因子效应。

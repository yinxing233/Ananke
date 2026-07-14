# 02 · IMPLEMENTATION（当前实现 / 可频繁变更）

> 本文件记录**当前**实现状态，可能数天到数月全部更换，理论不受影响。
> 冻结的协议见 `01_PROTOCOL_v3.md`；理论见 `00_THEORY.md`；研究过程见 `03_RESEARCH_LOG.md`。

## 当前状态（2026-07-14，已升级协议 v3）
- **协议已升 v3**（2026-07-14，PI 决策）：EV 阈值 0.85→0.80；新增「写入前去重」控制变量 `DEDUP_SIMILARITY_THRESHOLD=0.80`（pipeline 在提取后、写入前比对既有 working+consolidated 记忆，≥0.80 跳过写入并记 `memory_dedup_skip`，消除真实 LLM 提取碎片化混杂）；提取 Prompt 改「输出与输入同语言」。详见 `01_PROTOCOL_v3.md`。
- MVP 核心逻辑**已完成且被测过**：`uv run pytest` → 12/12 通过（确定性测试，用 FakeEmbedding / FakeLLM）。真实跑亦通过（见下）。
- LLM 接入层：provider 抽象（`BaseLLMClient` + `MockLLMClient` + `OpenAICompatibleClient`），工厂 `create_llm_client()`。已支持 Gemini / DeepSeek / Groq / OpenRouter / Ollama / OpenAI。密钥走 `.env`（已被 .gitignore 忽略），零硬编码。`OpenAICompatibleClient.call_llm` 对真实 API 限流（如 Gemini 免费层 15 req/min 的 429）做**指数退避重试**（8s→16s→32s→…，最多 6 次），保证任意长度语料都能跑完——纯 I/O 韧性，不影响理论行为。
- 观测工具（纯增益、非漂移）：
  - `tools/analyze_trajectory.py`：§九 日志 → per-memory **Memory Trajectory**（状态轨迹 + SVG 事件时间线 + 失败样本区）。纪律：只描述给定规则下系统产生的动力学（Rule→Dynamics），不判定理论。
  - `tools/dev_simulate.py`：确定性合成驱动（真实 pipeline + logger，FakeEmbedding + ScriptedLLM），验证管道，非实验语料；写 `logs/dev_events.jsonl` + `data/dev/`。
  - `tools/run_corpus.py`：用**真实** EmbeddingEngine + `create_llm_client()` 跑外部语料，产出真实语义日志；支持 `--strategy persistence|frequency`。守反身性红线（只喂外部语料，绝不自生成）。

## 模块清单（ananke/）
config / embedding / llm_client / extraction / activation / migration / reorganization / memory_store / logger / models / pipeline / promotion（共 12 个功能模块；另含 `__init__.py` 与运行入口 `main.py` / `run.py`，不计入模块数）。

## 事件日志类型（logger event key，全 8 类）
`memory_write` / `internal_activation` / `external_validation` / `working_eviction` / `working_to_consolidated` / `local_reorganization` / `consolidated_to_core` / `memory_dedup_skip`（v3 新增，写入前去重命中时记）。代码 log 的英文 event key 与历史设计文档的中文事件名无一一对照，以此清单为准。

## 当前具体选型（属 Implementation，可换）
- 嵌入模型：`all-MiniLM-L6-v2`（英文模型；中文阈值待 Phase 3 sweep，当前只验证"动力学是否发生"）。
- LLM：`.env` 配 `LLM_PROVIDER=gemini` + API key，`USE_MOCK_LLM=false` 时走真实；默认 mock。
- 控制变量（冻结于协议）：LLM 同源、Temperature = 0.0、Prompt 冻结。

## 尚未完成（MVP 边界 / 后续）
- 真实 LLM 端到端**已实跑且全链路跑通**（2026-07-14，Gemini + 本地 all-MiniLM-L6-v2）：
  - **26 句 Phase 1 长语料**（`corpus_phase1.txt`，badminton×6 / Mochi×6+矛盾×2 / 噪声若干），v3 配置。54 事件 = 2 EV + 22 IA + 8 去重跳过 + 21 写入 + **1 次 working→consolidated（badminton，persistence 3.10）**。这是**真实语义环境下第一例快→中迁移**，证明核心机制在真实 LLM 下启动。日志 `logs/real_events_p1b.jsonl` / `data/real_p1b`。
  - 三通过标准（Claude 定的 smoke test）：① badminton 升巩固层 ✓ ② Mochi 升层 + 矛盾触发重组 ✗（Mochi 因措辞多样碎成多条记忆，主记忆 persistence 1.84/3.0 未跨阈；矛盾句要么被去重跳过、要么相似度<0.90 未触发重组，local_reorganization=0）③ 噪声全停快层 ✓。
  - 关键发现：迁移对**输入措辞的语义冗余度高度敏感**——近义复述（badminton "plays badminton" 反复）会收敛升层；多样表述（Mochi 不同特质）会碎片化、不升层。这本身是可证伪的 Phase 1 动力学结果，非 bug。重组（REORG_SIMILARITY=0.90）只捕捉**近重复**记忆间的矛盾，不捕捉语义相关但表述不同的逻辑矛盾（如 "playful" vs "doesn't like touched"）——这是设计属性，是否需拓宽是 Phase 2/3 设计议题，非临时修。
  - 注意：沙箱 HuggingFace 快照软链接被拦，嵌入模型以真实副本存于 `data/all-MiniLM-L6-v2`，`.env` 的 `EMBEDDING_MODEL` 指向它。
- 合并 / 矛盾 **仅计数、不整合**（MVP 边界：整合会污染要观测的 trigger 信号）。
- 中文嵌入模型未换、阈值未标定（留给 Phase 3 sweep，非当前任务）。
- **Phase 3 对照实验（Route 1）已跑通**（2026-07-14，同语料 `corpus_phase1.txt` 仅切 `--strategy`）：
  - persistence（External Selection）→ 升巩固层 **1 次**（badminton，EV=2，persist=3.10）。
  - frequency（Internal Selection）→ 升巩固层 **4 次**（badminton + 3 条 **EV 全为 0** 的记忆："User loves badminton" / "The user adopted a cat named Mochi" / "Mochi the cat is playful and energetic"）。这 3 条正是 persistence 跑里**同一记忆对象**停留快层者（persist 1.10/1.84/1.47）。
  - 两遍提取记忆集完全一致（各 21 条，交集 21）→ 唯一变量 = Migration Rule，比较器有效。
  - 解读：External Selection 升层记忆全部 EV>0（受环境约束、稳定）；Internal Selection 把零外部验证、选择压力纯自循环的记忆也推上巩固层——协议 §5 预测的"退化为内部自循环、易被破坏的不稳定结构"。这是约束场理论在真实语义环境的 **Phase 3 先导实验（pilot）**——稳定性尚未测量（协议 §5 真比较器未执行，见 RELEASE 诚实边界）。日志 `logs/phase3_persist.jsonl`+`data/phase3_persist` / `logs/phase3_freq.jsonl`+`data/phase3_freq`；报告 `logs/phase3_persist_report.html` / `logs/phase3_freq_report.html`；对比脚本 `logs/_phase3_compare.py`。
  - 边界：本实验是 Phase 3 第一片（策略切换的动力学差异）。协议 §5 完整 Phase 3 还需"世界演化"语料比较存活记忆 vs 后期外部发展一致性——未做，列入待议。
- Phase 2 闭环（Reply）未接。

## 运行入口
- `uv run python run.py`（mock 交互）
- `uv run python tools/run_corpus.py corpus.txt`（真实语料）
- `uv run python tools/analyze_trajectory.py --log logs/events.jsonl --data data`（分析）

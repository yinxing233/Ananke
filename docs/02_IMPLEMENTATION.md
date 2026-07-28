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

---

## v0.2 实现状态（2026-07-22，协议 v4 草案 = MVP v0.2，**代码已完成、待冒烟校准**）

> 协议 v4 是**草案、未冻结**。本段记录代码已落地的事实；协议多处 `[待冒烟校准]`（R_RECALL、分类器甲/乙、"部分包含"计分、验证集锁定）仍待真实语料冒烟后填 §8 冻结条件。代码按"探索阶段允许校准"的纪律实现，开放参数给了合理初值。
>
> **2026-07-22 Fable5 审查后修正（四项漂移，均已在冒烟前完成）**：详见 `docs/03_RESEARCH_LOG.md`。简述：
> - **漂移1（最重，理论倒置）**：原 `conflict_trigger≥2 → 升 CORE` 是 v3「矛盾计为验证」EV 污染在第二道闸复活。改为 `conflict_trigger>0` = **CORE 晋升阻断器**（原则B：CORE 装经受住检验者，被矛盾=检验失败）。详见协议 §2.5。
> - **漂移2（更新能力）**：contradict 命中时新断言**写入快层 + 与受体建双向 conflict 链接**（系统须能更新世界状态），否则验证阶段命中率在含改口事实上系统性失真。mergeable 仍不写（冗余，留债）。
> - **漂移3（PI 追认）**：中→慢闸对两策略走同一逻辑，对分歧集 D 零贡献；**追认 D 仅测 working→consolidated 第一道闸**，写入 §6。
> - **漂移4（协议化）**：跨运行同一性判据「归一化内容比对」的规则（小写+去标点+折叠空白）成文入 §6，`tools/divergence_analysis._norm` 与之对齐。

### 架构变更（v3→v4）：余弦判定 → 召回-分类两段式
v3 死结（REORG 0.90 > DEDUP 0.80 使重组信号窗口为空集）由架构升级**自然解除**，方向三作废：
1. **召回（recall）**：新记忆 m 与既有 working+consolidated 记忆 e 余弦 ≥ `R_RECALL`(=0.65) 才进入下一步。
2. **分类（classification）**：关系分类器对 (m, e) 判 5 类：`duplicate / contradict / mergeable / related / unrelated`（协议 v4 §2.2）。
3. **信号映射（v4 §2.3，受体语义 recipient semantics）**：
   - duplicate → 跨 session 则 `external_validation +1`（且 `total_activation +1`）；同 session 仅去重；**不写**新记忆。
   - contradict → 受体 `conflict_trigger +1`；**写**新断言并与受体建**双向 conflict 链接**（漂移2 修正）；受体 `conflict_trigger>0` 即成为 CORE 晋升阻断器。
   - mergeable → 受体 `local_reorganization_trigger +1`；**不写**新记忆（信息多为冗余，留债）。
   - related → 受体 `internal_activation +1`；写新记忆（enrichment）。
   - unrelated → 写新记忆。
   - 写入规则：**不写 = duplicate（去重）+ mergeable（冗余）**；**写 = related / unrelated / contradict**。

### 中→慢闸（consolidated→core）：唯一晋升 = merge trigger，conflict = 阻断（v4 §2.5）
`migration.promote_consolidated_memories`：受体 `local_reorganization_trigger ≥ LOCAL_REORG_THRESHOLD(2)` → 升 CORE；`conflict_trigger > 0` → **冻结在中层**（`core_promotion_blocked` 事件），直到矛盾被裁决。core 晋升**与 --strategy 无关**（v4 分歧改在整体升层集 D 上测，且经 PI 追认 D 仅限第一道闸，见 §6）。

### 模块清单（ananke/，v0.2 新增/改动）
- **新增 `relation.py`**：`LLMRelationClassifier`（方案乙，复用 llm_client，`RELATION_CLASSIFIER_SCHEME=llm|nli`）+ `MockRelationClassifier`（确定性测试）。
- **改写 `pipeline.py`**：`process()` 走召回-分类；保留 working→consolidated 策略切换（`promotion_strategy` 槽）；新增 `relation_classifier` 注入 + `_link_conflict()`（双向矛盾链接）。
- **改写 `reorganization.py`**：`apply_relation_event(recipient, action)` 受体语义累加 trigger + 记 `local_reorganization`。
- **改写 `migration.py`**：`promote_consolidated_memories` 仅 merge trigger 晋升；conflict 阻断（记 `core_promotion_blocked`）。
- **`models.py`**：`MemoryEntry` 加 `session_id`（创建 session）、`conflict_trigger`、`conflict_links: List[str]`（双向矛盾链接）字段。
- **`config.py`**：加 `R_RECALL=0.65`、`RELATION_CLASSIFIER_SCHEME`、`EVAL_LLM_*`、`EVAL_PARTIAL_CREDIT=0.5`；`LOCAL_REORG_THRESHOLD=2`；**删除 `CONFLICT_TRIGGER_THRESHOLD`**（old 晋升逻辑，漂移1 已删）；v3 余弦阈值降为 legacy 仅审计。
- **`llm_client.py`**：加 `create_eval_llm_client()`（不同家族评判端）+ `MockEvaluationJudge`（子串匹配冒烟）。
- 其余（embedding / extraction / activation / memory_store / logger / promotion）沿用 v3。

### 事件日志类型（v4，全 10 类）
`memory_write` / `memory_dedup_skip` / `external_validation`(跨 session 计 EV) / `internal_activation`(frequency 改用 total_activation) / `local_reorganization`(受体语义，action=mergeable|contradict) / `working_eviction` / `working_to_consolidated` / `consolidated_to_core` / **`conflict_link`**(双向矛盾链接，漂移2) / **`core_promotion_blocked`**(被矛盾冻结，漂移1)。

### 工具（tools/）
- `dev_simulate.py`（v4 移植）：确定性 MockRelationClassifier + MockEmbedding + ScriptedExtractionLLM，全 10 类事件验证（含 conflict_link / core_promotion_blocked）；支持 `--strategy/--data/--log`。
- `run_corpus.py`：支持**会话感知语料**（.jsonl 含 `session_id`，或 .txt `# session: N` 标记）；`--strategy persistence|frequency` 对照。守反身性红线（只喂外部语料）。
- **新增 `evaluate.py`**（v4 §5）：独立家族 LLM 主裁判判定「记忆是否包含回答探针所需事实：包含/部分/不包含」，输出证据命中率 + `logs/eval_<tag>.json`。
- **新增 `divergence_analysis.py`**（v4 §6）：比对 persistence/frequency 两遍 CORE/CONSOLIDATED 升层集（**按归一化内容对齐**，非 id），算分歧集 D=(P∖F)∪(F∖P)、证据命中率 h_P/h_F、机制签名富集度；`|D|<20` 打印欠功效警告 + sweep 预案。只描述、不判定理论。

### 测试
- `tests/test_scenarios.py` 重写为 v4 语义：`uv run pytest` → **20 passed**（确定性 MockRelationClassifier + MockEmbedding + FakeExtractionLLM）。覆盖：跨/同 session 重复 EV、mergeable 受体 trigger、contradict 写入+双向链接+受体 conflict、related IA、unrelated 写入、dedup 跳过、working 双策略晋升、**core 仅 merge trigger 晋升 + conflict 阻断**、session 独立性、容量淘汰。

### 语料
- 新增 `corpus_phase2.jsonl`（6 session 结构化）+ `corpus_phase2_probes.jsonl`（5 探针），供后续真实 LLM 冒烟 + 评估。

### 两级缓存 + 确定性审计（2026-07-22~24 增补，Claude 三段结构执行件①）

> 为何要缓存：主测量量 D=(P\F)∪(F\P) 测"换策略后哪些记忆进巩固层"。若提取/分类非确定，噪声渗入 D，分不清"策略差"还是"LLM 抽风"。两级缓存让提取对所有运行一致、重叠句对分类一致 → D 退化为纯策略差测度。续跑=重跑：前 N 轮缓存命中零 API，第 N+1 轮起才新调用（附赠重放等价性测试）。

- **新增 `cache.py`（两级缓存 extraction/pairs）**：key = `(model_tag, prompt_hash, category, normalized_input)`，落盘 `cache/{extraction,pairs}.jsonl`（**与 data/ 平级**，红线：只增不删，`.gitignore` 已忽略）。`model_tag` 含 `provider|model`，换模型自动失效；`prompt_hash` = 实际发给 LLM 的 prompt 模板 SHA1 前 8 位；`normalized_input` 提取用 §6 归一化(输入)，分类用 `归一化(new)||归一化(existing)`。
- **新增 `text_norm.py`**：§6 归一化（小写+去标点+折叠空白）**唯一实现**；`cache.py` 与 `tools/divergence_analysis.py` 均 import 它（B1：消除 P0-A 三方矛盾病灶）。
- **`migrate_legacy_cache`（迁移 + key 重写，红线级）**：旧位置 `data/cache` → 平级 `cache/`（保住已付费 LLM 调用，如 253 轮 Qwen）。迁移同时把旧 key 的 version 段重写为当前 prompt 哈希段——旧 v0.2-draft 缓存 key 用 `"v1"`，B3 改哈希后若不重写，重放 1-253 轮会全部 miss → 重烧额度。重写安全（prompt 模板内容本轮未变、仅编码方式变）；8-hex 检测区分新旧、畸形/未知类原样保留。幂等（目标已有缓存则跳过）。
- **C1+C2（只缓存合法标签）**：提取/分类解析失败或空响应 = 基础设施故障（超时/429/连接断），**不落盘、重试、最终 raise**，绝不与 `"unrelated"` 折叠（unrelated 是唯一不发光信号类，每次折叠无声吞掉潜在 EV 或 contradict）。
- **D 内置**：`EventLogger` 加 `turn` 字段；`run_corpus` 标记轮序供重放推断原始轮数；`--clean` 红线拒绝清理缓存目录（指向缓存目录即 `exit(4)`）。
- **两个真实 bug 修复（排查中发现，非 Claude 原清单）**：
  1. **迁移 key 不兼容（红线级）**：见上 `migrate_legacy_cache` 重写——否则 253 轮已付费成果在重放下全 miss。
  2. **B2 防呆解析 bug**：`replay_equiv_test._cache_model_tag` 原用 `key.split("|",1)[0]` 取 model_tag，但 model_tag 含 `|`（如 `openai-compatible|deepseek-chat`）→ 截断后永不等真实 tag → 默认配置下合理重放被误 `exit(2)`。改为 key 固定末三段（hash/category/input 均不含 `|`）截断后拼回即完整 model_tag。
- **新增 `tools/export_annotation_pairs.py`**：从 `cache/pairs.jsonl` 分层导出 50 对标注模板（人工标注 + 方案甲/乙准确率拍板）。`model_tag` 含 `|` 的 key 用 `rpartition("||")`+`rsplit("|",2)` 还原两段记忆，避免 `|`/`||` 冲突错位。

### 待办（v4 冻结前）—— 更新
- [x] **两级缓存 + 确定性审计已完成**（cache.py / text_norm.py / migrate / 导出工具；Claude 三段结构 B1-B3 + C1/C2 + D 全落地；两个真实 bug 已修；全量 43 passed）。
- [ ] 真实 LLM 冒烟（**已解锁**：上述"先修"已完成，校准数据有效）：换额度续跑 254-419（253 轮已缓存、重放零 API），校准 `R_RECALL`、分类器甲/乙抉择、"部分包含"计分、锁定验证集。
- [ ] `replay_equiv_test` 等价性验证：前 253 轮缓存命中须与原始运行逐事件一致（fingerprint 忽略 `_id`/timestamp）。
- [ ] `RESEARCH_CONJECTURES.md` 升格（预登记→验证集承诺）。
- [ ] 填 v4 §8 冻结条件 → 协议 v4 冻结 → MVP v0.2 tag。
- 已知语义债（留 v0.3+）：① mergeable 命中不写新记忆（信息冗余，可接受）；② conflict 阻断后无裁决环节（矛盾如何"被解决"、被争议记忆何时解封），属 v0.3+ 设计；③ 归一化比对不处理改写容忍度（措辞不同的同事实判为两条分歧）。


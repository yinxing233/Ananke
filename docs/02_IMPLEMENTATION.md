# 02 · IMPLEMENTATION（当前实现 / 可频繁变更）

> 本文件记录**当前**实现状态，可能数天到数月全部更换，理论不受影响。
> 当前冻结历史协议见 `01_PROTOCOL_v3.md`；当前操作化草案见 `01_PROTOCOL_v4.md`，
> PI 已验收且已实现的裁决见 `DECISIONS_v0.2_freeze.md`；理论见 `00_THEORY.md`；
> 研究过程见 `03_RESEARCH_LOG.md`。

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
  - 两遍提取记忆集完全一致（各 21 条，交集 21），且 21<50 未触发淘汰；因此在该 v0.1
    小语料 pilot 中，观测分歧可归于当时的快→中策略切换。此历史条件不外推到 v4；
    v4 按 B4 明确比较完整选择制度。
  - 解读：External Selection 升层记忆全部 EV>0（受环境约束、稳定）；Internal Selection 把零外部验证、选择压力纯自循环的记忆也推上巩固层——协议 §5 预测的"退化为内部自循环、易被破坏的不稳定结构"。这是约束场理论在真实语义环境的 **Phase 3 先导实验（pilot）**——稳定性尚未测量（协议 §5 真比较器未执行，见 RELEASE 诚实边界）。日志 `logs/phase3_persist.jsonl`+`data/phase3_persist` / `logs/phase3_freq.jsonl`+`data/phase3_freq`；报告 `logs/phase3_persist_report.html` / `logs/phase3_freq_report.html`；对比脚本 `logs/_phase3_compare.py`。
  - 边界：本实验是 Phase 3 第一片（策略切换的动力学差异）。协议 §5 完整 Phase 3 还需"世界演化"语料比较存活记忆 vs 后期外部发展一致性——未做，列入待议。
- Phase 2 闭环（Reply）未接。

## 运行入口
- `uv run python run.py`（mock 交互）
- `uv run python tools/run_corpus.py corpus.txt`（真实语料）
- `uv run python tools/analyze_trajectory.py --log logs/events.jsonl --data data`（分析）

---

## v0.2 实现状态（2026-08-08：**路径 A 运行保护已实现，90 项测试通过；协议仍未冻结**）

> 协议 v4 是**草案、未冻结**。2026-07-28 形成的
> [`DECISIONS_v0.2_freeze.md`](./DECISIONS_v0.2_freeze.md) 已于 2026-07-30 获 PI 验收，
> 其实现已按 A3 → A1/B6 → A2/B7 → A4/A5/B2 → B1 → B3 完成。pre-audit Python 保存在
> `05205a9`，当时基线为 **43 passed**；B1–B7 完成时为 **70 passed**，2026-08-02 来源上下文保真修复后为 **73 passed**；2026-08-08 路径 A 运行保护完成后为 **90 passed**。以下原阻断项均已闭合：
>
> 1. 轮级状态与状态事件采用事务提交；失败回滚并保留失败审计；
> 2. `evaluate.py` 使用 question + reference fact，标签互斥，失败剔除并执行 5% 上限；
> 3. 未知分类 token 重试三次后硬失败，不缓存、不降级 unrelated；
> 4. run_corpus 贯通 `session_id/dia_id/speaker`，事件使用 `input_*`，记忆使用 `source_*`；
> 5. EV 按 distinct session 去重，Frequency 的逐次激活语义保持不变；
> 6. CORE 进入三层 top-1 召回并具备四关系守护，计数不驱动 v0.2 决策；
> 7. `system_guided` 仍只是未启用接口，正式 runner 中恒为 False。
> 8. LoCoMo 的 `speaker` 与 `session_<n>_date_time` 已贯通到提取 prompt、缓存键、记忆来源元数据与事件上下文；适配器缺任一可用字段时 fail closed，避免跨人物/跨日期缓存复用制造假 duplicate/EV。
>
> **2026-07-22 Fable5 审查后修正（四项漂移，均已在冒烟前完成）**：详见 `docs/03_RESEARCH_LOG.md`。简述：
> - **漂移1（最重，理论倒置）**：原 `conflict_trigger≥2 → 升 CORE` 是 v3「矛盾计为验证」EV 污染在第二道闸复活。改为 `conflict_trigger>0` = **CORE 晋升阻断器**（原则B：CORE 装经受住检验者，被矛盾=检验失败）。详见协议 §2.5。
> - **漂移2（更新能力）**：contradict 命中时新断言**写入快层 + 与受体建双向 conflict 链接**（系统须能更新世界状态），否则验证阶段命中率在含改口事实上系统性失真。mergeable 仍不写（冗余，留债）。
> - **漂移3（PI 追认）**：中→慢闸对两策略走同一逻辑，对分歧集 D 零贡献；**追认 D 仅测 working→consolidated 第一道闸**，写入 §6。
> - **漂移4（协议化）**：跨运行同一性判据「归一化内容比对」的规则（小写+去标点+折叠空白）成文入 §6，`tools/divergence_analysis._norm` 与之对齐。

### 架构变更（v3→v4）：余弦判定 → 召回-分类两段式
v3 死结（REORG 0.90 > DEDUP 0.80 使重组信号窗口为空集）由架构升级**自然解除**，方向三作废：
1. **当前召回（recall）**：新记忆 m 与既有 working+consolidated+core 记忆 e 余弦 ≥
   `R_RECALL`(=0.65) 才进入下一步；同分按 `CORE > CONSOLIDATED > WORKING`。
2. **分类（classification）**：关系分类器对 (m, e) 判 5 类：`duplicate / contradict / mergeable / related / unrelated`（协议 v4 §2.2）。
3. **信号映射（v4 §2.3，受体语义 recipient semantics）**：
   - duplicate → 每个非 guided 的后续 distinct session 首次命中才 `external_validation +1`；
     同一后续 session 的后续命中只增加 Frequency 的 `total_activation`；创建 session 仅去重；
     **不写**新记忆。
   - contradict → 受体 `conflict_trigger +1`；**写**新断言并与受体建**双向 conflict 链接**（漂移2 修正）；受体 `conflict_trigger>0` 即成为 CORE 晋升阻断器。
   - mergeable → 受体 `local_reorganization_trigger +1`；**不写**新记忆（信息多为冗余，留债）。
   - related → 受体 `internal_activation +1`；写新记忆（enrichment）。
   - unrelated → 写新记忆。
   - 写入规则：**不写 = duplicate（去重）+ mergeable（冗余）**；**写 = related / unrelated / contradict**。

### 中→慢闸（consolidated→core）：唯一晋升 = merge trigger，conflict = 阻断（v4 §2.5）
`migration.promote_consolidated_memories`：受体 `local_reorganization_trigger ≥ LOCAL_REORG_THRESHOLD(2)` → 升 CORE；`conflict_trigger > 0` → **冻结在中层**（`core_promotion_blocked` 事件），直到矛盾被裁决。core 晋升**与 --strategy 无关**（v4 分歧改在整体升层集 D 上测，且经 PI 追认 D 仅限第一道闸，见 §6）。

### 模块清单（ananke/，v0.2 新增/改动）
- **新增 `relation.py`**：`LLMRelationClassifier`（路径 A 固定方案乙，复用 llm_client）+ `MockRelationClassifier`（确定性测试）；关系输出上限 6 tokens，只有解析失败走 B7 三次重试。
- **改写 `pipeline.py`**：`process()` 走召回-分类；保留 working→consolidated 策略切换（`promotion_strategy` 槽）；新增 `relation_classifier` 注入 + `_link_conflict()`（双向矛盾链接）；top-1 后的 normalized exact pair 走确定性 duplicate 并记录来源。
- **改写 `reorganization.py`**：`apply_relation_event(recipient, action)` 受体语义累加 trigger + 记 `local_reorganization`。
- **改写 `migration.py`**：`promote_consolidated_memories` 仅 merge trigger 晋升；conflict 阻断（记 `core_promotion_blocked`）。
- **`models.py`**：`MemoryEntry` 使用
  `source_session_id/source_dia_id/source_speaker` 保存创建来源，并持久化
  `source_session_datetime`、`ev_contributing_session_ids`、`conflict_trigger`、`conflict_links`。
- **`config.py`**：加 `R_RECALL=0.65`、`EVAL_LLM_*`、模型 family 与评判端 RPM；B6 的 0.5 不再是环境变量；`LOCAL_REORG_THRESHOLD=2`；**删除 `CONFLICT_TRIGGER_THRESHOLD`**（old 晋升逻辑，漂移1 已删）；v3 余弦阈值降为 legacy 仅审计。
- **`llm_client.py`**：加 `create_eval_llm_client()`（不同家族评判端）+ `MockEvaluationJudge`（子串匹配冒烟）；正式 judge 对未知/同家族 fail closed；关闭 SDK 隐式重试，使每次真实 HTTP 尝试都经过可见计量并写 usage JSONL。
- **新增 `usage.py`**：区分逻辑 LLM 调用与真实 HTTP 尝试，逐次记录成功、429、其它错误、操作类型、耗时及 provider token usage；不推测价格。
- **新增 `cache.py` / `text_norm.py`**：两级缓存（extraction/pairs）+ §6 归一化唯一实现，见下方「两级缓存」节。
- 其余沿用 v3：embedding / extraction / memory_store / logger / promotion。
  **注**：`activation.py` 为 v3 遗留模块，v4 召回-分类管线不再调用 `detect_activations`（信号由 pipeline 的 `_handle_relation` 直接按分类结果登记），保留仅供历史参考，勿再接入。

### 事件日志
状态事件包括 `memory_write` / `memory_dedup_skip` / `external_validation` /
`internal_activation` / `local_reorganization` / `working_eviction` /
`working_to_consolidated` / `consolidated_to_core` / `conflict_link` /
`core_promotion_blocked` / `rule_based_duplicate`；失败审计另含 `classification_unparsed` 与 `turn_failed`。
每个轮内事件均带 `input_session_id/input_dia_id/input_speaker/system_guided`。

### 工具（tools/）
- `dev_simulate.py`（v4 移植）：确定性 MockRelationClassifier + MockEmbedding +
  ScriptedExtractionLLM，覆盖核心状态事件（含 conflict_link / core_promotion_blocked /
  consolidated_to_core / rule_based_duplicate）；支持 `--strategy/--data/--log`。
  **2026-08-08 修复**：exact-dup 短路规则引入后 script 队列曾错位导致演示链断裂
  （consolidated_to_core / conflict_link / core_promotion_blocked 缺失），已按实际
  分类器调用序重建 script 并在 main() 末尾加守护断言（缺失任一关键事件即非零退出）。
- `run_corpus.py`：支持**会话感知语料**（.jsonl 含 `session_id`，或 .txt `# session: N` 标记）；`--strategy persistence|frequency` 对照。守反身性红线（只喂外部语料）。新增只读 `--preflight`（不构造客户端、不触发 API）与 `--formal`（禁止缓存绕过、要求真实模型/密钥/temperature=0/显式策略、独占共享缓存）；请求计量文件默认从事件日志名派生。
  成功结束时把 cache hit/miss 与 API 汇总共同写入持久 `run_metrics` 审计事件。
- **新增 `evaluate.py`**（v4 §5）：独立家族 LLM 对 question + reference_fact 做
  reference-grounded 判定；互斥标签、缺 reference fact 拒绝、失败剔除与 5% 上限均已闭合，
  “部分”固定 0.5、输出上限 6 tokens，并记录独立 usage JSONL。
- **新增 `divergence_analysis.py`**（v4 §6）：比对 persistence/frequency 两遍 CORE/CONSOLIDATED 升层集（**按归一化内容对齐**，非 id），算分歧集 D=(P∖F)∪(F∖P)、证据命中率 h_P/h_F、机制签名富集度；`|D|<20` 打印欠功效警告 + sweep 预案。只描述、不判定理论。

### 测试
- 2026-07-28 pre-audit 基线：`uv run pytest` → **43 passed**。
- 2026-07-30 B1–B7 实现后：`uv run pytest -q` → **70 passed**；2026-08-02 来源上下文
  保真修复后 → **73 passed**。覆盖评估契约、轮级原子性、分类硬失败、distinct-session EV、
  来源元数据贯通与上下文缓存隔离、CORE 三层召回与四关系处置。
- 2026-08-08 路径 A 保护批次后：`python -m pytest -q` → **90 passed**。新增覆盖请求/token
  计量、429 逐请求计数、preflight 估算、正式模式拒绝危险配置、P/F 串行锁、family 分离、
  6-token 上限、B7 异常效力域与 exact duplicate 短路审计。
- `uv run python -m compileall -q ananke tools tests` → 通过。

### 语料
- 新增 `corpus_phase2.jsonl`（6 session 结构化）+ `corpus_phase2_probes.jsonl`（5 探针），供后续真实 LLM 冒烟 + 评估。

### 两级缓存 + 确定性审计（2026-07-22~24 增补，Claude 三段结构执行件①）

> 为何要缓存：主测量量 D=(P\F)∪(F\P) 测"换策略后哪些记忆进巩固层"。若提取/分类非确定，
> 噪声会渗入 D。两级缓存代码的目标是让提取与重叠分类对可确定性重放。**当前运行时
> `cache/` 与 `data/cache/` 均不存在，旧 253 轮没有可用缓存，不能免费重放。**

- **新增 `cache.py`（两级缓存 extraction/pairs）**：key = `(model_tag, prompt_hash, category, normalized_input)`，落盘 `cache/{extraction,pairs}.jsonl`（**与 data/ 平级**，红线：只增不删，`.gitignore` 已忽略）。`model_tag` 含 `provider|model`，换模型自动失效；`prompt_hash` = 实际发给 LLM 的 prompt 模板 SHA1 前 8 位；`normalized_input` 提取用 §6 归一化(输入)，分类用 `归一化(new)||归一化(existing)`。
- **新增 `text_norm.py`**：§6 归一化（小写+去标点+折叠空白）**唯一实现**；`cache.py` 与 `tools/divergence_analysis.py` 均 import 它（B1：消除 P0-A 三方矛盾病灶）。
- **`migrate_legacy_cache`（迁移 + key 重写，红线级）**：若旧位置 `data/cache` 存在，则迁移到
  平级 `cache/` 并重写旧 version 段。此能力用于保护未来/外部留存的已付费调用；当前工作区没有
  可迁移的旧缓存，不能据此声称 253 轮可重放。
- **C1+C2（只缓存合法标签）**：提取/分类解析失败或空响应 = 基础设施故障（超时/429/连接断），**不落盘、重试、最终 raise**，绝不与 `"unrelated"` 折叠（unrelated 是唯一不发光信号类，每次折叠无声吞掉潜在 EV 或 contradict）。
- **D 内置**：`EventLogger` 加 `turn` 字段；`run_corpus` 标记轮序供重放推断原始轮数；`--clean` 红线拒绝清理缓存目录（指向缓存目录即 `exit(4)`）。
- **两个真实 bug 修复（排查中发现，非 Claude 原清单）**：
  1. **迁移 key 不兼容（红线级）**：见上 `migrate_legacy_cache` 重写——否则 253 轮已付费成果在重放下全 miss。
  2. **B2 防呆解析 bug**：`replay_equiv_test._cache_model_tag` 原用 `key.split("|",1)[0]` 取 model_tag，但 model_tag 含 `|`（如 `openai-compatible|deepseek-chat`）→ 截断后永不等真实 tag → 默认配置下合理重放被误 `exit(2)`。改为 key 固定末三段（hash/category/input 均不含 `|`）截断后拼回即完整 model_tag。
- **新增 `tools/export_annotation_pairs.py`**：从 `cache/pairs.jsonl` 分层导出 50 对标注模板，用于独立验收路径 A 的 LLM 分类准确率与 contradict 召回。`model_tag` 含 `|` 的 key 用 `rpartition("||")`+`rsplit("|",2)` 还原两段记忆，避免 `|`/`||` 冲突错位。

### 路径 A：付费校准前停止点（2026-08-08）

- PI 选择付费、简单仪器路线；本批次未实现批量提取、本地 NLI、RPD 账本或真正检查点。
- 已从已暴露的 `conv-26` 固定前 100 轮探索子集：
  `data/locomo/conv-26_calibration_100.jsonl`（运行数据被 `.gitignore` 排除，不接触其余验证候选）。
  已逐行确认等于完整语料前 100 行；SHA256 =
  `E3ACF574E06A375117A7C026792909EC1EC05FED0117F4330E7C7BC98A240A98`。
- 只读 preflight 已通过正式保护条件：100 轮、6 sessions、100 个唯一提取 key、0 cache hit，
  即 100 个 cache miss、**至少 100 次逻辑提取调用**；实际 HTTP 数还会受提取解析与 429 重试影响，
  必须实测。miss 提示总计 110,695 字符，粗略约 27,674–36,899 input tokens。
  分类调用数因提取结果与状态演化而保持 `unknown`，须由真实校准实测。
- 同一预检对完整 `conv-26` 报告：419 轮、19 sessions、419 个唯一提取 key、0 hit（至少 419 次逻辑提取调用）、
  462,301 提示字符，粗略约 115,576–154,101 input tokens；分类调用仍未知。
- 当前预检配置满足：真实驱动端、缓存开启、密钥已配置、temperature=0。预检前后均无 `cache/`
  目录、无 `*llm_usage*.jsonl`，证明本步骤没有创建客户端或发出真实 API 请求。
  本次读取的 model tag 为 `openai-compatible|qwen3.6-27b`；它须经真实校准后才可冻结。
- 下一步命令、产物与成本换算见 [`CALIBRATION_PATH_A.md`](./CALIBRATION_PATH_A.md)；本轮在该命令前停止。

### 待办（v4 冻结前）—— 2026-07-28 审计更新
- [x] 两级缓存、归一化、导出与重放**源码**已纳入版本控制；43/43 基线通过。
- [x] PI 已于 2026-07-30 验收 `DECISIONS_v0.2_freeze.md`。
- [x] 按 A3 → A1/B6 → A2/B7 → A4/A5/B2 → B1 → B3 顺序 Red → Green 实现；当时 70/70 通过，来源上下文保真修复后 73/73、路径 A 保护后 90/90 通过。
- [ ] 修复后从第 1 轮重跑探索语料；旧 253 轮状态与日志只作探索审计，不续跑。
- [ ] 新运行产生缓存后验证确定性重放；不得声称不存在的旧缓存可命中。
- [x] 路径 A 将关系分类仪器固定为 LLM 五选一，不接入本地 NLI；部分计分已由 B6 定为 0.5。
- [ ] 用真实 100 轮校准 `R_RECALL`、LLM 分类器可靠性/成本，并完成独立的 50 对人工锚点。
- [ ] 锁定验证集，并新建一次性 `PREREGISTRATION.md`。
- [ ] 填 v4 §8 冻结条件 → 协议 v4 冻结 → MVP v0.2 tag。
- 已知语义债（留 v0.3+）：① mergeable 命中不写新记忆（信息冗余，可接受）；② conflict 阻断后无裁决环节（矛盾如何"被解决"、被争议记忆何时解封），属 v0.3+ 设计；③ 归一化比对不处理改写容忍度（措辞不同的同事实判为两条分歧）。

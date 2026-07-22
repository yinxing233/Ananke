# Ananke 版本计划（plan/）

> 本目录是 v0.1 冻结（git tag `v0.1`）之后的**后续版本路线**，不是权威规范。
> 权威层：理论 [`../docs/00_THEORY.md`](../docs/00_THEORY.md) → 协议 [`../docs/01_PROTOCOL_v4.md`](../docs/01_PROTOCOL_v4.md)（**草案，未冻结**）→ 实现 [`../docs/02_IMPLEMENTATION.md`](../docs/02_IMPLEMENTATION.md)。
> 协议 v3 已被 v4 取代但保留供审计（[`../docs/01_PROTOCOL_v3.md`](../docs/01_PROTOCOL_v3.md)）。
> 凡涉及"操作定义/判定函数/证据来源"变更的，按原则 C 必须升协议版本，不得静默改冻结文件。

---

## 0. 起点（v0.1 已冻结的事实）

| 迁移闸                        | 代码                                                                                                           | 真实 LLM 下触发            | 策略可切换                         | persistence vs frequency 差异可观测 |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------- | ---------------------------------- | ----------------------------------- |
| 快→中（working→consolidated） | [`ananke/promotion.py`](../ananke/promotion.py) + [`ananke/migration.py:35`](../ananke/migration.py)           | ✅（persist 1× / freq 4×） | ✅（`WORKING_PROMOTION_STRATEGY`） | ✅ Phase 3 pilot 已示分歧           |
| 中→慢（consolidated→core）    | [`ananke/migration.py:58`](../ananke/migration.py) + [`ananke/reorganization.py`](../ananke/reorganization.py) | ❌ 从未触发                | ❌ 两策略共用同一规则              | ❌ 不可能观测                       |

**用户判断属实**：快→中已实现并可观测差异；中→慢代码在但从未真实触发，且不可策略切换。

> **v0.2（协议 v4）的路线变更**：v0.1 后的下一步原计划是"让中→慢可切换 + 解死结"（见 [`v0.2_consolidated_to_core.md`](./v0.2_consolidated_to_core.md)，**已废弃**）。
> 协议 v4 采取了**不同的战略**：用"召回-分类两段式"关系分类器取代余弦阈值判信号，使 v3 死结由架构自然解除（§2.4），方向三不再需要；同时把 LoCoMo session 语义、分歧集统计、评估独立性、预登记纳入本版，把 persistence/frequency 对照从"机制分歧 pilot"升级为"分歧集 evidence 命中率"的严谨比较。
> **中→慢双策略切换未予采用**——分歧改由分歧集 D = (P\F) ∪ (F\P) 在整体升层集合上测量（v4 §6），而非靠切换第二道闸的规则。

---

## 1. 核心问题与路线逻辑

约束场理论的核心命题是"长期稳定结构依赖不可控外部输入的持续检验（External Selection），而非系统内部自循环（Internal Selection）"。本项目检验的工程推论 C2："存续驱动迁移优于频率驱动"（主张层级链见 [v4 §1](../docs/01_PROTOCOL_v4.md)）。

路线（v4 后更新）按"先严谨化对照 → 再闭环检验原则B → 再消偏/补语料"展开：

| 版本      | 主题                                                                  | 解决什么                                                                                                      | 依赖          |
| --------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------- |
| **v0.2**（协议 v4 草案）  | 召回-分类两段式 + LoCoMo session 语义 + 分歧集统计 + 评估独立性 + 预登记 | 用关系分类器取代余弦阈值，自然解除 v3 死结与 EV 污染；persistence/frequency 对照升级为分歧集 evidence 命中率比较（v4 §6） | 协议 v4 冻结（§8） |
| **v0.3**  | 闭环 / 世界演化（原则B 闭环检验）                                     | v4 §3.3 明确 deferred：系统自身行为是否污染输入流（闭环情形的原则B）                                          | v0.2          |
| **v0.4**  | 中文嵌入标定 + 多基准（LongMemEval-S）                                | v4 已纳入 LoCoMo + sweep；剩余中文阈值标定与多基准留此                                                        | v0.2          |
| **v0.5+** | 反事实重要性 / 被动衰减 / Reply 闭环 / Memory Identity 协议化         | 理论完整版与闭环                                                                                              | 各自独立      |

---

## 2. 各版本文件索引

- [`v0.2_recall_classification.md`](./v0.2_recall_classification.md) — **当前 v0.2**：协议 v4 的 plan 层视图（召回-分类两段式 + 分歧集）
- [`v0.2_consolidated_to_core.md`](./v0.2_consolidated_to_core.md) — [已废弃] 旧 v0.2 方案（方向三解死结 + 中→慢双策略切换），被协议 v4 取代，保留供审计
- [`v0.3_world_evolution_phase3.md`](./v0.3_world_evolution_phase3.md) — 闭环 / 世界演化（v4 §3.3 deferred 的 v0.3 方向）
- [`v0.4_external_corpus_and_sweep.md`](./v0.4_external_corpus_and_sweep.md) — 剩余：中文标定 + 多基准（LoCoMo/sweep 已并入 v0.2）
- [`v0.5_long_term.md`](./v0.5_long_term.md) — 反事实重要性 / 衰减 / Reply 闭环 / Memory Identity

---

## 3. 跨版本纪律（防漂移）

1. **每个版本先问"提高系统能力 or 提高理论可验证性"**——只做后者。检索增强回复、合并真整合、可视化打磨等归"能力"，挂起。
2. **改协议 = 升 vN**，不静默改冻结文件；v3 保留供审计。
3. **反身性红线不动**：EV 永不接纳系统自生成/诱导内容。
4. **诚实边界先行**：每版结论先写"证明了什么 / 没证明什么"，再写数字。
5. **探索/验证两阶段分离（v4 §7）**：探索阶段（冒烟、调参）的数字标注"探索性"不进结论；冻结后验证集须用冒烟未接触的对话，数据隔离为硬约束。
6. **预登记（[`../docs/RESEARCH_CONJECTURES.md`](../docs/RESEARCH_CONJECTURES.md)）**：协议冻结时推测升格为预测承诺，此后不得修改，只可追加验证结果；反驳时如实报告、不回改管线。
7. **主张层级不越级（v4 §1）**：预测成立 → C2 获支持 → "与原则B一致"（非验证）→ 对理论本身无断言。任何文档/叙事不得越级。

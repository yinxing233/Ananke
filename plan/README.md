# Ananke 版本计划（plan/）

> 本目录是 v0.1 冻结（git tag `v0.1`）之后的**后续版本路线**，不是权威规范。
> 权威层不变：理论 [`../docs/00_THEORY.md`](../docs/00_THEORY.md) → 协议 [`../docs/01_PROTOCOL_v3.md`](../docs/01_PROTOCOL_v3.md) → 实现 [`../docs/02_IMPLEMENTATION.md`](../docs/02_IMPLEMENTATION.md)。
> 凡涉及"操作定义/判定函数/证据来源"变更的，按原则 C 必须升协议版本（v3 → v4…），不得静默改冻结文件。

---

## 0. 起点（v0.1 已冻结的事实）

| 迁移闸                        | 代码                                                                                                           | 真实 LLM 下触发            | 策略可切换                         | persistence vs frequency 差异可观测 |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------- | ---------------------------------- | ----------------------------------- |
| 快→中（working→consolidated） | [`ananke/promotion.py`](../ananke/promotion.py) + [`ananke/migration.py:35`](../ananke/migration.py)           | ✅（persist 1× / freq 4×） | ✅（`WORKING_PROMOTION_STRATEGY`） | ✅ Phase 3 pilot 已示分歧           |
| 中→慢（consolidated→core）    | [`ananke/migration.py:58`](../ananke/migration.py) + [`ananke/reorganization.py`](../ananke/reorganization.py) | ❌ 从未触发                | ❌ 两策略共用同一规则              | ❌ 不可能观测                       |

**用户判断属实**：快→中已实现并可观测差异；中→慢代码在但从未真实触发，且**不可策略切换**——这是当前 persistence vs frequency 对照实验只能停在"第一道闸"的结构性原因。

---

## 1. 核心问题与路线逻辑

约束场理论的核心命题是"长期稳定结构依赖不可控外部输入的持续检验（External Selection），而非系统内部自循环（Internal Selection）"。**最稳定的结构 = 慢层（core）**。因此 persistence vs frequency 的差异，理论上**最应该在中→慢这道闸上显现**——而当前恰恰在这道闸上既不可观测、又不可切换。

路线按"先让第二道闸可切换且能触发 → 再用世界演化语料测量稳定性 → 再换外部语料消偏"的顺序展开：

| 版本      | 主题                                                                  | 解决什么                                                                                                      | 依赖      |
| --------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------- |
| **v0.2**  | 中→慢双策略可切换 + 真实触发 + 解 reorg/dedup 死结                    | 让 persistence/frequency 的差异在第二道闸上可观测；须先解开 `REORG(0.90) > DEDUP(0.80)` 使 reorg 触发窗口非空 | 协议升 v4 |
| **v0.3**  | 世界演化语料 + 稳定性/扰动检验                                        | 完整 Phase 3 真比较器（协议 §5）：测"稳定 vs 易被破坏"，而非"谁被升层"                                        | v0.2      |
| **v0.4**  | 外部语料 LoCoMo + 阈值动态 sweep + 中文标定                           | 消除手工语料构造偏误；动态重跑验证阈值稳健性                                                                  | v0.3      |
| **v0.5+** | 反事实重要性 / 被动衰减 / Phase 2 Reply 闭环 / Memory Identity 协议化 | 理论完整版与闭环                                                                                              | 各自独立  |

---

## 2. 各版本文件索引

- [`v0.2_consolidated_to_core.md`](./v0.2_consolidated_to_core.md) — 中→慢双策略可切换 + 真实触发（**直接回应"如何观察 persistence vs frequency 区别"**）
- [`v0.3_world_evolution_phase3.md`](./v0.3_world_evolution_phase3.md) — 世界演化语料 + 稳定性测量（完整 Phase 3 真比较器）
- [`v0.4_external_corpus_and_sweep.md`](./v0.4_external_corpus_and_sweep.md) — LoCoMo 接入 + 阈值动态 sweep + 中文标定
- [`v0.5_long_term.md`](./v0.5_long_term.md) — 反事实重要性 / 衰减 / Reply 闭环 / Memory Identity

---

## 3. 跨版本纪律（防漂移）

1. **每个版本先问"提高系统能力 or 提高理论可验证性"**——只做后者。检索增强回复、合并真整合、可视化打磨等归"能力"，挂起。
2. **改协议 = 升 vN**，不静默改冻结文件；v3 保留供审计。
3. **反身性红线不动**：EV 永不接纳系统自生成/诱导内容；世界演化语料的外部输入仍须"实验者未控制"。
4. **诚实边界先行**：每版结论先写"证明了什么 / 没证明什么"，再写数字。
5. **n≥1、单语料、零统计推断**是 v0.1 已知边界；v0.3/v0.4 才开始补统计与多语料。

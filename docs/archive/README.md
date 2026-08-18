# docs/archive/ — 历史文档归档区（按版本轮次分类）

> **用途**：收留"在当时正确、现已被取代"的**历史参考文档**（协议早期版本、各轮实验报告/发布说明、过期 memo）。
> 归档 = **移走 + 保留**（不是删除）。这些文件是研究仪器的演进轨迹，对复盘实验轮次仍有价值。
>
> **纪律**：
> - 只收"历史参考"类文档。**当前活跃文档若只是滞后，应更新而非归档**（见下"为何 v3 / Memory_Architecture 未归档"）。
> - 归档用 `git mv`，历史可追溯。
> - 本索引是归档文件的**规范导航**，优先看这里；活跃文档中的历史脉络引用按本索引定位。
>
> **相邻目录**：短生命周期操作类备忘（待决策 / 协作约定 / 临时指引）不归本目录，
> 见 [`../memos/`](../memos/README.md)（决策完成后的 memo 移入本目录**当前轮次**子目录归档）。

## 分类规则（2026-08-08 立，防归档区扁平膨胀）

> **按"版本轮次"分类，不按"文档类型"**。理由：
> 1. archive 的核心读者是"复盘一轮实验的人"，查询单位是轮次（tag v0.1 / v0.2…）——
>    审计某轮时最想要"该轮全部文档在一处"；按类型分（protocols/ reports/ releases/）
>    会把一轮实验拆散到多个目录。
> 2. 类型信息已在文件名中（`01_PROTOCOL_` / `EXPERIMENT_` / `RELEASE_` / `memo_`），
>    无需再建类型目录重复表达。
> 3. 轮次目录与项目"每轮实验 = 升 vN"的结构同构，是删不掉的不可约关系。

```
docs/archive/
├── README.md     ← 本索引
├── v0.1/         ← 2026-07-14 冻结轮次（tag v0.1）
└── v0.2/         ← 2026-08-18 启用：过期操作文档归档
```

- 新增归档文件时：判断它属于哪一轮实验（协议升版 / 冻结 / 决策完成的时间点），移入对应 `vN/` 子目录。
- 轮次子目录内不再细分类型（文件名前缀已区分）。
- 删除归档 = 禁止（演进轨迹）。清理只发生在"文档体检"时合并重复项，不移除。

## 归档文件清单

### v0.2/（2026-08-18 启用，探索点火轮次）

| 文件 | 原日期 | 为何归档 | 被谁取代 |
|---|---|---|---|
| `v0.2/CALIBRATION_PATH_A.md` | 2026-08-08 | 100 轮校准手册；校准与完整 419 轮点火均已完成后达到过期触发点 | 运行事实见 `02_IMPLEMENTATION.md` / `IGNITION_RECEIPT_v0.2.md` |
| `v0.2/2026-08-08_calibration_decision_memo.md` | 2026-08-08 | 校准前"三出口预案"决策备忘；决策已闭合 | `DECISIONS_v0.2_freeze.md` §13/§14 |

### v0.1/（2026-07-14 冻结轮次）

| 文件 | 原日期 | 为何归档 | 被谁取代 |
|---|---|---|---|
| `v0.1/01_PROTOCOL_v1.md` | 2026-07-13 | 协议最早草稿（EV/IA 重叠定义），被 v2 升版取代 | `01_PROTOCOL_v3.md`（冻结）/ `01_PROTOCOL_v4.md`（草案） |
| `v0.1/01_PROTOCOL_v2.md` | 2026-07-14 | EV/IA 改互斥，被 v3 阈值校准取代 | 同上 |
| `v0.1/EXPERIMENT_REPORT.md` | 2026-07-14 | v0.1 实验报告（阈值敏感性相图等），属已发布轮次记录 | v0.2 实现见 `02_IMPLEMENTATION.md`；新实验将产生新报告 |
| `v0.1/RELEASE_v0.1.md` | 2026-07-14 | v0.1 发布说明，历史产物 | v0.2 发布前不产生新 RELEASE |

## 为何以下几类**未**归入本目录

- **`01_PROTOCOL_v3.md`（v0.1 冻结协议）**：仍被 8 个活跃文档引用（`00_THEORY`、`01_PROTOCOL_v4`、`02_IMPLEMENTATION`、`03_RESEARCH_LOG`、`Memory_Architecture`、`plan/README`、`plan/v0.2_consolidated_to_core`、`plan/v0.5_long_term` 等）。它是活跃系统的引用锚点，归档会断链。留在 `docs/` 作为冻结参考；**v4 冻结后**再归档至 `v0.1/`。
- **`Memory_Architecture_设计文档_MVP.md`**：被 `plan/v0.2_handoff_brief`、`v0.4`、`v0.5` 引用。虽是 Jul 14 早期设计、早于协议系列，但活跃计划文档仍指向它。暂留 `docs/`；若日后归档需同步改这 3 处引用。
- **`00_THEORY.md`**：最稳的公理层（几年不变），0 提及 v4 是正确的。留活跃区。
- **`02_IMPLEMENTATION.md` / `03_RESEARCH_LOG.md`**：本应随代码生长。属"活文档"——持续更新到当前状态，不归档。

## 活跃文档中对归档文件的残留引用

以下活跃文档仍文字提及归档文件（多为历史脉络引用，非当前操作指引）：
- `03_RESEARCH_LOG.md` → 提及 `01_PROTOCOL_v1`（v1/v2 演进脉络）、`EXPERIMENT_REPORT`（相图出处）。
- `plan/v0.3_world_evolution_phase3.md`、`plan/v0.4_external_corpus_and_sweep.md` → 提及 `EXPERIMENT_REPORT`、`RELEASE_v0.1`。
- `plan/v0.2_consolidated_to_core.md` → 提及 `RELEASE_v0.1`。
- `plan/v0.5_long_term.md` → 提及 `RELEASE_v0.1`、`Memory_Architecture`（后者未归档）。

阅读这些引用时，按本索引定位到 `docs/archive/v0.1/` 对应文件即可。

# docs/archive/ — 落后文档归档区

> **用途**：收留"在当时正确、现已被取代"的**历史参考文档**（协议早期版本、v0.1 实验报告/发布说明、早期 MVP 设计）。
> 归档 = **移走 + 保留**（不是删除）。这些文件是研究仪器的演进轨迹，对复盘实验轮次仍有价值。
>
> **纪律**：
> - 只收"历史参考"类文档。**当前活跃文档若只是滞后，应更新而非归档**（见下"为何 v3 / Memory_Architecture 未归档"）。
> - 归档用 `git mv`，历史可追溯。
> - 活跃文档若仍用相对路径引用本目录下文件，链接会指向 `docs/archive/<file>`——这是预期行为；本索引是归档文件的**规范导航**，优先看这里。

## 归档文件清单

| 文件 | 原日期 | 为何归档 | 被谁取代 |
|---|---|---|---|
| `01_PROTOCOL_v1.md` | 2026-07-13 | 协议最早草稿（EV/IA 重叠定义），被 v2 升版取代 | `01_PROTOCOL_v3.md`（冻结）/ `01_PROTOCOL_v4.md`（草案） |
| `01_PROTOCOL_v2.md` | 2026-07-14 | EV/IA 改互斥，被 v3 阈值校准取代 | 同上 |
| `EXPERIMENT_REPORT.md` | 2026-07-14 | v0.1 实验报告（阈值敏感性相图等），属已发布轮次记录 | v0.2 实现见 `02_IMPLEMENTATION.md`；新实验将产生新报告 |
| `RELEASE_v0.1.md` | 2026-07-14 | v0.1 发布说明，历史产物 | v0.2 发布前不产生新 RELEASE |

## 为何以下几类**未**归入本目录

- **`01_PROTOCOL_v3.md`（v0.1 冻结协议）**：被 **11 个活跃文档**引用（`00_THEORY`、`01_PROTOCOL_v4`、`02_IMPLEMENTATION`、`03_RESEARCH_LOG`、`plan/*` 等）。它是活跃系统的引用锚点，归档会断 11 处链。留在 `docs/` 作为冻结参考。
- **`Memory_Architecture_设计文档_MVP.md`**：被 3 个活跃 `plan/*` 引用（`v0.2_handoff_brief`、`v0.4`、`v0.5`）。虽是 Jul 14 早期设计、早于协议系列，但活跃计划文档仍指向它。暂留 `docs/`；若日后归档需同步改这 3 处引用。
- **`00_THEORY.md`**：最稳的公理层（几年不变），0 提及 v4 是正确的。留活跃区。
- **`02_IMPLEMENTATION.md` / `03_RESEARCH_LOG.md`**：本应随代码生长，但滞后于 Jul 22-24 的两级缓存 + 修复工作。属"活文档滞后"——**已更新到当前状态**（见各自文件），不归档。

## 活跃文档中对归档文件的残留引用

以下活跃文档仍文字提及归档文件（多为历史脉络引用，非当前操作指引）：

- `03_RESEARCH_LOG.md` → 提及 `01_PROTOCOL_v1`（v1/v2 演进脉络）、`EXPERIMENT_REPORT`（相图出处）。
- `plan/v0.3_world_evolution_phase3.md`、`plan/v0.4_external_corpus_and_sweep.md` → 提及 `EXPERIMENT_REPORT`、`RELEASE_v0.1`。
- `plan/v0.2_consolidated_to_core.md` → 提及 `RELEASE_v0.1`。
- `plan/v0.5_long_term.md` → 提及 `RELEASE_v0.1`、`Memory_Architecture`（后者未归档）。

阅读这些引用时，按本索引定位到 `docs/archive/` 对应文件即可。

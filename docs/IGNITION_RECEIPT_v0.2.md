# Ananke v0.2 `conv-26` 点火回执

> 回执日期：2026-08-18  
> 性质：探索性 P/F 完整运行的可审计收据  
> 基线 commit：`a969e5b4dce9df16950b631000c2a0a7cbf04461`  
> 可达分支：`rescue`  
> 点火前 manifest：`docs/calibration/FREEZE_MANIFEST_v0.2.json`

## 1. 运行身份

| 字段 | 值 |
|---|---|
| 语料 | `data/locomo/conv-26_corpus.jsonl` |
| 语料 SHA-256 | `1db2db3b1420dc685074f3b39331a84a77b5f96cdf88bb262cf2372bd474a904` |
| probes | `data/locomo/conv-26_probes.jsonl`，199 条 |
| probes SHA-256 | `65da45deb05f4c3a67216ec688e170ebce9b7f786a22e7772323a027e00d6c17` |
| 驱动端 | `openai-compatible|mistral-small-2603` |
| 轮次 / sessions | 419 / 19 |
| 运行顺序 | Persistence 先，Frequency 后；串行共享缓存 |
| 完成标志 | 两边 `run_metrics.completed=true` |
| 预冻结 manifest SHA-256 | `22921d2f08d2069ee397ecdc6d5e78d6647d9929a9a8fb616eeece54af65b86c` |

manifest 中“commit object 已创建、ref 未持久化”记录的是其产生当时的状态。本回执记录后续事实：
该对象已由 `rescue` 分支恢复为可达 commit。为保留点火前基线，不回写 manifest 的历史字段或文件指纹。

## 2. 结果摘要

| 指标 | Persistence | Frequency |
|---|---:|---:|
| `memory_write` | 673 | 658 |
| `working_eviction` | 609 | 546 |
| `internal_activation` | 410 | 418 |
| `local_reorganization` | 84 | 98 |
| `working_to_consolidated` | 14 | 62 |
| `consolidated_to_core` | 6 | 17 |
| `conflict_link` | 5 | 4 |
| `classification_unparsed` | 2 | 2 |
| `core_promotion_blocked` 审计记录 | 181 | 384 |
| 唯一被阻断记忆 | 1 | 2 |
| 终态 W/C/CORE | 50/8/6 | 50/45/17 |
| 终态 EV 总和 | 0 | 0 |

按 `ananke.text_norm.normalize` 对第一闸升层内容对齐：P=14、F=62、交集=14、P-only=0、F-only=48、D=48。

## 3. 请求与缓存计量

| 指标 | Persistence | Frequency |
|---|---:|---:|
| 逻辑调用 / HTTP 请求 | 1,005 / 1,005 | 153 / 153 |
| 提取 HTTP | 419 | 0 |
| relation HTTP | 586 | 153 |
| 提取 cache hit / miss | 0 / 419 | 419 / 0 |
| pair cache hit / miss | 10 / 584 | 469 / 151 |
| prompt tokens | 350,859 | 56,140 |
| completion tokens | 11,802 | 364 |
| total tokens | 362,661 | 56,504 |
| cached prompt tokens | 243,680 | 39,792 |
| 429 / HTTP errors | 0 / 0 | 0 / 0 |

P 的 relation HTTP=586 而 pair miss=584，F 的 relation HTTP=153 而 pair miss=151；两边各有 2 次分类解析重试。
F 的 153 次请求是在 P 先行填充共享缓存后的边际请求数，不得解读为 Frequency 制度的固有成本。

## 4. 产物指纹

| 产物 | SHA-256 |
|---|---|
| `logs/conv-26-full-persistence_events.jsonl` | `9ec4fe9a8e470617a06f23f0b8bc8fb17016a875f6eccdbe08ef345fcec401de` |
| `logs/conv-26-full-persistence_llm_usage.jsonl` | `62b8e0c8f528906091ef922d2ce34e211b1f3bd1c679e219f6e959bfe987fb80` |
| `data/calibration/conv-26-full-persistence/working.jsonl` | `63e6e6c22896932d9396ec36ef38fa0bf215910fe0d2b2466808a6c882c0aa4f` |
| `data/calibration/conv-26-full-persistence/consolidated.jsonl` | `340e8aa6efe99265917132ec177132f4f879e14d7bfba54495bfb27d9c108d90` |
| `data/calibration/conv-26-full-persistence/core.jsonl` | `9e7651258c47c787b2300269935e24246b5fba475201d3558cbeab40f5b8efc5` |
| `logs/conv-26-full-frequency_events.jsonl` | `14f2c92c7f1d6cce132c6b661eee71beff8986b39d703051f6bff89a852a9108` |
| `logs/conv-26-full-frequency_llm_usage.jsonl` | `366d47386568c2025e60ba67b84a680e14de2c6065ab0e345a68959471d744e7` |
| `data/calibration/conv-26-full-frequency/working.jsonl` | `e3758820ea1e1c93918b6d1ea7b8b5c60739bd733ffbdc9fe0ebbfa7e42d8b70` |
| `data/calibration/conv-26-full-frequency/consolidated.jsonl` | `c87c2a1bfb51fd4f55fc358eee184113f9071e05dbbf3a3bb30ae4cf720ba60f` |
| `data/calibration/conv-26-full-frequency/core.jsonl` | `63ce6c26a39898a47373e2ab99af46685c8a54a55d5a32cac42b7273107c5dec` |

上述 10 个运行产物均已复制到 `_IGNITION_BACKUP/`，本回执生成时逐文件重算 SHA-256，主产物与备份 10/10 全部相等。

关系分类点火前最终复跑产物 `logs/relation_retest_prompt_v2.json` 的 SHA-256 为
`79889f03a3377934275e3685b446bdba3f2528eb139748005749f4b11088845b`；其请求计量日志 SHA-256 为
`cc9555d4f21fe99b997276dbf9e89a206e88c8413949231c9b1cdef77c731f10`。

## 5. 评测停止决议

全量 judge 计划量为 199 probes × (14 P + 62 F) = 15,124 请求，其中 P/F 交集的 14 条记忆对应
2,786 次重复评估。由于 P-only=0 且 F-only 全部 EV=0，两项推测在 judge 运行前已经结构性不可判。
本轮因此未运行 DeepSeek evaluate，也未产生 `eval_p` / `eval_f` / 全量 divergence 评判产物。

## 6. EV=0 的事后分解（2026-08-18 五项检查，见 `DECISIONS_v0.2_freeze.md` §14）

本回执补充记录影响结论权重的一次归因修正与四次实证：

1. **`classification_unparsed` 原始输出**（P/F 各 2 次）均从事件日志取得，为
   `"same fact"` / `"same frame"`——mistral 对近义重复的默认输出不在协议标签内，经 B7 重试改写。
2. **c3a3d0f4 缓存模型身份**：key 前缀 + 100 轮校准 usage 日志均指向 mistral-small-2603，
   故"旧 qwen 判出 4 条 duplicate"的说法错误——那是 mistral + 旧 prompt 判的。
   由此 (a1) prompt 收窄成为 EV=0 主因（同模型、旧 prompt 判 4 条、冻结 prompt 判 0 条）。
3. **跨模型探针**（qwen3.7-max vs mistral，4 对冻结 prompt）：qwen 对同一句对判出 duplicate，
   mistral 输出 "same" 解析失败——(a2) 模型交互存在但非主因。
4. **v3 期 63 次 EV 不可比**：qwen-plus + 余弦阈值判定（样本 cosine 0.719），与 v4 分类器机制不同。
5. **模型切换从未入档**：DECISIONS 0 处提及驱动模型；冻结域不含模型标识（母题二重现）。

探针日志：`logs/cross_model_probe.json`；探针请求计量随本次会话 usage 记录，未计入上表正式运行计量。

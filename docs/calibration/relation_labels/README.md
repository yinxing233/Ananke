---
status: draft
schema_version: 1
protocol_version: v4
created_at: "2026-08-10T22:39:04+08:00"
last_adjudicated_at: "2026-08-11T16:43:00+08:00"
frozen_at: null
frozen_cases_sha256: null
source_run: conv-26-p100-persistence
model_tag: openai-compatible|mistral-small-2603
canonical_ledger: cases.jsonl
initial_cases_sha256: 7bfbc1b671160ab050c37b8d14e14627ab8c3994c15351d9e406b423fc7c6fca
---

# 关系分类操作定义与判例集

本目录是关系分类校准的自包含权威资产：本文件保存人类可读的规则、裁决理由和冻结状态；[`cases.jsonl`](cases.jsonl) 保存唯一机器可读案例账本。CSV 和 XLSX 不属于冻结域，也不作为事实来源。

当前状态为 **draft**。本轮 50 对已经用于显影分类边界，统一标记为 `development`，不得再兼任最终盲验集。正式验收必须从不重叠数据重新抽取，并标记为 `validation`。

## 当前结论

对 50 对开发样本的初步审查结果：

| 状态 | 数量 | 含义 |
|---|---:|---|
| `agreement_stable` | 18 | 人工与 Mistral 一致，暂未发现必须单独裁决的边界风险 |
| `model_clear_error` | 14 | 按下述草案规则，Mistral 的标签暂定明显不合适 |
| `human_label_review` | 6 | 原人工标签暂定需要复核 |
| `true_boundary` | 10 | 当前规则不足以唯一决定，需要 PI 裁决 |
| `consensus_boundary_risk` | 2 | 人工与模型虽然一致，但可能共同受到未冻结边界影响 |

上述分组本身也是一次待审查的分类行为，不是 ground truth。冻结前应从 `model_clear_error` 中抽查至少 3 条，确认没有系统性替任一方开脱。

## 校准进度（2026-08-11 更新）

- **12 例边界案例已裁决**（PI，2026-08-11），final_label 已写回 `cases.jsonl`；两条显式规则
  （R1 模态一致性、R2 同谓词）已入操作定义。
- **50 对一致率（闭包金标准 = final_label 兜底 human_label）**：

| 口径 | 一致率 | κ（卡帕系数） |
|---|---|---|
| human vs model（原始人工标签） | 40.0% | 0.200 |
| gold vs model（12 例裁决后） | 46.0% | 0.259 |
| 新 prompt 首次重测（2026-08-11，三层判定 + R1/R2）vs gold | 62.0% | 0.448 |
| **点火前最终复跑（2026-08-18，同 prompt）vs gold** | **60.0%** | **0.422** |

- 新 prompt 首次重测（`tools/retest_relation_50.py`，2026-08-11，50 次真实 relation 调用全
  success、零解析失败）把 κ 从 0.259 提升到 **0.448**（Landis & Koch: fair → moderate），
  over-merge 误判从 8 例降到 0，over-related 从 8 例降到 4。**12 例裁决产出的规则
  有效拉高分类器一致率，Mistral 可保留。**
- 2026-08-18 在点火前用同一 prompt 和同一 50 对开发集复跑，得到 **60.0% / κ=0.422**，
  50 次调用全部成功、零解析失败。点火基线以该次复跑为准；62%/0.448 保留为前一次结果，
  不得事后挑选较高的一次。
- 残差：duplicate 5 对全误判（判成 mergeable/related）——分类器仍不擅长"同一事实"
  识别，记入后续校准关注；contradict 仍零样本，定向补样待办。

## 判断输入闭包

人工裁决只使用关系分类器实际收到的两条记忆文本：

- 不回看 LoCoMo 原对话来补入未写出的共指、因果或事件身份；
- 共享人物不能单独构成 `related`；
- 不同日期、活动类型或言语行为方向，默认属于不同记忆键；
- 无法从文本确认 same-event / same-object / same-plan / same-attitude 时，不判 `mergeable`；有明确共同主题则降为 `related`，否则判 `unrelated`。

这样校准的是实际分类接口，而不是一个拥有额外上下文的人类任务。

**状态（2026-08-11 PI 已追认）**：本节为校准端规则，与实验设计端的"逐对无上下文分类"
（协议 v4 §2.2 设计理由 + `DECISIONS_v0.2_freeze.md` §12）是同一决策的两个面，PI 已于
2026-08-11 追认，与 §12 一并入冻结域（归因修正：PI 标注时未看 LoCoMo 对话，κ 低主因是
两句话欠定与指南未定稿，见 §12）。

**仪器属性登记（2026-08-18，B1-b）**：提取器输入仅含当前轮（Source speaker + Session
date/time + User input），看不到前文，跨轮引用（如 "something sweet"、悬空的 she/it）
**系统性不提取**——这是"上下文单点塌缩"原则的当前实现边界，不是 prompt 措辞缺陷。处置：
上下文窗口（同 session 前 N 轮）列入 v0.3 升级项，本轮不实施。决策依据：读者定位（HR）
与 PI 带宽约束。另注：本标注集的记忆文本采自前代提取器输出（未含自足性条款），与新
提取器的输出分布不同源。

## 五分类操作定义草案

判定采用**三层收紧结构**（与 relation.py prompt 一致）：① **同一事实** → `duplicate`；② **同一框架**（同一事件/计划/态度槽）→ 相容 = `mergeable`、不相容 = `contradict`；③ **同一主题**（不同框架但共享明确主题）→ `related`，无明确主题 → `unrelated`。这只是语义检查结构，不改变运行时信号映射（运行时信号优先级仍为 `duplicate > contradict > mergeable > related`，见协议 v4 §2.3）。

### `duplicate`（同一事实）

- 两句核心命题近似互相蕴含；删除任一句不会丢失实质信息。
- 上位词与明确成员枚举之间的差异可以是复述，例如“家人”与“丈夫和孩子”。
- 若一方新增独立属性、原因、时间或事件，则不判同一事实。

### `contradict`（矛盾）

- 必须是同一主体、同一命题槽、同一时间/条件框架下无法同时成立。
- 时间先后变化、偏好改变、计划后来实现，不能自动当作矛盾。
- 不能确认参考框架相同时，保守地不判矛盾。

### `mergeable`（可合并补充）

- 文本必须明确共享同一事件、对象、计划或态度框架。
- 另一句增加兼容属性、原因、时间或细节；合并后每项信息仍可追溯。
- 只有共同人物或宽泛主题，或者明显是不同日期/活动时，不得合并。

### `related`（相关但不同）

- 两句存在明确共同主题，足以解释为何会共同召回。
- 事件、状态、计划或态度仍然独立；合并会形成两个并列命题。
- 若只能依靠共享人物或抽象正向语气建立联系，则不够相关。

### `unrelated`（无关）

- 没有明确共同事件、对象、计划、态度或具体主题。
- 删除人物姓名后仍看不出实质联系时，默认无关。

### 显式交叉规则（2026-08-11 裁决后写入，约束相邻类边界）

判定顺序为 `contradict → duplicate → mergeable → related → unrelated`，**逐层收紧**：

- **层1 同一事实** → `duplicate`：核心命题互相蕴含，删任一句不丢信息。
- **层2 同一框架**（同一事件/计划/态度槽）→ 相容 = `mergeable`，不相容 = `contradict`。
- **层3 同一主题**（不同框架但共享明确主题）→ `related`；连明确主题都没有 → `unrelated`。
- **related 的本质 = 不确定性着陆点**：闭包规则下"无法确认同一框架"的案例自然落进
  `related`（即"related 汇"效应，已登记为仪器属性，见 DECISIONS §12 与相关讨论）。

**规则 R1（模态一致性）**：上位—具体可合并，**仅当两句同模态**（同为计划 / 同为事件 /
同为态度）；跨模态时至多 `related`。例：P036 同为计划模态（探索职业方向 vs 规划继续教育）
→ `mergeable`；P007 为倾向 vs 已发生事件（跨模态）→ `related`。

**规则 R2（同谓词）**：`mergeable` 要求相同的态度谓词（同"关系框架"）。例：P001
`admires + admires`（同谓词）→ 可并槽；P037 `inspired + admires`（不同谓词）→ 不合并，
仅 `related`。

## 12 个边界案例（2026-08-11 PI 已裁决，写回 cases.jsonl）

裁决时只需给出最终标签；若接受建议，不需要另写理由。若修改建议，后续只讨论发生修改的条目。最终标签已写回 `cases.jsonl` 的 `final_label`，并记录 `adjudicator=PI` 与 `decided_at=2026-08-11`。

| 案例 | 人工 | Mistral | 建议 | **裁决** |
|---|---|---|---|---|
| P001 | mergeable | related | mergeable | **mergeable** |
| P002 | mergeable | mergeable | related | **related**（规则推翻人机共识：实现 vs 计划为因果相关，非同一框架） |
| P006 | unrelated | related | related | **related**（related 下界标定案例） |
| P007 | mergeable | related | related | **related**（跨模态：倾向 vs 事件） |
| P010 | duplicate | mergeable | related | **related**（"梦想"句内未解析） |
| P014 | unrelated | related | unrelated | **unrelated**（不补隐藏因果） |
| P018 | duplicate | mergeable | mergeable | **mergeable**（实质原因为新增槽） |
| P019 | unrelated | mergeable | related | **related**（共享"获得支持"主题，来源结果不同） |
| P022 | unrelated | mergeable | related | **unrelated**（与 P014 同构，统一无关） |
| P028 | unrelated | mergeable | related | **related**（无显式共指，不合并） |
| P036 | related | mergeable | mergeable | **mergeable**（同模态：计划+计划，R1 支持） |
| P037 | related | related | related | **related**（不同谓词，R2 排除合并） |

裁决分布：**mergeable 3（P001/P018/P036）· related 7（P002/P006/P007/P010/P019/P028/P037）·
unrelated 2（P014/P022）· duplicate 0 · contradict 0**。duplicate/contradict 零样本意味着开发集对
这两个关键类无约束力，须在独立数据定向补齐（见"冻结检查表"）。

### P001 — 同一关系框架中的并列属性

- 新记忆：Melanie admires Caroline's impact（梅兰妮钦佩卡罗琳带来的影响）
- 既有记忆：Melanie admires Caroline's courage（梅兰妮钦佩卡罗琳的勇气）
- 人工：`mergeable`；Mistral：`related`
- 建议：`mergeable`
- 冻结问题：相同主体、态度和对象下的并列理由，是否属于同一态度记忆的可追加槽？建议是；两句不互相蕴含，所以不是 `duplicate`。

### P006 — 抽象共同主题的粒度

- 新记忆：Caroline agrees that taking care of oneself is important
- 既有记忆：Caroline feels accepted and gained courage to embrace herself through the support group
- 人工：`unrelated`；Mistral：`related`
- 建议：`related`
- 冻结问题：自我照顾与自我接纳共享心理健康主题，但不是同一事件或状态；因此不应 `mergeable`。

### P007 — 一般倾向与具体实例

- 新记忆：Caroline speaks up for the trans community
- 既有记忆：Caroline talked about her transgender journey at a school event last week
- 人工：`mergeable`；Mistral：`related`
- 建议：`related`
- 冻结问题：具体演讲可能体现一般性倡导，但文本没有说明两者是同一事件；保留为两个命题。

### P010 — 模糊指代与隐藏上下文

- 新记忆：Caroline is starting the hard work to turn her dream into reality
- 既有记忆：Caroline is planning to continue her education and explore career options
- 人工：`duplicate`；Mistral：`mergeable`
- 建议：`related`
- 冻结问题：“梦想”没有在句内解析为教育/职业目标；不能依赖原对话补足。它显然不是 `duplicate`，直接合并也过强。

### P014 — 隐含回应关系

- 新记忆：Melanie praised Caroline for taking in kids in need
- 既有记忆：Caroline thanked Melanie for something sweet
- 人工：`unrelated`；Mistral：`related`
- 建议：`unrelated`
- 冻结问题：称赞与感谢可能在原对话中相连，但句对没有明确说明感谢针对该称赞；不补入隐藏因果。

### P018 — 概括与带原因的具体陈述

- 新记忆：Caroline thanked Melanie
- 既有记忆：Caroline thanked Melanie for something sweet
- 人工：`duplicate`；Mistral：`mergeable`
- 建议：`mergeable`
- 冻结问题：后者增加了感谢原因；需要决定单向蕴含是否仍算同一事实。建议把实质原因视为新增槽，因此不是 `duplicate`。

### P019 — 共同支持主题

- 新记忆：Caroline is grateful for support from friends and mentors
- 既有记忆：Caroline feels accepted and gained courage to embrace herself through the support group
- 人工：`unrelated`；Mistral：`mergeable`
- 建议：`related`
- 冻结问题：两句共享“获得支持”主题，但来源和结果不同；因此不应直接合并，也不完全无关。

### P022 — 可能属于同一交流链

- 新记忆：Melanie praised Caroline for sharing her story and creating love, acceptance and hope
- 既有记忆：Caroline thanked Melanie for something sweet
- 人工：`unrelated`；Mistral：`mergeable`
- 建议：`related`
- 冻结问题：两句话可能构成称赞—感谢链，但没有显式说明感谢对象；至多判相关，不足以合并。

### P028 — 可能同一事件但缺少显式共指

- 新记忆：Caroline found the transgender stories inspiring and felt happy and thankful for the support
- 既有记忆：Caroline went to an LGBTQ support group on 7 May 2023
- 人工：`unrelated`；Mistral：`mergeable`
- 建议：`related`
- 冻结问题：鼓舞和支持可能发生在支持小组，但句对没有显式共指；不得直接合并。

### P036 — 上位计划与具体选项

- 新记忆：Caroline has been exploring counseling and mental health as a career path
- 既有记忆：Caroline is planning to continue her education and explore career options
- 人工：`related`；Mistral：`mergeable`
- 建议：`mergeable`
- 冻结问题：教育/职业探索是上位计划，咨询和心理健康是具体方向；若允许“上位计划 + 明确选项”共享一个计划键，则可以合并。

### P002 — 双方一致但存在时间身份风险

- 新记忆：Melanie took her family camping in the mountains a week before 27 June 2023
- 既有记忆：Melanie is considering going camping next month
- 人工：`mergeable`；Mistral：`mergeable`
- 建议：`related`
- 冻结问题：已发生的露营与未来露营计划在文字上是不同时间事件；是否为同一计划的实现无法从句对确认。

### P037 — 双方一致但需与 P001 保持规则一致

- 新记忆：Melanie is inspired by Caroline's dedication
- 既有记忆：Melanie admires Caroline's courage
- 人工：`related`；Mistral：`related`
- 建议：`related`
- 冻结问题：两句使用不同态度谓词，而 P001 使用相同谓词；规则应明确“同一关系框架”是否要求谓词也相同。

## 候选判例骨架

以下仅为候选；待上面 12 个边界案例裁决后再复核，并从 `development` 中正式标记为 `precedent`。

| 标签 | 候选 ID | 边界说明 |
|---|---|---|
| `duplicate` | P013、P030、P040 | 核心命题互相蕴含；没有独立新增事实 |
| `mergeable` | P004、P035、P039 | 明确共享同一体验、对象或具体记忆键，并增加兼容属性 |
| `related` | P003、P020、P038 | 共同主题明确，但活动身份或时间不同 |
| `unrelated` | P008、P031、P050 | 除人物外没有实质共同主题 |
| `contradict` | 暂缺 | 必须从独立数据取得同一命题槽、同一参考框架下的不相容陈述 |

## 动力学相关性

分类误差会进入状态演化，因此判例集不能只解释语义，还必须记录相邻类别的系统后果：

| 标签 | v4 当前后果 |
|---|---|
| `duplicate` | 不写新记忆；满足跨 session 条件时可能贡献 EV |
| `contradict` | 写入新断言；建立 conflict；阻断相关记忆晋升 CORE |
| `mergeable` | 不写新记忆；`local_reorganization_trigger +1` |
| `related` | 写新记忆；既有记忆 `internal_activation +1` |
| `unrelated` | 只写新记忆，不增加既有记忆信号 |

## 来源与迁移记录

迁移时间：`2026-08-10T22:39:04+08:00`。

| 迁移来源 | SHA-256 |
|---|---|
| `cache/pairs.jsonl` | `9601e73e49754e2a6623c500a0243083367926e9e3f01ba22160e9a0bc3e204f` |
| 原始 50 对导出 JSONL | `050fe6b3f3910fba71012e2d9823d6e2a992b7fc91b079f97a6c02b3e92be383` |
| 原始 50 对导出 CSV | `9382e90757d909331251ef954f0d1b366946881ab7baa83aa5dc90649e0a5e88` |
| 完成人工标注的 XLSX | `7702cc6f443e9e8f31481ecd361e372e4c94ecf19cc777aece88535d6e296927` |
| 三分诊断草案 XLSX | `d95f76399f956456f71f106c09d5b31d2b40e9dc92e8f1898a0cdf247caa01b2` |

这些中间文件在迁移核对完成后删除；其内容已由本文件和 `cases.jsonl` 接管。缓存 `cache/pairs.jsonl`、运行日志和实验状态不属于中间文件，不得删除。

## 冻结检查表

- [x] 完成 12 个边界案例裁决并记录时间（2026-08-11）
- [ ] 抽查至少 3 个 `model_clear_error` 条目
- [ ] 为五个类别各保留 3–5 个“为什么不是相邻类”的判例
- [ ] 从独立数据补齐 `contradict` 定向样本
- [ ] 将候选判例标记为 `precedent`
- [ ] 从不重叠数据创建新的 `validation` 集
- [ ] 计算并填写 `frozen_cases_sha256`
- [ ] 把 `status` 改为 `frozen`，填写 `frozen_at`
- [ ] 创建对应 Git commit；需要时打 `relation-labels-v1` tag

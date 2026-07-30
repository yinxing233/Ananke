# 01_PROTOCOL_v4.md

# Ananke 协议 v4（草案，未冻结）

状态：草案。冻结条件见 §8。
2026-07-28 形成的 B1–B7 裁决集已于 2026-07-30 获 PI 验收（见
[`DECISIONS_v0.2_freeze.md`](./DECISIONS_v0.2_freeze.md)）；实现与守护测试已完成，
但冒烟校准、独立复核及其余 §8 条件尚未完成。不得把“裁决已实现”叙述为“协议 v4 已正式冻结”。
上游文档：00_THEORY.md（原则A/B，约束C1–C4，本版本不改动）
取代：01_PROTOCOL_v3.md

---

## §0 变更-反驳条款（本版本起为协议元规则）

每次协议版本变更必须同时声明：
(a) 本次变更改变了哪个可观测量；
(b) 什么实验结果将构成对相应理论推论的反驳。

**v4 声明：**

- (a) 改变的可观测量：EV/IA/DEDUP/REORG 四信号的判定来源，
  从"单一余弦阈值"变更为"余弦召回 + 关系分类 + session 结构"。
- (b) 反驳条件：在 §6 定义的分歧集分析中，若 persistence 独有
  升层记忆的 evidence 命中率不高于 frequency 独有升层记忆，
  则 C2（存续检验优于频率驱动）的本操作化不获支持。

**2026-07-30 PI 已验收的追加声明（B1–B7）：**

| 裁决 | 改变的可观测量 | 反驳/失效条件 |
|---|---|---|
| B1 distinct-session EV | EV 总量、P/F 升层集合与 D | EV 稀疏到无法驱动 persistence 时，本 session 操作化欠功效；不得恢复同 session 重复投票 |
| B2 system_guided 未启用 | 无动力学变化；新增来源审计 | v0.2 正式运行若出现 `system_guided=True`，运行违反边界 |
| B3 CORE 进入召回 | 写入量、重复晋升、CORE 审计计数、D | `|D|<20` 触发结局 (c)，不得撤回 CORE 召回来恢复样本量 |
| B4 完整制度比较 | 因果解释上限 | 若有效 D 上 `h_P≤h_F`，C2 的 v4 制度操作化不获支持 |
| B5 保留 EV=0 晋升可能 | 无，保留既有公式 | 若 EV=0 记忆在有效评估中系统性缺乏 evidence，后续版本重审权重/阈值 |
| B6 reference-grounded judge | evidence 命中、有效分母、失败率 | judge 失败率>5% 或人工锚点未达标时评估无效 |
| B7 分类解析硬失败 | 写入量、失败轮次、恢复次数 | 重试后仍高频失败则分类器未达冻结条件，不得静默降级 |

完整裁决、被拒绝方案与实现边界以
[`DECISIONS_v0.2_freeze.md`](./DECISIONS_v0.2_freeze.md) 为准。

---

## §1 主张层级链（约束所有文档与叙事的措辞）

```

约束场理论（本项目不检验）
→ 原则B（不直接检验）
→ 工程推论C2："存续驱动迁移优于频率驱动"（本项目检验的命题）
→ v4操作化：Persistence / Frequency 两套完整选择制度的沉淀质量比较
→ 可观测预测："分歧集上，persistence独有升层的
reference-grounded evidence命中率 > frequency独有升层"（本实验测量的量）

```

结果向上传导力度逐级递减。预测成立 → C2 获支持 → "与原则B一致"
（非验证）→ 对理论本身无断言。任何文档、README、口头叙事中的
主张不得越级。

---

## §2 核心架构变更：召回-分类两段式（取代 v3 的阈值分类）

### 2.1 问题（v3 的范畴错误）

余弦度量话题邻近度；四信号需要命题关系（同一/蕴含/矛盾/关联）。
矛盾对与复述对在嵌入空间占据同一高余弦区间，单标量不可分离。
v3 死结（REORG⊂DEDUP拦截区）与 EV 污染（矛盾计为验证）是同一
错误的两次显影。

### 2.2 新管线

```

新提取记忆 m
→ 余弦召回：对 WORKING + CONSOLIDATED + CORE 全部已有记忆检索
  cos ≥ R_recall 的候选对 [R_recall 初值 0.65，待冒烟校准]
→ 关系分类器：对每个候选对 (m, e) 输出五分类
{duplicate, contradict, mergeable, related, unrelated}
→ 信号映射（§2.3）

```

关系分类器实现（二选一，冒烟测试后定）：

- 方案甲：本地 NLI cross-encoder（DeBERTa-MNLI 系），
  entail→duplicate/mergeable 需附加同义判定；零 API 成本。
- 方案乙：LLM 结构化五选一（复用现有 llm_client）。
- [待冒烟校准]：在 50 个候选对上人工标注对比两方案准确率后拍板。

**分类解析失败条款（B7）**：

- 只接受五个合法标签及协议显式登记的同义 token；
- 未知、空或不可解析响应不缓存，最多重试 3 次；
- 每次失败记录 `classification_unparsed`；
- 重试耗尽后本轮硬失败，不得降级为 unrelated；
- 轮级原子性是前置条件：失败回滚本轮状态与状态事件，回滚后保留
  `classification_unparsed` / `turn_failed` 审计事件；
- runner 非零退出；恢复时保留合法 LLM 缓存，清理运行状态后从第 1 轮确定性重放。

原因：unrelated 会写入新记忆。把格式/基础设施故障折叠成 unrelated 等于把仪器故障变成真实动力学，
改变未来召回集合。

**召回简化声明（v0.2 已验收裁决，须冒烟时复核）**：
v0.2 对**余弦最高的单个候选** e 做关系分类（top-1），而非字面的「每个候选对」。
候选覆盖三层；相似度完全相同时按 `CORE > CONSOLIDATED > WORKING` 决胜，同层再用稳定内容键和
ID 兜底，禁止依赖容器遍历顺序。层级决胜是 B3 的 PI 裁决，直接影响分类受体与 D，不是实现细节。
这是 v0.2 的工程简化，避免一对多信号叠加；但有一个**有方向的失效模式**必须登记：
矛盾对（改一个词）的余弦往往**高于**复述对（换个说法），故当 m 同时与 e1 构成 duplicate、
与 e2 构成 contradict 时，top-1 会系统性偏向捕获 contradict 而漏掉 EV——在含改口的语料上
是对 persistence 策略的**单向压制**（persistence 依赖 EV 升层，漏 EV = 系统性低估 persistence）。
v0.2 处理：已验收裁决保持 top-1；冒烟时观察实际候选分布（多少 (m,e) 对存在多候选、矛盾对是否
系统性排在复述对前）。若观测到上述偏向，不得在实现层静默切 top-k；须新增协议修订，声明对
可观测量 D 的影响，再决定是否按 duplicate > contradict > mergeable > related 归并多候选信号。

### 2.3 信号映射表（取代 v3 的阈值表）

| 分类结果   | 附加条件                    | 触发信号                                                         |
| ---------- | --------------------------- | ---------------------------------------------------------------- |
| duplicate  | 来源为尚未贡献过 EV 的后续 distinct session，且非 system-guided（§3） | EV +1，登记该 session，不写入（去重） |
| duplicate  | 创建 session、已贡献过 EV 的同一 session、session 缺失或 system-guided | 去重，不计 EV；system-guided 不占用该 session 的未来 EV 资格 |
| contradict | —                           | ① 受体 conflict trigger +1；② **新断言写入快层**并与受体建**双向 conflict 链接**（漂移2 修正：系统须能更新世界状态）；③ 受体 conflict_trigger>0 即成为 CORE **晋升阻断器**（见下） |
| mergeable  | —                           | local_reorganization_trigger +1（**不写**新记忆，信息多为冗余，留债） |
| related    | 同 session                  | IA +1                                                            |
| related    | 跨 session                  | IA +1 [注：跨session的related是否应计EV，挂起至v5，当前保守处理] |
| unrelated  | —                           | 正常写入快层                                                     |

EV/IA 互斥原则（v2 决策）保留：每条记忆每轮至多触发一个信号，
判定优先级 duplicate > contradict > mergeable > related。

B1 只限制 EV：对非 system-guided 的后续跨 session duplicate，Frequency 使用的
`total_activation` 仍按每次出现累加；同一 session 首次可同时贡献 EV，后续只贡献
total_activation。创建 session 内 duplicate 沿用“去重、无激活信号”。改变 total_activation
来源语义须另走 §0，不能夹带在 distinct-session EV 实现中。

**CORE 受体语义（B3）**：上述五分类同样作用于 CORE，但 CORE 已在顶层，所有新增计数在 v0.2
只供审计，绝不进入晋升、淘汰或降级决策：

- duplicate：按 B1 计或不计 EV，始终不写新记忆；
- related：CORE IA +1，新事实写入 WORKING；
- mergeable：CORE local_reorganization_trigger +1，不写新记忆；事件日志必须保存完整增量文本
  与输入来源，不能只保留前 120 字符；
- contradict：新断言写入 WORKING，与 CORE 建双向 conflict link，CORE conflict_trigger +1；
  不降级、不删除、不裁决；
- unrelated：正常写入 WORKING。

CORE 的“很少改动”来自写入/修改门槛，而非召回隔离。v0.2 只做到识别、计数和留痕；
真正吸收 mergeable 增量、裁决 contradict 及受控改写 CORE 留给 v0.3。

### 2.4 v3 死结的解除

DEDUP 与 REORG 不再共享余弦轴。duplicate 命中即去重（含EV判定），
contradict/mergeable 直接进入重组——重组信号不再经过 dedup 丢弃堆。
v3 推荐的方向三由本结构自然吸收。

### 2.5 CORE 晋升阻断器（Fable5 漂移1 修正）

中→慢闸（consolidated→core）晋升**唯一条件** = 受体 local_reorganization_trigger
≥ LOCAL_REORG_THRESHOLD（mergeable 累积，代表被反复确认/合并的稳定结构）。
**conflict_trigger > 0 的记忆不得升 CORE，冻结在中层**（v0.2 重组已退化为计量，无裁决/解封
机制，故 = 永久阻断；见下方「阻断可观测性」条款）。

理由：v3 的病根是"把被外部输入接触当成被外部输入确认"（矛盾被余弦 EV 计为验证，
污染快→中迁移）。本结构已在**第一道闸**用关系分类杀死了它；但若允许矛盾两次→升
CORE，等于在**第二道闸亲手重建同一错误**——一条被矛盾两次的记忆是"正在被检验且检验
失败中"的结构，送进最稳定层是方向性反转，且 LoCoMo 自然语料中改口/更新高频，被争议
记忆将批量涌入 CORE，直接污染验证阶段测量。故 conflict 从"晋升信号"改为"晋升阻断器"。
（阻断器与 --strategy 无关；若未来需恢复矛盾路径，须先有裁决环节，属 v0.3+ 设计。）

**阻断可观测性（PI 漂移B 回执）**：永久阻断是 v3 死结的同构复现风险——自然语料上
contradict 高频 → 中层记忆批量被永久阻断 → core 晋升率可能趋零（v0.1 已见"中→慢在真实
LLM 下从未触发"症状，须警惕换机制回来）。`tools/run_corpus.py` 结束时报告阻断率与 core 晋升数
（实现在 `migration.block_state_summary`）；若阻断率 ≥ ~30%，第二道闸实质瘫痪，**冻结前**须
重评阻断条件（如改 `conflict_trigger > merge_trigger` 的相对判据，而非 v0.2 的绝对 `>0`）。

**阻断不威胁主测量（须显式声明，防审查者误问）**：D 只测 working→consolidated 第一道闸
（§6），evaluate 测中层+core 两层之和（§5）；阻断只改变记忆**位于哪一层**，不改变它**是否被
测到**。故阻断率不影响主测量量的有效性，仅影响 core 层的构成（core 是 v0.2 的描述性产物，
非反驳条件的载体）。

---

## §3 EV/IA 的 session 语义（LoCoMo 适配，PI 已拍板）

### 3.1 定义

- **EV（外部验证）**：记忆 m 已存在于系统中，且在一个**此前尚未为 m 贡献过 EV 的后续
  distinct session** 中被判定为 duplicate（再确认），同时该输入不是 system-guided。
  每个 session 对同一记忆终身至多贡献 1 次 EV。
- **IA（内部激活）**：输入被判定为 related；同/跨 session 均按 §2.3 的保守规则计 IA。
- 记忆必须持久化已贡献 EV 的 session 集合。system-guided 输入不计 EV，也不占用该 session
  未来贡献 EV 的资格。
- 创建来源与当前输入来源分轨保存：`source_*` 属于 MemoryEntry，`input_*` 属于当轮事件上下文；
  speaker/dia_id 在 v0.2 只用于审计，不参与任何得分或迁移。

### 3.2 理论依据（写入 00_THEORY 附录）

原则B中"不可控外部输入"的检验力来自输入与系统局部状态的
**因果独立性**，而非随机性。同 session 重提受话语惯性驱动
（局部连贯性 = 内循环的语料层同构物）；session 边界是一次
话语状态重置，跨 session 再断言由说话人稳定世界状态支撑。
故 session 边界 = 去相关事件，跨 session 再确认 = 独立性代理。
人工时间标注足够，因为起作用的是话语状态重置而非物理时间。

### 3.3 显式适用边界（不可删除）

LoCoMo 为静态语料回放，系统是被动观察者，agent 输出不影响
后续输入。**闭环情形下的原则B（系统自身行为污染输入流）在
本设计中未被检验。** 此为 v0.3 方向，非本版本缺陷。

代码保留 `system_guided` 钩子，但 v0.2 runner 中恒为 False、没有真实触发源。它是未启用接口，
不是闭环防护已实装的证据；正式 v0.2 事件若出现 True，则该运行违反本边界并作废。

---

## §4 保留与冻结的 v3 条款

- 三层结构、容量（50/200/∞）、persistence_score 公式、
  权重比 1/e、persistence 阈值 3.0、frequency 阈值 3：不变。
- 淘汰跟随策略（v3 修复 #13）：不变。
- 局部重组 LLM 三选一（合并/矛盾/无关）：被 §2.2 分类器吸收，
  reorganization.py 的入口改为接收 contradict/mergeable 事件。

### 4.1 P/F 比较单位（B4）

> P/F 是两套完整的记忆选择制度，差异起点为存续/频率计分，经由晋升门槛、超容量淘汰、及由此
> 改变的后续召回集合传播。本实验比较**制度整体的沉淀质量**，不宣称隔离了计分函数的单因子
> 效应。单因子消融为后续版本方向。

因此，“同语料、同驱动模型、同缓存、同输入顺序”仍是控制条件，但 D 的因果解释上限是完整制度
差异，不能写成 score 函数的单变量效应。

### 4.2 EV=0 边界（B5）

保留 `persistence_score = EV×1.0 + IA×(1/e)`，不增加 `EV>0` 必要条件。C3 约束的是外部权重
方向性高于内部激活，不等于外部信号一票否决。预登记推测 2 依赖 EV=0 记忆在两种制度下都存在
晋升可能；若加硬门槛，`F\P` 富集 EV=0 将退化为定义上的同义反复。

---

## §5 评估独立性条款

- 驱动端：sentence-transformers 嵌入 + Gemini 提取。
- 评判端主裁判：**不同家族 LLM**（DeepSeek 或 GLM）。每次判定必须同时接收记忆 X、
  问题 Q 与标准事实/答案 `reference_fact`，结构化回答：
  “X 是否包含支持 reference_fact、从而正确回答 Q 所需的事实：包含/部分/不包含”。
- 已验收计分裁决：包含=1.0，部分=0.5，不包含=0.0；标签必须互斥解析。
- 缺少 `reference_fact` 的 probe 不得进入正式评估。
- judge 失败的 `(memory, probe)` 对剔除并计数，不折算为不命中；某记忆全部 probe 无有效判断时
  标记 `unscored`。`judge_failure_rate = 失败调用对 / 全部计划调用对`，超过 5% 时整次评估
  无效并以非零状态结束。
- 正式评估缺少真实评判端配置时不得静默降级为 mock。
- 人工锚点：PI 本人抽检 50 条与主裁判对齐，报告一致率。
- 嵌入模型在评估端**禁止出现**（防驱动-评判度量循环）。

---

## §6 分歧集实验设计

- P = persistence 完整选择制度的第一道闸升层集合，
  F = frequency 完整选择制度的第一道闸升层集合（§4.1）。
- 分歧集 D = (P\F) ∪ (F\P)。主分析对象为 D，非聚合指标。
- **测量范围（PI 追认，Fable5 漂移3）**：D 仅在 **working→consolidated 第一道闸** 测量。
  中→慢闸（consolidated→core）对两策略走**同一逻辑**（晋升条件不含 --strategy，
  仅受 merge trigger / conflict 阻断器约束），故对 D **零贡献**。这是**收窄测量范围**的
  显式决策（把比较限定在第一道闸），非实现默认——记录为 PI 签字项。若未来要在第二道闸
  也比较，须先解决 §2.5 冲突路径的未决语义，属 v0.3+。
- **跨运行同一性判据（Fable5 漂移4）**：两次独立运行里同一条事实会生成不同 UUID，D 比对
  **按归一化内容键**对齐，规则如下（实现见 tools/divergence_analysis._norm）：
  - 小写化；
  - 去除所有非字母数字/非空白字符（即去标点；`\w` 在 unicode 下覆盖中文）；
  - 折叠连续空白并去首尾空白。
  - **改写容忍度不在 v0.2 范围**：两条表述同一事实但措辞不同的记忆，归一化后仍判为两条
    分歧（假阳性）。此为已知限制，v0.3+ 引入语义聚类消解。
- 核心测量：D 中两侧独有升层记忆的 **reference-grounded evidence 命中率**。
  主裁判必须对照 question + reference_fact；包含=1.0、部分=0.5、不包含=0.0。
  judge 失败按 §5 剔除并报告，失败率>5% 时本次测量无效。
- 机制签名检查：F\P 中 EV=0 记忆的富集度及其命中率。EV=0 在 persistence 中不被硬阻断，
  因而该签名不是定义上的必然（§4.2）。
- CORE 的 normalized exact duplicate rate 作为描述性报告指标，不作失败断言；确定性测试只要求
  exact duplicate 命中 CORE 后不再新建副本。
- 统计功效下限：|D| ≥ 20。
- 欠功效预案：|D| < 20 时，对阈值 sweep 强发散区各配置格
  重跑双策略，聚合各格分歧集分析，同时报告逐格结果。

---

## §7 探索/验证两阶段分离

- **探索阶段（当前）**：LoCoMo 抽取 1–2 个对话做冒烟测试。
  允许调参、改协议、修 bug。本阶段所有数字标注"探索性"，
  不进入任何结论。
- **冻结点**：v4 全部 [待冒烟校准] 项填入定值、B1–B7 实现与守护测试通过 →
  创建一次性 `PREREGISTRATION.md`（验证集 ID、预测原文、代码/语料/探索日志指纹、
  不可变性声明）→ 协议冻结。
- `RESEARCH_CONJECTURES.md` 保留为探索期来源文档，不通过删掉“可修改”字样伪装成历史预登记；
  正式承诺由新建的 `PREREGISTRATION.md` 承担。
- **验证阶段**：在**冒烟未使用的**对话上运行正式实验。
  数据隔离为硬约束：探索阶段接触过的对话不得进入验证集。

---

## §8 冻结条件清单

- [ ] R_recall 定值
- [ ] 关系分类器方案（甲/乙）定值 + 50 对人工标注准确率报告
- [x] "部分包含"计分规则定值：0.5（B6 已实现并有守护测试）
- [x] B1–B7 行为实现 + 守护测试通过（2026-07-30：`70 passed`）
- [ ] 轮级原子性与硬失败恢复冒烟通过
- [ ] 冒烟测试通过（全链路无错 + 提取量级/成本在预算内）
- [ ] 验证集对话 ID 列表锁定并写入本文档附录
- [ ] `PREREGISTRATION.md` 一次性提交（预测、保留集、指纹、不可变性声明）

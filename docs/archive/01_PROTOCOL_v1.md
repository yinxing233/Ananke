# Phase 1 实验协议（Experimental Protocol）

> ⚠️ **本版本已被 `01_PROTOCOL_v2.md` 取代（2026-07-14）。保留供审计。**

> **身份声明（原则 C 的操作化）**：本协议是**约束场理论**与 Ananke 实现/证据之间的**唯一合法映射层**。
> 理论不会直接面对世界，世界也不会直接验证理论；中间必须隔着这一层"操作定义"。
> 冻结本协议后，`analyze_trajectory.py` / `run_corpus.py` / 具体 LLM 都只是"同一协议下可替换的实现"，
> Evidence 才能落进协议定义好的格子里，理论才真正开始接受约束。

---

## TL;DR — 冻结要点（先读这段）

- **协议是什么**：约束场理论 → 可执行语言（操作定义 + 判定函数 + 证据来源 + 获取红线）。不是"实验流程说明书"。
- **External Validation（外部验证）** = 不可控外部输入 + 余弦 ≥ 0.85。有意为"系统诱导/自生成"一律不计。
- **Internal Activation（内部激活）** = 余弦 ≥ 0.60 但 **未达**外部验证标准。注意：s≥0.85 且来源外部时，EV 与 IA **同时** +1（设计有意，非 bug）。
- **Persistence** = 外部验证×1.0 + 内部激活×1/e，**终身累积、不重置、不衰减**（衰减属 v0.2）。
- **Migration（单向阀）**：working→consolidated 当 persistence ≥ 3.0；consolidated→core 当 trigger ≥ 2。只升不降。
- **Phase 1 证伪命题**：若迁移规则=Persistence，系统能否稳定产生符合该规则预期的动力学轨迹？（只证实现忠实，不证理论正确）
- **Phase 3 真比较**：Internal Selection（Frequency，内部选择压力）vs External Selection（Persistence，环境选择压力）—— 谁产生的结构更能经受演化中的外部世界。

---

## 0. 本协议冻结什么、不冻结什么

- **冻结**：理论变量的**操作定义（Operational Definition）** + **判定函数（Decision Function，布尔）** + **证据来源（Evidence Source）** + **证据获取的允许/禁止方式（防反身性污染）**。
- **不冻结（属实验控制变量，固定即可）**：具体 LLM 型号、Prompt 微调用词、运行环境。这些不改变理论映射。
- **本协议不证明理论正确**，只保证：若实现偏离理论，Evidence 能显示偏离；若实现忠实，Evidence 能复现理论预测的**可能性空间形状**（分层 / 外部门控 / 单向阀）。

---

## 1. 理论变量 → 操作定义 → 判定函数

> 每个判定函数返回布尔；条件用 `config.py` 中的实际常量，确保可复现。

### 1.1 外部验证 External Validation — `EV(m, x)`
- **理论根**：原则 B / 反身性条件（不可被系统自身消除的外部验证）/ "疏而非堵"通道。
- **操作定义**：一条外部输入 x 对记忆 m 构成"外部验证" ⇔ x 来自**不可控外部来源**，且与 m 语义高度相似。
- **判定函数** `EV(m, x) = True` 当且仅当：
  1. `s = cosine(encode(x), encode(m.content)) ≥ EXTERNAL_VALIDATION_THRESHOLD` (0.85)
  2. `Source(x)` ∈ 允许集合（见 §3）：x 是用户/语料/公开数据集提供的真实输入，**不是系统生成、不是系统诱导、不是实验者构造的近重复**
  3. x 代表一个真实环境事件（非系统自问自答、非复述自身输出）
- → 若 True：`external_validation_count[m] += 1`

### 1.2 内部激活 Internal Activation — `IA(m, x)`
- **理论根**：原则 A（沉淀速率分离；工作层有独立于外部的自身更新频率）。
- **操作定义**：输入 x 与记忆 m 语义相似但未达外部验证标准的，计为一次内部激活。
- **判定函数** `IA(m, x) = True` 当且仅当：
  1. `s = cosine(...) ≥ INTERNAL_ACTIVATION_THRESHOLD` (0.60)
  2. **且 `NOT EV(m, x)`**（即 s < 0.85，或虽 ≥0.85 但来源不满足外部条件）
- → 若 True：`internal_activation_count[m] += 1`
- ⚠️ **重叠声明（冻结，防日后重新解释）**：当 s ≥ 0.85 **且**来源满足外部条件时，EV 与 IA **同时触发**（+1 外部 +1 内部）。这是设计有意行为，persistence_score 因此涨得比"纯外部"更快。任何后续分析不得把它 reinterpret 成单一信号。

### 1.3 存续检验 Persistence — `P(m)`
- **理论根**：原则 B（"持续检验"由环境执行）/ 约束场理论"存续检验必须不可控"。
- **操作定义**：记忆 m 的存续分数 = 外部验证（环境选择压力，权重 1.0）+ 内部激活（系统内部选择压力，权重 1/e）。
- **判定函数**：
  - `persistence_score(m) = external_validation_count[m] * 1.0 + internal_activation_count[m] * (1/e)`
  - **计时语义（冻结）**：**终身累积、不重置、不衰减**（衰减属 v0.2 开放问题）。这忠实实现"持续检验"；若未来换实现（如带衰减），须作为新的理论-实现映射单独冻结。

### 1.4 局部重组 Local Reorganization — `Conflict(m, c)` / `Merge(m, c)`
- **理论根**：单向阀机制（慢→快塑形，快不回写慢；重组只在巩固层内部发生）。
- **操作定义**：新记忆 c 进入巩固层后，若与既有巩固记忆 m 高度相似，由 LLM 三选一判定关系。
- **判定函数** `Conflict(m, c) = True` 当且仅当：
  1. `s = cosine(encode(c), encode(m.content)) ≥ REORG_SIMILARITY_THRESHOLD` (0.90)
  2. `LLM(three-choice prompt, temperature=0.0)` 返回 "矛盾"
- → 若 True：`local_reorganization_trigger[c] += 1`（c 是触发源）
- `Merge` 同理，LLM 返回 "合并" 时触发。**MVP 仅计数、不整合**（避免污染要观测的 trigger 信号，见 MVP 边界 §十二）。

### 1.5 迁移 Migration（单向阀）
- **理论根**：沉淀速率分离（三层各自独立更新条件）+ 单向阀（只升不降）。
- **判定函数**：
  - working→consolidated：`persistence_score(m) ≥ MIGRATION_THRESHOLD` (3.0)
  - consolidated→core：`local_reorganization_trigger[m] ≥ LOCAL_REORG_THRESHOLD` (2)
  - **单向性（冻结）**：记忆只向上迁移，绝不回写；慢层塑形快层 via 检索，不 via 回写。

### 1.6 淘汰 Eviction
- **理论根**：工作层容量有限（快层高周转率 = 沉淀速率分离的工程体现）。
- **判定函数**：当 working 层 size > `WORKING_CAPACITY` (50)，淘汰 `persistence_score` 最低者。

---

## 2. Phase 1 可证伪命题（Theory → Implementation）

> **若迁移规则 = Persistence（外部验证驱动），则系统能稳定产生符合该规则预期的动力学轨迹**：
> 记忆在累积到足够外部验证后升层、未获检验者停留或淘汰、且无任何记忆违反单向阀。

本协议**仅证明实现忠实于理论设计**，不证明 Persistence 优于 Frequency，更不证明约束场理论正确。
若 Evidence 显示实现偏离（如触发信号与规则不符、单向阀被破），那是实现 bug 或协议定义漏洞，不是理论证伪。

---

## 3. 证据来源与反身性防护（防污染）

- **允许来源（计入 EV）**：真实用户对话输入；提供的外部语料（LoCoMo / 构造语料 / 公开数据集）；真实环境事件。
- **禁止来源（绝不计入 EV）**：
  - 系统/LLM 自身生成的任何文本（回复、自我提问、摘要、复述）；
  - 实验者为强制触发某记忆而插入的近重复句；
  - 因系统 prompting 诱导出的用户输入。
- 这是原则 B / 反身性条件的操作红线：一旦 EV 可被系统自身消除或诱导，选择压力就退化为内部自循环（约束场理论 RLHF 退化原型），实验即作废。

---

## 4. 实验控制变量（固定，属控制而非理论映射）

- **LLM 同源**：抽取 / 冲突判定 / 回复（Phase 2）**必须同源同一模型**（控制变量，否则引入新变量）。
- **Temperature = 0.0**：所有 LLM 调用固定，保证可复现、降低随机性对判定函数的影响。
- **Prompt 冻结**：抽取 Prompt、冲突三选一 Prompt **冻结措辞**，见附录 A，运行期不得改。
- **嵌入模型**：Phase 1 用 `all-MiniLM-L6-v2`（已知英文模型，中文阈值待 Phase 3 sweep；当前只验证"动力学是否发生"，不验证"中文语义精度"）。
- **随机性**：合成驱动（dev_simulate）确定性；真实驱动（run_corpus）仅依赖语料顺序。

---

## 5. Phase 3 基础（此处仅冻结映射，执行在后）

- **理论根**：约束场理论"长期存续结构的选择压力不能由结构自身完全控制"。
- **External Selection（Persistence 模式）**：迁移由**环境**产生的选择压力驱动（外部验证权重 1.0）。预测：产生受环境约束的稳定结构。
- **Internal Selection（Frequency 模式）**：迁移由**系统内部**产生的选择压力驱动（仅用 internal_activation 次数，忽略外部验证权重差异）。预测：退化为内部自循环，产生易被破坏的不稳定结构。
- **比较器（冻结）**：同语料两模式，**唯一变更 = Migration Rule（选择压力来源）**，其余全同。比较对象不是"留下多少记忆"，而是"存活记忆 vs **演化中的外部世界**后期发展"的一致性（Adaptive System 框架）。
- **注**：Phase 3 比较的是**选择压力来源**（Internal vs External Selection），Persistence/Frequency 只是其两种实现；若未来换其它实现仍属 External Selection，理论依旧成立。

---

## 附录 A：冻结的 Prompt 措辞（运行期不得改）
- 抽取 Prompt（来自 `extraction.py`）：「从以下用户输入中提取值得长期保留的、简短且原子化的事实。只输出 JSON 字符串数组；没有事实则输出 []。用户输入：<input>」
- 冲突三选一 Prompt（来自 `reorganization.py`）：「记忆A：<new> 记忆B：<old> 这两条记忆的关系是什么？请只回答一个词：合并、矛盾 或 无关。」+ system_prompt「你是严格的记忆一致性裁判。只依据两条记忆的字面语义判断，不推测隐含意图。若它们断言了彼此不相容的事实，答'矛盾'；若它们表达同一事实的不同表述，答'合并'；否则答'无关'。」

## 附录 B：常量表（来自 config.py，冻结）
```
EXTERNAL_VALIDATION_THRESHOLD = 0.85
INTERNAL_ACTIVATION_THRESHOLD = 0.60
REORG_SIMILARITY_THRESHOLD   = 0.90
MIGRATION_THRESHOLD          = 3.0
LOCAL_REORG_THRESHOLD        = 2
WORKING_CAPACITY            = 50
CONSOLIDATED_CAPACITY       = 200
EXTERNAL_VALIDATION_WEIGHT  = 1.0
INTERNAL_ACTIVATION_WEIGHT  = 1/e
EMBEDDING_MODEL             = "all-MiniLM-L6-v2"
WORKING_PROMOTION_STRATEGY  = "persistence"   # Phase 3 切 "frequency"
```

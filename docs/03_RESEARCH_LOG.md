# 03 · RESEARCH LOG（研究过程 / 数小时级）

> 本文件是科研过程记录，不是长期事实。记录：讨论脉络、GPT / DeepSeek 评审、agent 的自我纠正、关键决策与失败。
> 理论公理在 `00_THEORY.md`；冻结协议在 `01_PROTOCOL_v3.md`；当前实现在 `02_IMPLEMENTATION.md`。

## 2026-07-13 研究脉络（一日内的关键转向）
1. **初始状态**：agent 把项目当"做一个更好用的记忆系统"推进（接真实 LLM、检索增强回复、合并整合、换中文嵌入）。
2. **PI 纠偏（GPT 转述）**：真正实验对象是原则 A/B，不是 Memory；三层/检索/回复是让 A/B 可操作化的脚手架；每加功能问"提高系统能力 or 提高理论可验证性"。
3. **Trajectory Analyzer 落地**：把 §九 日志重建成 per-memory Memory Trajectory（分析单元从 Event → Trajectory）。GPT 评"方向正确，但是 System Verification 不是 Theory Validation"。
4. **确认偏误护栏**：删掉初版报告里"Persistence 主导 / 100% 与假设一致"等结论性话术（GPT 指出那是代码定义非实验发现）。分析器定位收紧为"描述给定规则下系统产生的动力学（Rule→Dynamics）"。
5. **原则 C + 三层验证框架**：GPT 提出"实验协议也是理论的一部分"；把 Phase 1/2/3 映射为 Theory→Implementation / Implementation→Dynamics / Theory A vs B→Different Dynamics。
6. **约束场理论接入**：PI 给《3》《5》两份文档，确认根 = 约束场理论，原则 A/B 是其推论；Phase 3 被赋予"Internal vs External Selection"的精确含义。
7. **协议起草**：依 GPT"操作化 / 判定函数"建议，写出 `01_PROTOCOL_v1.md`（EV / IA / Persistence / Conflict / Migration 的布尔判定函数 + 反身性红线 + 控制变量）。
8. **四层知识分离（本轮）**：GPT 指出项目记忆把 Theory / Protocol / Implementation / Research Log 混写，违反"沉淀速率分离"；建议拆 00/01/02/03。PI 同意。

## 2026-07-14 EV/IA 互斥 → 协议升 v2（PI 决策 + 外部评审融合）
- **背景**：Claude 尚未收到本项目的最新进展（PI 计划待项目推进到一定阶段后，一次性将全部代码文件发给他评审），因此他基于较早的 MVP 设计文档阶段认知给出建议：把 EV/IA 从「重叠」改为「互斥」，并附三份建议：① 协议文档指令（删重叠声明、改互斥）② 代码评审（确认重叠是唯一必改项，性能提示归 v0.2）③ 精确改码（含 `total_activation` + Frequency 指向它）。
- **技术有效部分**：Claude 抓到 v1 内部矛盾——§1.2 形式化定义写 `IA = sim≥0.60 AND NOT EV`（互斥），但「重叠声明」警告说两者同时 +1（重叠），代码按重叠实现。矛盾真实存在。
- **漂移风险（已识破）**：Claude 未收到协议/理论层文档（PI 尚未同步进展），其"重叠声明"本就是 v1 刻意冻结"防日后重新解释"的条款；他在只看到部分代码的旧认知下 reinterpret，正是 PI 反复预警的漂移样本——即便他本人无措，流程上也不能让"未拿到冻结协议的人"在协议层直接决策。
- **PI 决策（选 B）**：采纳互斥，但**升 v2 不改静默 v1**——严守"改协议 = 升 vN"铁律（符合关键不变量）。因当前零真实 Evidence，切换成本为零。
- **理论理由（PI 审议）**：EV（环境独立确认）与 IA（系统内部关联发现）是不同性质事件；cosine≥0.85 必然≥0.60 仅是检测机制数学副产物，非事件具有双重理论性质。互斥保证 persistence_score 可精确归因（外部 vs 内部压力），且阈值 3.0 语义不变（≈3 次纯外部验证）。
- **关键融合（agent 拍板，已向 PI 报备）**：Claude建议1 字面测试改法（仅把断言改为 `IA==0 and EV==3`）会让 `test_frequency_control_promotes_by_activation_count` 的 layer 升层断言崩——互斥后 "fact"×3 只拿 EV、IA=0，而原 Frequency 策略按 `internal_activation` 升层升不上去。采用 Claude建议3 的 `total_activation` 方案（Frequency 计"一切语义命中 ≥0.60，不区分来源"），正合 PI"Frequency 不复用 IA、用独立计数器"论述，语义一致、非私自加功能。
- **落地与验证**：`activation.py` 两 if→if-elif（顺带修 EV 命中不入 activated 列表的原 bug）；`models.py` 加 `total_activation` + `frequency_score` 改返回它；`promotion.py` Frequency 指向 `frequency_score`；测试 line 77 改 `IA==0 and EV==3`；docs 复制 v1→v2 并改标题/版本/TL;DR/§1.2/§5，v1 加弃用注，00/02/03 指针 v1→v2。`uv run pytest` → 11/11 通过；`dev_simulate.py` 正常（4× working→consolidated、1× consolidated→core）。
- **未动**：Claude建议2 的性能提示（每轮重编码全部候选记忆）→ 归 v0.2，本次不动。
- **过程教训**：外部评审者即便尚未拿到最新进展、基于旧认知给建议，也可能戳中真实不一致（v1 自相矛盾）。正确处理方式 = 不静默采纳、不静默否决，而是交 PI 按理论决策并升版本，而非在冻结文件上打补丁。

## 2026-07-14（续）v3 阈值校准 + Phase 1 真实全链路跑通

- **v3 决策背景**：Claude 诊断抓到真实问题——12 句语料 0 迁移，根因是真实 LLM 把 4 句 badminton 提成了 5 条独立记忆（**碎片化**），信号分散。他提"写入前去重 + EV 0.85→0.80"。PI 识破：去重是 v2 没有的新控制变量、EV 0.85 是冻结常量，且实测余弦显示二者耦合在 ~0.80（0.818 这对句既不会被 0.85 去重也不会判 EV）。决策：**升 v3 正式校准**（不静默改冻结变量）。
- **v3 落地**：`01_PROTOCOL_v3.md`（EV 0.80 + 新增 `DEDUP_SIMILARITY_THRESHOLD=0.80` §1.7 + 提取同语言 + 附录常量表更新）；`pipeline.py` 提取后、写入前去重（命中跳写、信号由激活登记到既有记忆）；`config.py` 降 EV 加去重常量。踩 bug（`existing_vecs` 是 ndarray 不能 append，改 `.tolist()`）已修。`uv run pytest` → 11/11 通过。重跑 12 句：badminton 5→2 条收敛，主记忆 1.74→2.37，仍差 0.63 未升层。
- **Phase 1 全链路跑通（26 句长语料）**：Claude 建议"先跑通快→中再谈外部基准"。写 `corpus_phase1.txt`（badminton×6 / Mochi×6+矛盾×2 / 噪声）。首次跑撞 Gemini 免费层 15 req/min 限流（429），给 `OpenAICompatibleClient.call_llm` 加**指数退避重试**（8→16→32s，≤6 次）后跑完——纯 I/O 韧性，不影响理论行为。
- **结果**：54 事件 = 2 EV + 22 IA + 8 去重跳过 + 21 写入 + **1 次 working→consolidated（badminton 3.10）**。这是**真实语义环境下第一例快→中迁移**，核心机制证活。
- **三通过标准（Claude 定的 smoke test）**：① badminton 升巩固层 ✓ ② Mochi 升层 + 矛盾触发重组 ✗（Mochi 措辞多样碎成多条、主记忆 persistence 1.84/3.0 未跨阈；矛盾句或去重跳过或相似度<0.90 未触发重组，local_reorganization=0）③ 噪声全停快层 ✓。
- **关键发现（可证伪的 Phase 1 动力学，非 bug）**：(a) 迁移对**输入措辞语义冗余度高度敏感**——近义复述收敛升层，多样表述碎片化不升层；(b) 重组（REORG_SIMILARITY=0.90）只捕**近重复**记忆间矛盾，不捕语义相关但表述不同的逻辑矛盾（"playful" vs "doesn't like touched"）。是否需拓宽重组是 Phase 2/3 设计议题，非临时修。

## 2026-07-14 · Phase 3 对照实验（Route 1：persistence vs frequency）

- **决策**：Phase 1 收尾后，Claude 提三条路线（① Phase 3 对照实验 ② LoCoMo 基准 ③ Phase 2 Reply 闭环），PI 选 **①**。理由：代码已有 `FrequencyPromotionStrategy` + `Config.WORKING_PROMOTION_STRATEGY` 开关，工程量近零；产出直接支撑核心命题"同一系统同一数据，只切迁移规则产生不同动力学"。LoCoMo/Phase 2 延后。
- **方法（守住协议 §5 比较器）**：用同一份 `corpus_phase1.txt`（26 句），仅切 `--strategy` 跑两遍——`persistence`（External Selection）/ `frequency`（Internal Selection）。两遍提取的记忆集**完全一致**（各 21 条，交集 21，无独有偶），证明**唯一变量 = Migration Rule**，比较器有效（无提取非确定性污染）。
- **结果**：
  - persistence（外部选择）：**升巩固层 1 次**——"The user enjoys playing badminton on weekends"（EV=2, IA=3, total=5, persist=3.10, freq=5）。唯一升层记忆**带外部验证**。
  - frequency（内部选择）：**升巩固层 4 次**——上述 badminton + 另外 3 条 **EV 全为 0** 的记忆："User loves badminton"(IA=3,persist=1.10)、"The user adopted a cat named Mochi"(IA=5,persist=1.84)、"Mochi the cat is playful and energetic"(IA=4,persist=1.47)。这 3 条恰是 persistence 跑里**同一记忆对象**停留快层者（persist 1.10/1.84/1.47，均 <3.0）。
- **理论解读（只描述，不越权判定）**：External Selection 升层的记忆全部 EV>0（受环境约束、结构稳定）；Internal Selection 把**零外部验证、选择压力完全来自内部自循环**的记忆也推上巩固层——正是 §5 预测的"退化为内部自循环、产生易被破坏的不稳定结构"。3 条 EV=0 记忆 = 结构存续完全由自身检索频率决定，违反"选择压力不能由结构自身完全控制"。这是约束场理论在真实语义环境下的 **Phase 3 先导实验（pilot）**——稳定性尚未测量（协议 §5 真比较器未执行；见下方 GLM 审查降级）。
- **边界（须如实记）**：本实验只是 Phase 3 的第一片（策略切换的动力学差异）。协议 §5 完整的 Phase 3 还要求"世界演化"语料，比较存活记忆 vs 后期外部发展的**一致性**（Adaptive System 框架）——该深层对照需专门设计的演化语料，本轮未做，列入待议。
- **Claude 角色**：Route 1 建议正确（近零工程、直击核心命题），其"同系统同数据只切迁移规则"表述与协议 §5 比较器一致。他未读过本段研究日志，但给出的方法论恰与既有纪律吻合。

## 2026-07-14（续3）GLM 证伪审查与发布前降级

- **审查来源**：GLM 对理论/协议/实现/测试/语料完成系统性证伪审查，列出 17 条漏洞。Claude 逐条分类为三桶：桶一(真问题必须处理 4 条) / 桶二(真观察写进协议或声明 3 条) / 桶三(不采纳 5 条，附理由)。
- **桶一(已行动)**：
  - **#13 淘汰逻辑 bug(已修)**：`enforce_working_capacity` 在 frequency 模式仍用 `persistence_score` 淘汰，污染纯 Internal Selection 条件。改为跟随当前策略 score（persistence→persistence_score / frequency→frequency_score）。本次实验 21 条<50 容量，淘汰未触发，既有结果不受影响。
  - **#8/#9 措辞过强(已降级)**：实验只测"谁被升层"，从未做扰动/存活率检验，"稳定 vs 易被破坏"标签无经验支撑。故"首份 Phase 3 证据"全部降级为"Phase 3 先导实验（pilot）"，并声明协议 §5 真比较器（存活记忆 vs 演化世界一致性）未执行。
  - **#1 阈值耦合(声明+反驳并存)**：纯 IA 记忆在 frequency 下 3 次升层、persistence 下需约 8 次，差异部分可归因阈值数值；但频率策略语义本就是"不区分来源"，阈值差异是策略定义一部分。诚实处理：声明耦合 + 把"阈值 sweep 下结论是否稳健"列 Future Work。
  - **#5 语料构造偏误(成立，接 LoCoMo 论据)**：手工构造语料预先决定结果形状，MVP 可接受但须声明，并作为下一步外部语料的动机。
- **桶二(已写入声明)**：
  - **#11 EV 与 Dedup 共用 0.80**：在协议 §1.7 显式命名为"记忆同一性阈值(Memory Identity Threshold)"——同一性标准统一是设计决定而非混杂；与 GPT 此前提的"Memory Identity"收敛。
  - **#15 两个表征空间**：EV 比"原始输入 vs 提取记忆"、dedup 比"提取物 vs 提取物"，同一 0.80 在不同分布上使用——记开放问题，MVP 不修。
  - **#7 数据目录预清理**：`run_corpus.py` 加 `--clean` 开关 + 非空警告，防状态污染。
- **桶三(不采纳，理由)**：#3(提取一致非逻辑必然，21=21 是经验事实，且 #3 与 #6 自相矛盾) / #10(Phase 1 从不声称检验理论，v2→v3 碎片化即其失败实例) / #14(1/e 自由参数已在设计文档与开放问题声明) / #4#6#17(n=1、非位级确定性、因果方向——均为 MVP 已知边界) / #16(与 #8 同源，措辞收窄后消解)。
- **结论收窄(关键)**：GLM 结语"至多证明了两个不等价分数函数产生不同升层计数这一平凡事实"是修辞过度；正确收窄版——机制差异确实被证明(分歧方向与理论对 Internal Selection 机制描述相符，受阈值自由度污染)，但"哪种结构更稳定"未被测量。前者值得写进求职材料，后者是 Phase 3 完整版任务。证伪审查的正确用法是替结论修剪到刚好能防御的尺寸。

## 2026-07-14（续4）GLM 第二轮审查 + Claude 认错 + 阈值回放

- **GLM 第二轮质量更高**——不再撒网，改查修补接缝。逐条回应，Claude 在 **R1 认错**（关键）：
  - **R1（Claude 认错）**：第一轮"frequency 对 IA 要求 8 次就变成 persistence 变体"是**错的**。score 函数（是否区分来源）与阈值数值（多少分升层）是**两个独立自由度**——frequency 阈值设为 8 仍是 frequency 策略、只是更严格，而那样 3 条 EV=0 记忆（freq=3 或 4）全部无法升层，头条结果消失。原报告 §④"两头占"（既称阈值差异是策略定义一部分、又称需 sweep）的辩护断裂，已删。
  - **R2**：§②"升层分歧只能来自策略切换"改为"只能来自策略切换（score函数+阈值作为整体），无法进一步归因选择压力来源的单独贡献"。
  - **R3（采纳 GLM 降级终点）**：原"分歧方向与理论预测一致"过称。收紧为"支持'比较器管道可运行且能产生与理论机制描述相符的分歧'，而非'分歧方向已被证明与理论一致'"；保留"frequency升EV=0/persistence不升 与 Internal Selection 机制相符"，但紧跟"该相符性受阈值自由度污染、核心后果(不稳定性)未测量"。
  - **R4-R7（机械修复）**：R4 新增"无去重(v2)零迁移、可观测性受去重门控"限制；R5 补 `test_capacity_evicts_lowest_frequency_score`（frequency 淘汰跟随 frequency_score，捕捉 #13 回归）；R6 复现命令加 `--clean`；R7 复核——`:43` 早已是"Phase 3 先导实验（pilot）"（第一轮已降级），无残留。
- **最有价值的动作：阈值敏感性离线回放（零 LLM 成本）**。R1 暴露"结论是否对阈值敏感"可离线回答——逐记忆 EV/IA/total 已持久化在 `data/phase3_{persist,freq}/`。写 `tools/threshold_sweep.py`：读取两遍计数、验证 21=21 可复现（逐记忆一致，经验事实非逻辑必然），在 persistence×frequency 阈值网格重算升层判定。结果：**发散区是连续矩形** Tp∈[2.0,5.0]×Tf∈[2,5]（28/56=50% 网格，含冻结配置 3.0/3），证明头条分歧非单点巧合；仅在 Tf≥6（本语料最大激活=5，全不升层）或 Tp≤1.84（persistence 自身背叛 External Selection）时消失。输出 `logs/threshold_sweep.json`，相图与解读写入 `EXPERIMENT_REPORT.md §⑥`。
- **v0.1 形态因此进化为**：单点结果 + 阈值敏感性分析 + 诚实边界——GLM 两轮回溯完整转化为报告的防御纵深。此轮修正重新定稿 v0.1 tag（旧冻结 commit d064bca 与上一轮 67fc66d 均保留在 history 可审计），仍未 push，待 PI 确认。

## Agent 自我认领的历史漂移（已纠正）
- 把"接真实 LLM"话术为"系统能工作"（能力视角，非理论视角）。
- 推"检索增强回复演示"理由为演示 / 体验（标准漂移样本）。
- 建议"合并 / 矛盾真整合"会污染要观测 trigger 信号且违反 MVP 边界。
- 把"换中文嵌入 + 标阈值"当工程优化（阈值实为 Phase 3 要 sweep 的超参）。

## 评审中曾被判定为"挂起 / 非结构增量"的点
- Predictor（反事实预测）、Trigger 机制解释、LLM Invariance —— GPT 自认漂移，当前推演场删除它们不变，挂起至 Phase 3 后。
- 分析器可视化 / HTML 细节打磨 —— 工程优化区，停止。

## 漂移探测器（Π 拆解自检）
- 每提一个"改进"，问"删掉它，当前推演场变不变？"不变 = 结构回声 → 挂起。
- 纪律：连续两轮无新增理论变量 → 默认进入实验阶段，不再讨论架构。

## 开放问题
- 语料问题待议：Phase 3 需"世界会演化"的语料；待定用改造公开基准（LoCoMo 类）还是自建。
- v0.2 路线（未做）：分析单元从 Memory 提升到 Constraint 网络；跨 LLM 一致性（LLM Invariance）等。

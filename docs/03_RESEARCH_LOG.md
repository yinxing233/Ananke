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

## GLM 第三轮 / Claude 复核 + 强/弱双判据 + 路径无关性（v0.1 最终收尾）

Claude 核验 round-2 数字对上（badminton pscore=3.1036、Mochi pscore=1.839、Tp≥3.5 时 persistence 升 0 条），但指出两个 push 前必修的小问题：

- **问题1（相图一半是退化格，50% 撑不住）**：原发散判据"frequency 升≥1 EV=0 且 persistence 升 0 EV=0"在 persistence 整段瘫痪（Tp≥3.5）时被平凡满足——Tp∈[3.5,5.0] 四行（16/28 格）是"persistence 不工作"而非"两系统分歧"。GLM 第三轮会精确打这里。
  - **修法**：加**强发散判据** = persistence 升≥1 EV>0 **且** frequency 升≥1 EV=0（两系统都在跑、真实分歧）。结果：弱发散 Tp∈[2.0,5.0]×Tf∈[2,5]=28/56=50%（含退化格）；**强发散 Tp∈[2.0,3.0]×Tf∈[2,5]=12/56≈21%（防御得住）**，两者都含冻结配置 (3.0,3)。报告 §⑥ 改为双数字表述+解释退化格区别。21% 比 50% 弱，但是经得起第三轮审查的 21%。
- **问题2（回放路径无关性假设未声明，但已有经验证据）**：回放"复用计数、只变阈值"隐含"计数对阈值路径无关"。本系统按构造成立（activation/dedup 扫 working+consolidated 两层、升层早晚不改计数、淘汰未触发 21<50）；且**直接经验证据**：persist 与 freq 两遍升层时点/条数不同（1 vs 4）但逐记忆 (EV,IA,total) 计数逐字节一致（`per_memory_count_match=true`）。脚本 docstring + 报告 §⑥ 显式声明 + 该经验论证，漏洞→预先封堵边界。
- **工具改动**：`tools/threshold_sweep.py` 增 `weak_cell`/`strong_cell`/`region_of`，打印三级相图（S/w/.）与双区域百分比，json 输出 `weak_*`/`strong_*`/`path_independence` 字段（删模糊的 `divergence_region`）。
- **文档同步**：RELEASE §已知限制、报告 §④/§⑤/§⑥ 全改为双数字；研究日志本轮不回改 round-2 条目（历史日志保持时序），仅追加本节的强/弱澄清。
- **收尾决策（PI + GPT 同意）**：v0.1 经三轮完整审查消化，第三轮起边际收益低于日历成本，剩余问题全归 Future Work；本轮回放修正后定稿 v0.1 并 push。

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

## 2026-07-22~24 v4 召回-分类落地 + 两级缓存（实验仪器前提）

- **背景**：v4 协议草案（§2.2 召回-分类两段式 vs v3 余弦阈值判定）代码已完成、待冒烟。本轮重心从"协议设计"转向"让实验可重放、可审计"——因为主测量 D=(P\F)∪(F\P) 对提取/分类非确定性极度敏感，噪声会淹没"策略差"。
- **Fable5 审查四项漂移修正（2026-07-22，冒烟前完成）**：
  1. **漂移1（最重，理论倒置）**：原 `conflict_trigger≥2 → 升 CORE` 是 v3「矛盾计为验证」EV 污染在第二道闸复活。改为 `conflict_trigger>0` = **CORE 晋升阻断器**（CORE 装经受住检验者，被矛盾=检验失败）。详见协议 §2.5。
  2. **漂移2（更新能力）**：contradict 命中时新断言**写入快层 + 与受体建双向 conflict 链接**（系统须能更新世界状态），否则验证阶段命中率在含改口事实上系统性失真。mergeable 仍不写（冗余，留债）。
  3. **漂移3（PI 追认）**：中→慢闸对两策略走同一逻辑，对分歧集 D 零贡献；**追认 D 仅测 working→consolidated 第一道闸**，写入 §6。
  4. **漂移4（协议化）**：跨运行同一性判据「归一化内容比对」规则（小写+去标点+折叠空白）成文入 §6，`tools/divergence_analysis._norm` 对齐。
- **Claude 三段结构审查（B系列裁决 + 操作红线）**：对两级缓存代码做纯 review 后，Claude 裁决 B 系列**全部照修但等级重排**——B3（prompt 模板 SHA1 哈希自动失效）被低估，它是三项里**唯一能无声毁掉主实验数据**的（改 prompt 不失效缓存 → 混合版本结果污染 D）；C2（空响应缓存为 unrelated）藏规约缺陷（传输失败与语义判定被折叠）。并补**操作红线**：缓存移出 data/ 与 data/ 平级存放、`--clean` 或任何清理**不得触碰缓存目录**（缓存是已付费 LLM 调用，253 轮 Qwen 全在里面）；D 内置为脚本默认（重放默认跑满原始轮数，跑满为显式 opt-in）。
- **执行（5 处修复 B1+B2+B3+C1/C2+D）**：B1（§6 归一化抽到 `text_norm.py` 单一来源）/ B2（model_tag 防呆）/ B3（prompt 模板哈希自动失效）/ C1+C2（只缓存合法解析标签）/ D（turn 字段内置 + 平级 `cache/` + `--clean` 红线）。全量 43 passed。
- **排查中发现的真实 bug（原 review 摘要未覆盖，已修）**：
  1. **迁移 key 不兼容（红线级）**：旧 253 轮缓存 key 用 prompt 版本号 `"v1"`，B3 改哈希后 key 变 `model_tag|<hash>|...`；若只搬文件不改 key，重放 1-253 全部 miss → 重烧 253 轮额度。修复：`migrate_legacy_cache` 接收当前 prompt 模板、迁移时重写 version 段为哈希段（8-hex 检测区分新旧、畸形/未知类原样保留）。验证旧 `openai-compatible|deepseek-chat|v1|extraction|user likes cats` → `...|8019d93a|...` 命中零 API；幂等。
  2. **B2 防呆解析 bug**：`_cache_model_tag` 用 `key.split("|",1)[0]` 取 model_tag，但 model_tag 含 `|`（如 `openai-compatible|deepseek-chat`）→ 截断后永不等真实 tag → 默认配置下合理重放被误 `exit(2)`。改 key 固定末三段（hash/category/input 均不含 `|`）截断后拼回即完整 model_tag。
- **沉淀为实验仪器纪律**：两级缓存不是"省钱优化"，是测量前提——它把 D 从"策略差+LLM噪声"退化为"纯策略差"，并把"续跑"升级为"可审计重放"（缓存重放前 N 轮须与原始逐事件一致，否则暴露非确定性）。导出 50 对标注模板（方案甲 NLI cross-encoder vs 方案乙 LLM 五选一，人工标注准确率拍板）亦建于此时，待完整语料跑完后使用（`tools/export_annotation_pairs.py`）。
- **未决（留待 v4 冻结）**：真实 LLM 冒烟（换额度续跑 254-419 + replay 等价性验证）、`RESEARCH_CONJECTURES.md` 升格、`§8` 冻结条件填写 → MVP v0.2 tag。

## 2026-07-28 · 代码漂移审计后：B1–B7 裁决冻结候选

- **主张层级重新锁定**：v0.2 的直接观测对象是 C2 的 v4 操作化——第一道闸分歧集 D 上，
  persistence / frequency 两套完整选择制度的 reference-grounded evidence 命中率。原则 B、
  约束场理论整体与闭环慢→快塑形不直接检验。
- **pre-audit 基线保全**：把审计前已有代码/工具、文档归档和已跟踪轨迹报告分别提交为
  `05205a9` / `29e22b6` / `2c780f8`，避免后续裁决 commit 夹带无来源改动。
  2026-07-28 实际重跑测试为 `43 passed`。
- **旧 253 轮降级**：当前 `cache/` 与 `data/cache/` 均不存在；conv-26 工作层 52>容量 50，
  与非原子部分轮一致。故“续跑 254–419”方案作废，旧状态/日志只作探索碎片；修复后从第 1
  轮重跑。
- **替代此前未决方案**：上一节历史记录中的“续跑 254–419”与
  “直接把 RESEARCH_CONJECTURES.md 升格”均被本轮事实和裁决取代。正式承诺将由新建的
  `PREREGISTRATION.md` 承担，历史文字保留只为呈现决策演进。
- **探索日志指纹**：`logs/conv26_events.jsonl` 共 949 条，SHA256 =
  `040E4AC4DE0DE3674DD9CE0B04B635D1CEA3BB18C910EB76779C76CBF6E337F7`。
  事件不含 session_id，不能据此机械证明探索数据隔离。
- **LoCoMo 库存闭合**：源文件含 10 条对话、272 sessions、5,882 个双-speaker 轮次、1,986 QA。
  conv-26 已用于探索；其余 9 条为验证候选，但本轮不替 PI 选择保留集。
- **B1–B7 裁决**：
  1. B1：每个 distinct session 对同一记忆至多贡献 1 次 EV；guided 输入不占资格；
  2. B2：`system_guided` 保留为 v0.2 恒 False 的未启用接口；
  3. B3：CORE 进入 top-1 召回；同分 `CORE>CONSOLIDATED>WORKING`；四关系只计数/留痕，
     不让 CORE 进入晋升、淘汰、降级或裁决；
  4. B4：P/F 是完整选择制度比较，不声称 score 单因子效应；实验比较器移出 Theory；
  5. B5：不设 EV=0 硬禁令，保留推测 2 的非平凡机制对照；
  6. B6：judge 必须拿 question + reference_fact；部分=0.5；失败剔除计数，>5% 整体无效；
  7. B7：未知分类响应重试后硬失败，依赖轮级原子性，不再降级 unrelated。
- **本轮边界**：只形成文档冻结候选，不修改 Python，不运行正式语料，不锁定验证 ID，不创建
  正式 `PREREGISTRATION.md`，协议 v4 仍为草案。PI 验收后再进入 Red → Green 实现阶段。

## 2026-07-30 · PI 验收 B1–B7 裁决集

- PI 验收通过 `DECISIONS_v0.2_freeze.md` 的完整裁决集，包括 B1–B7、三项补充裁决
  （CORE 同分优先、guided 输入不占 EV 资格、来源元数据双轨）以及 B1 对
  `total_activation` 来源语义的澄清。
- 自记录本次验收的提交起，B1–B7 成为实现代理必须遵守的冻结裁决；后续改变任一裁决必须
  新增带日期的修订记录，不得静默改写。
- 本次验收只改变文档效力状态，不修改 Python，不表示 B1–B7 已实现，也不表示协议 v4
  已正式冻结；下一阶段按 A3 → A1/B6 → A2/B7 → A4/A5/B2 → B1 → B3 顺序执行
  Red → Green 行为切片。

## 2026-07-30 · B1–B7 Red → Green 实现回执

- **依赖链与提交**：A3 `cb57938` → A1/B6 `7806382` → A2/B7 `05e063f` →
  A4/A5/B2 `7825d28` → B1 `3858de1` → B3 `4319f9c`；每段先运行失败测试确认 Red，
  再做最小实现、全量回归并独立提交。
- **阶段 7 协议对照审查**发现并闭合三类同条款缺口（`0699745`）：日志部分落盘的回滚边缘、
  三层文件准备失败时的原文件保护；`unscored` 记忆必须保留在 P/F 升层集合但退出命中率分母；
  非法缓存/自定义分类标签必须 fail closed。三类均先补失败测试，不改变 B1–B7。
- **最终确定性验收**：`uv run pytest -q` → `70 passed`；
  `uv run python -m compileall -q ananke tools tests` → 通过。
- **红线核对**：未修改 persistence 公式/阈值、CORE 晋升/淘汰/降级规则或 P/F 制度定义；
  未给 runner 增加 `system_guided=True` 来源；未选择验证 ID；未修改推测原文；未运行正式语料。
- **仍未闭合**：本轮执行者完成了逐条协议对照，但仍需新上下文的独立只读复核；此外
  `R_recall`、分类器甲/乙、50 对人工锚点、真实冒烟、验证集锁定与正式预登记均未完成。
  因此协议 v4 继续保持草案状态。

## 2026-08-08 · 路径 A 选择与真实 API 前停止点

- **PI 裁决**：为避免实验仪器继续增殖，选择路径 A——接受小额付费，保持逐轮提取 + LLM
  五分类的简单仪器。明确不实现批量提取、本地 NLI、RPD 账本与真正检查点；先用已暴露的
  `conv-26` 小样本取得真实成本。
- **协议修订**：top-1 受体选定后，归一化内容非空且完全相同的 pair 确定性判为 duplicate，
  不调用分类 API；对 P/F 对称执行，并记录 `rule_based_duplicate` 与分类来源。该规则只覆盖 exact，
  未变更既有 `R_RECALL=0.65` 短路，也未加入低相似度阈值。
- **仪器收紧**：B6 的 0.5 改为不可配置常量；关系/judge 输出上限均为 6 tokens；B7 三次重试
  限定于解析失败，传输/鉴权/配置异常保留身份；正式 judge 对未知/同家族 fail closed。
- **成本与重放审计**：新增 append-only 请求计量，区分逻辑调用与包括 429 在内的实际 HTTP
  尝试，记录 provider token usage；正式模式禁用缓存绕过并以独占锁强制 P/F 串行。
- **诚实 preflight**：提取 miss 可由语料与缓存键精确计算；分类次数因提取输出和记忆状态演化
  只能在校准后实测。完整 `conv-26` 离线预检为 419 轮/19 sessions/419 个确定提取 miss
  （至少 419 次逻辑提取调用；实际 HTTP 受解析/429 重试影响）、
  462,301 提示字符（粗略 115,576–154,101 input tokens）；分类请求保持 unknown。
- **100 轮校准输入**：从同一已暴露对话按原顺序取前 100 轮（6 sessions）。正式保护 preflight
  通过：100 个确定提取 miss（至少 100 次逻辑提取调用；实际 HTTP 待测）、110,695 提示字符
  （粗略 27,674–36,899 input tokens）。当前配置
  为真实驱动端、缓存开启、密钥存在、temperature=0；预检前后 `cache/` 均不存在，usage 日志为 0。
  子集逐行等于完整语料前 100 行，SHA256 =
  `E3ACF574E06A375117A7C026792909EC1EC05FED0117F4330E7C7BC98A240A98`。
- **验证**：确定性测试 `90 passed`；`python -m compileall -q ananke tools tests`、
  `run_corpus.py --help`、`evaluate.py --help` 与 `git diff --check` 均通过。最终完整/100 轮保护
  preflight 后仍为 `cache_exists=False`、`usage_log_count=0`、`formal_lock_count=0`。
- **停止点**：未创建 LLM 客户端，未发任何真实 API 请求。下一动作才是 100 轮付费校准；须先
  由操作者明确跨过 [`CALIBRATION_PATH_A.md`](./CALIBRATION_PATH_A.md) 的 STOP 标记。

## 2026-08-08（下午）· 守护断言纪律（从 dev_simulate 静默断裂教训立定）

- **事件**：全量一致性审查发现 `tools/dev_simulate.py` 演示链**静默断裂**。8-08 exact-dup
  规则（normalized exact duplicate）使 pipeline 对逐字相等的 pair 走确定性
  `rule_based_duplicate`、**不消耗** MockRelationClassifier 的 script 队列；STEPS 中
  6 个 dup 步骤因此被短路跳过，script 队列整体错位 → merge/contradict 链全部落空 →
  `consolidated_to_core` / `conflict_link` / `core_promotion_blocked` 三类事件缺失。
  但 docstring 与 02_IMPLEMENTATION.md 仍声称覆盖——**文档与工具行为脱节，且无任何
  测试守护**，直至审查日才被发现（若未审查，静默期会继续）。
- **病理**：这是 P0-A"协议条款无机器守护"病灶的**同构复发**，只是换到工具层。
  诚实性依赖"人肉三方对照"（文档↔代码↔测试），成本高、易漏。
- **纪律（PI 已认可，写死）**：
  1. **任何声称"覆盖事件 X / 演示路径 Y"的工具，必须自带可运行的守护断言**——
     缺失 X/Y 即非零退出（dev_simulate 已加：缺三类关键事件任一即 abort）。
  2. 工具 docstring 的能力声明 = 其守护断言集的最小上界；改工具必须同步改断言，
     改断言必须同步改文档，三者任一漂移即违反纪律。
  3. **协议条款变更后，必须扫描 tools/ 下所有声称覆盖该条款的工具**，核对短路类
     新规则（如 exact-dup、fail-closed）是否会改变其脚本/队列消耗路径。
  4. 守护断言本身进 CI 或至少进常规测试清单，不依赖下一次人工审查发现。
- **观测含义**：漂移探测器（Π 拆解自检）只防"新增功能漂移"，不防"既有工具因协议
  变更静默失能"。后者须由守护断言承接——两类探测器互补，缺一不可。

## 2026-08-10–18 · 分类校准、仪器冻结与 `conv-26` P/F 完整点火

- **100 轮路径 A 校准完成**：`conv-26` 前 100 轮 persistence 真实运行结束，请求级用量、缓存、
  解析失败与状态演化均得到实测。这标志 `CALIBRATION_PATH_A.md` 的 STOP 已由 PI 明确跨过；
  该文档达到自身声明的过期触发点，待后续文档清理归档。
- **关系分类口径定稿后复跑**：12 个边界案例已由 PI 裁决，R1/R2 写入三层判定 prompt。
  2026-08-11 首次重测为 62.0% / κ=0.448；2026-08-18 点火前同 prompt 最终复跑为
  60.0% / κ=0.422，50 次调用全部成功、零解析失败。点火基线取后者，不挑选较高一次。
  duplicate 金标 5 例命中 0，contradict 金标仍为 0 样本；这是仪器边界，不是继续调 prompt 的授权。
- **点火前最小冻结**：提取 prompt、关系 prompt、协议/裁决/实现文档与判例账本指纹记入
  `docs/calibration/FREEZE_MANIFEST_v0.2.json`；对应 commit object 为
  `a969e5b4dce9df16950b631000c2a0a7cbf04461`，后由 `rescue` 分支恢复可达。
- **Persistence 完整运行**：419 轮/19 sessions，`completed=true`。事件计数：写入 673、淘汰 609、
  IA 410、局部重组 84、第一闸 14、CORE 晋升 6、`conflict_link` 5、分类解析重试 2。
  终态 W/C/CORE=50/8/6，EV 总和 0。HTTP=1,005（提取 419+关系 586），零 429、零 HTTP 错误。
- **Frequency 完整运行**：同语料同顺序 419 轮/19 sessions，`completed=true`。写入 658、淘汰 546、
  IA 418、局部重组 98、第一闸 62、CORE 晋升 17、`conflict_link` 4、分类解析重试 2。
  终态 W/C/CORE=50/45/17，EV 总和 0。提取 419/419 从 P 共享缓存命中，只产生 153 次
  relation HTTP 请求；这是串行运行顺序下的边际成本，不是 F 制度的固有优势。
- **分歧集显影**：按协议归一化内容键对齐第一闸，P=14、F=62、交集=14、P-only=0、
  F-only=48、D=48。这是真实的制度分叉，但两边 EV 都为 0：Persistence 只由 IA/e 累积，
  Frequency 由不区分来源的 `total_activation` 累积（包含 related/mergeable/contradict 等非 EV 关系事件）。
  因而分叉不能被识别为 External Selection 对 Internal Selection 的效果。
- **EV=0 的双解释不闭合**：(a) duplicate 分类器 5 例命中 0，实际 EV 可能被检测盲区吞掉；
  (b) `conv-26` 在当前提取表示下可能真的缺少跨 session duplicate。现有数据不能区分两者。
- **两项推测均不可判**：推测 1 缺 `P∖F`；推测 2 缺 `F∖P` 内 `EV>0` 子组。旧
  `divergence_analysis.py` 会把推测 1 的空集真空判为 True；PI 批准后改为
  `held / not_held / not_testable` 三态，两个推测的任一必需组为空都输出 `not_testable`。
- **全量 DeepSeek evaluate 否决**：199 probes × (14+62) = 15,124 次 judge 请求，其中重叠集会
  重复消耗 2,786 次。评判端不能创造缺失的比较组，故不运行。描述性 judge smoke 默认不做；
  如报告后续真需要，必须另批固定种子、≤500 请求的抽样。
- **conflict 计数更正**：P=181/F=384 是 `core_promotion_blocked` 重复审计事件，不是独立矛盾。
  独立 `conflict_link` 为 P=5/F=4，被持续阻断的唯一记忆为 P=1/F=2。CORE 最终为 6/17，
  故“阻断导致 CORE 趋零”未在本运行发生，但不外推为结构性风险已消失。

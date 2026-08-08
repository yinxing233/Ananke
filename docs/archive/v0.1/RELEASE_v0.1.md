# Ananke — MVP v0.1 Release（冻结快照）

> **版本**：MVP v0.1（仪器发布版本）
> **基于协议**：`01_PROTOCOL_v3.md`（实验协议 v3，EV/IA 互斥 + 写入前去重 0.80）
> **冻结日期**：2026-07-14
> **git tag**：`v0.1`

## 这是什么
Ananke 是**约束场理论（Constraint Field Theory）的实验仪器**，不是"更好用的记忆系统"。
本发布冻结的是"仪器"——代码 + 协议 v3 + 真实 LLM 下产出的 Phase 1 机制验证 / Phase 3 先导实验（pilot）。
Evidence 的判定标准 = 系统是否产生理论预测的结构形状（分层 / 外部门控 / 单向阀），
不是记忆内容对不对。

## 冻结范围（IN / OUT）

### IN（本版本承诺）
- 三层记忆（Working / Consolidated / Core）+ 单向阀迁移
- 两种可切换迁移规则：`persistence`（External Selection，默认）/ `frequency`（Internal Selection，控制组）
- 真实 LLM 接入层（Gemini / DeepSeek / OpenAI 兼容）+ 真实嵌入（all-MiniLM-L6-v2）
- 观测工具：`analyze_trajectory.py`（Memory Trajectory 报告）、`run_corpus.py`、`dev_simulate.py`、`threshold_sweep.py`（离线阈值敏感性回放）
- 真实 LLM 证据：Phase 1（快→中迁移、噪声抑制）+ Phase 3 先导实验（persistence vs frequency 管道可运行、结构差异可判别）
- 协议 v3 冻结常量（EV=0.80 / IA=0.60 / 去重=0.80 / 重组=0.90 / 迁移=3.0）

### OUT（Future Work，不在本版本，归位挂起清单）
- Memory Unit 协议化（GPT 提出，跨 LLM 对比时才生效）
- 逻辑矛盾检测（重组 0.90 只捕近重复矛盾，不捕逻辑矛盾）
- Phase 2 Reply 闭环（检索影响输出）
- LoCoMo 基准接入
- 中→慢迁移在真实 LLM 下的触发
- 被动衰减
- 反事实重要性
- 中文嵌入阈值标定（留给 Phase 3 sweep）

## 已知限制（诚实边界，GLM 证伪审查后声明）

- **阈值语义耦合（score 函数与阈值是两个独立自由度）**：persistence 阈值 3.0（对纯 IA 记忆需约 8 次激活）与 frequency 阈值 3（仅需 3 次）相差约 3 倍。但 score 函数（是否区分来源）与阈值数值（多少分升层）是**两个独立自由度**，不可捆绑辩护——若把 frequency 阈值也设为 8，它仍是 frequency 策略（仍不区分来源）、只是更严格，而那样 3 条 EV=0 记忆（freq=3 或 4）将全部无法升层，头条结果消失。单点数据无法分离"选择压力来源"与"阈值数值"各自的贡献，结论对阈值敏感。离线阈值回放见实验报告 §⑥（弱发散 50% 含退化格、强发散 21% 含冻结配置且防御得住，但仍条件于去重与阈值区间）。
- **去重机制门控了可观测性**：本结果在 v3 写入前去重（DEDUP=0.80）后的最终状态上测得。无去重（v2）时真实语料**零迁移**，结构差异根本不可观测——"可判别的结构差异"依赖去重这一控制变量。
- **语料构造偏误**：`corpus_phase1.txt` 由知情实验者手工构造（badminton 近义复述、Mochi 多样特质），升层结果形状被"措辞冗余度"预先决定，是确认偏误的结构性来源。MVP 阶段可接受（目的是验证机制能否产生差异，非测自然分布表现），但必须声明，且正是下一步接入外部语料（LoCoMo）的动机。
- **n=1、单次运行、零统计推断**：无重复实验、无置信区间；temperature=0 不保证 LLM 位级确定性。
- **两个表征空间**：EV 比较"原始输入 vs 提取记忆"，dedup 比较"提取物 vs 提取物"，同一 0.80 在两个不同相似度分布上使用（技术细节，MVP 不修，记开放问题）。

## Future Work（接 GLM 审查）

- **阈值 sweep**：在 persistence/frequency 阈值组合网格上重跑，检验结论稳健性，分离"来源加权"与"阈值数值"贡献。
- **外部语料（LoCoMo）**：用公开对话基准替代手工构造语料，消除构造偏误，测自然分布下的表现。
- **稳定性 / 扰动检验（协议 §5 真比较器）**：设计"世界演化"语料，比较存活记忆 vs 后期外部发展的一致性，测量"稳定 vs 易被破坏"标签——这是完整 Phase 3 的任务，本 MVP 未做。
- **Memory Identity 显式化（v0.2）**：把 0.80 同一性标准从隐含提升为协议一级概念，统一 EV / dedup / Memory Unit 边界。

## 复现步骤
```bash
# 1. 安装依赖
uv sync

# 2. 获取嵌入模型（data/ 已 gitignore，需本地拉取）
uv run python tools/fetch_model.py

# 3. 配置 .env（复制 .env.example，填入 LLM_API_KEY，选 gemini/deepseek）
cp .env.example .env
#   编辑 .env: USE_MOCK_LLM=false, LLM_PROVIDER=gemini, LLM_API_KEY=..., LLM_MODEL=gemini-2.0-flash,
#             EMBEDDING_MODEL=data/all-MiniLM-L6-v2

# 4. 跑 Phase 1 全链路（真实 Gemini + 本地嵌入）
uv run python tools/run_corpus.py corpus_phase1.txt --clean --log logs/real_events_p1b.jsonl --data data/real_p1b
uv run python tools/analyze_trajectory.py --log logs/real_events_p1b.jsonl --data data/real_p1b

# 5. 跑 Phase 3 对照（同语料，仅切策略）
uv run python tools/run_corpus.py corpus_phase1.txt --clean --strategy persistence --log logs/phase3_persist.jsonl --data data/phase3_persist
uv run python tools/run_corpus.py corpus_phase1.txt --clean --strategy frequency   --log logs/phase3_freq.jsonl   --data data/phase3_freq

# 6. （可选，零 LLM 成本）阈值敏感性离线回放：在阈值网格上重算升层判定
uv run python tools/threshold_sweep.py
```
注：免费层 LLM 有速率限制，客户端已实现 429 指数退避，长语料可跑完。

## 证据清单（已入库，指向 tag v0.1）
| 文件 | 说明 |
|---|---|
| `corpus_phase1.txt` | 26 句英文语料（badminton×6 / Mochi×6+矛盾×2 / 噪声），Phase 1+3 共用 |
| `logs/real_events_p1b.jsonl` | Phase 1 全链路事件日志（含首例 working→consolidated 迁移） |
| `logs/trajectory_report.html` | Phase 1 轨迹报告（每条记忆状态轨迹 + 重组事件） |
| `logs/phase3_persist.jsonl` | Phase 3 persistence 策略事件日志 |
| `logs/phase3_freq.jsonl` | Phase 3 frequency 策略事件日志 |
| `logs/phase3_persist_report.html` / `phase3_freq_report.html` | 两份策略轨迹对比报告 |
| `logs/_phase3_compare.py` | 两策略升层记忆精确对比脚本（验证提取集 21=21、唯一变量=strategy） |
| `logs/threshold_sweep.json` | 阈值敏感性离线回放结果（persistence×frequency 阈值网格上的升层计数与发散区） |

## 核心结果（供叙事文档引用，数字不可变）
- **Phase 1**：badminton 记忆在真实 Gemini 下完成首例 `working→consolidated` 迁移（persistence 3.10）；噪声全停快层（0.00）。
- **Phase 3**：同语料、同 LLM、提取集完全一致（21=21），仅切策略 →
  persistence 升 1 条（badminton, EV=2）；frequency 升 4 条，其中 **3 条 EV=0**（纯自循环检索频率升层）。
  分歧精确落在"纯内部激活记忆是否该升层"。

> **诚实边界（GLM 证伪审查后降级）**：本结果验证的是"两种不等价的迁移规则在同一输入流上**产生可判别的结构差异，且分歧方向与理论对 Internal Selection 机制的描述相符**"（frequency 将零外部验证的记忆推上巩固层、persistence 不推），**并非**"分歧方向已被证明与理论一致"，更非"哪种结构更稳定"。协议 §5 真正的比较器（存活记忆 vs 演化中外部世界后期发展的一致性）与"稳定 vs 易被破坏"的标签**尚未测量**——本实验只测了"谁被升层"，从未做扰动/存活率检验。因此本发布称"Phase 3 先导实验（pilot）"，不称"Phase 3 证据"。阈值耦合（score 函数与阈值是两个独立自由度，结论对阈值敏感）在下方已知限制中声明，离线阈值回放见实验报告 §⑥。

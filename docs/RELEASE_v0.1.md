# Ananke — MVP v0.1 Release（冻结快照）

> **版本**：MVP v0.1（仪器发布版本）
> **基于协议**：`01_PROTOCOL_v3.md`（实验协议 v3，EV/IA 互斥 + 写入前去重 0.80）
> **冻结日期**：2026-07-14
> **git tag**：`v0.1`

## 这是什么
Ananke 是**约束场理论（Constraint Field Theory）的实验仪器**，不是"更好用的记忆系统"。
本发布冻结的是"仪器"——代码 + 协议 v3 + 真实 LLM 下产出的 Phase 1 / Phase 3 证据。
Evidence 的判定标准 = 系统是否产生理论预测的结构形状（分层 / 外部门控 / 单向阀），
不是记忆内容对不对。

## 冻结范围（IN / OUT）

### IN（本版本承诺）
- 三层记忆（Working / Consolidated / Core）+ 单向阀迁移
- 两种可切换迁移规则：`persistence`（External Selection，默认）/ `frequency`（Internal Selection，控制组）
- 真实 LLM 接入层（Gemini / DeepSeek / OpenAI 兼容）+ 真实嵌入（all-MiniLM-L6-v2）
- 观测工具：`analyze_trajectory.py`（Memory Trajectory 报告）、`run_corpus.py`、`dev_simulate.py`
- 真实 LLM 证据：Phase 1（快→中迁移、噪声抑制）+ Phase 3（persistence vs frequency 可判别差异）
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
uv run python tools/run_corpus.py corpus_phase1.txt --log logs/real_events_p1b.jsonl --data data/real_p1b
uv run python tools/analyze_trajectory.py --log logs/real_events_p1b.jsonl --data data/real_p1b

# 5. 跑 Phase 3 对照（同语料，仅切策略）
uv run python tools/run_corpus.py corpus_phase1.txt --strategy persistence --log logs/phase3_persist.jsonl --data data/phase3_persist
uv run python tools/run_corpus.py corpus_phase1.txt --strategy frequency   --log logs/phase3_freq.jsonl   --data data/phase3_freq
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

## 核心结果（供叙事文档引用，数字不可变）
- **Phase 1**：badminton 记忆在真实 Gemini 下完成首例 `working→consolidated` 迁移（persistence 3.10）；噪声全停快层（0.00）。
- **Phase 3**：同语料、同 LLM、提取集完全一致（21=21），仅切策略 →
  persistence 升 1 条（badminton, EV=2）；frequency 升 4 条，其中 **3 条 EV=0**（纯自循环检索频率升层）。
  分歧精确落在"纯内部激活记忆是否该升层"。

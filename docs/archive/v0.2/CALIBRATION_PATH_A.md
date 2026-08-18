# 路径 A：conv-26 付费校准运行手册

状态：**已准备到真实 API 调用前；下方 STOP 之后的命令尚未执行。**

关系分类的操作定义、开发案例与裁决状态统一维护在
[`docs/calibration/relation_labels/`](calibration/relation_labels/)；其中当前 50 对已改列为定义开发集，
不计作正式盲验集。

本手册只覆盖“跑对话”的驱动端 API，不运行 judge，不触碰其余 9 条验证候选。目标是用已暴露的
`conv-26` 前 100 轮测到真实 HTTP 请求、provider token usage、解析失败率和缓存复用，再估算完整
P/F 对照的驱动端成本。路径 A 不加入批量提取、本地 NLI、RPD 账本或真正检查点。

## 1. 已完成的离线准备

校准子集由原始 `conv-26` 按 session、轮次原顺序截取，不抽样、不重排：

```powershell
.\.venv\Scripts\python.exe tools\locomo_loader.py `
  --data data\locomo\locomo10.json `
  --sample-id conv-26 `
  --max-turns 100 `
  --out-corpus data\locomo\conv-26_calibration_100.jsonl `
  --out-probes data\locomo\conv-26_calibration_probes.jsonl
```

这些运行数据受 `.gitignore` 保护，不进入版本库。探针虽随适配器生成，但本轮不调用评测 API。
语料子集已逐行核对为完整 `conv-26` 的前 100 行，SHA256 为
`E3ACF574E06A375117A7C026792909EC1EC05FED0117F4330E7C7BC98A240A98`。

只读保护预检命令：

```powershell
.\.venv\Scripts\python.exe tools\run_corpus.py `
  data\locomo\conv-26_calibration_100.jsonl `
  --preflight --formal --strategy persistence
```

2026-08-10 在当前 Mistral 配置下重新执行的实际结果：

- 100 轮、6 sessions；
- 100 个唯一提取 key，现有 cache hit 为 0，即 100 个确定 cache miss、至少 100 次逻辑提取调用；
- 实际 HTTP 请求数仍为 `unknown`：提取解析重试和每次逻辑调用内部的 429 重试只能由校准计量；
- miss 提示共 110,695 字符；字符启发式约 27,674–36,899 input tokens；
- 分类调用为 `unknown`，因为它依赖真实提取结果和逐轮记忆状态；
- 当前配置满足真实模型、缓存开启、密钥存在、temperature=0；
- 本次预检读取到的 `model_tag` 为 `openai-compatible|mistral-small-2603`；它是下一条命令将使用的
  当前仪器，不等于已经完成冻结，若在调用前更换必须重新运行 preflight 并按新价格核算；
- `cache/` 当前存在但为空，Mistral extraction/pairs cache hit 均为 0；预检未写入缓存；
- 正式目标 data/event/usage 路径均不存在，且没有 `.formal-run.lock`，可开始首次校准运行。

完整 419 轮的同类预检为 419 个确定提取 miss（至少 419 次逻辑提取调用）、462,301 提示字符，粗略约
115,576–154,101 input tokens；这不是 provider 计费 token，也不包含状态依赖的分类量。

## 2. 真实调用前检查

执行者需确认：

- `.env` 中的 provider、base URL、model 和计费账户正是本轮拟冻结的驱动仪器；
- provider/model 一旦用于这次校准，正式运行中不临时换装；换模型会因 cache key 中的 model tag
  自动失效，并构成重新校准；
- `LLM_TEMPERATURE=0.0`、`CACHE_ENABLED=true`；
- 下面的 data/event/usage 三个 tag 一致且对应新运行；
- 没有另一个 P/F runner 正在使用共享 `cache/`；
- 价格换算使用调用当日、该账户/网关的实际输入、缓存输入和输出单价，不在代码里硬编码旧价格。

`--formal` 会在真正构造客户端之前拒绝 mock、缺密钥、非零温度、缓存关闭、缺少显式策略、
`--no-cache` 或 `--refresh-cache`。运行时 `.formal-run.lock` 强制单写者。若进程被硬杀并遗留锁，
必须先确认原进程已经终止并检查锁中的 PID，不能自动删锁后并行重跑。

## 3. STOP — 本轮在这里停止

以下命令会产生真实付费 API 请求。**本次实现与验证没有执行它。**

```powershell
.\.venv\Scripts\python.exe tools\run_corpus.py `
  data\locomo\conv-26_calibration_100.jsonl `
  --formal `
  --strategy persistence `
  --data data\calibration\conv-26-p100-persistence `
  --log logs\conv-26-p100-persistence_events.jsonl `
  --usage-log logs\conv-26-p100-persistence_llm_usage.jsonl `
  --clean
```

预期产物：

- `logs/conv-26-p100-persistence_events.jsonl`：动力学事件；成功结束时的 `run_metrics` 同时持久化
  cache hit/miss 与 API 汇总；
- `logs/conv-26-p100-persistence_llm_usage.jsonl`：每次真实 HTTP 尝试，包括 429/错误与 provider
  usage；SDK 隐式重试已关闭，同一逻辑调用的显式 429 重试共享 `call_id`；
- `data/calibration/conv-26-p100-persistence/`：校准状态；
- `cache/{extraction,pairs}.jsonl`：可供后续 F 重放复用的只增缓存。

## 4. 校准后才执行的核算

先检查 stdout 与 usage JSONL 中的四项：

1. `logical_calls` 与 `http_requests`；两者之差主要来自 429 的 HTTP 层重试；
2. `logical_calls_by_operation` 与 `http_requests_by_operation`：同一 operation 下两者之差是
   HTTP 层重试；B7/提取解析重试会增加新的 logical call，cache hit 则两者都不增加；
3. `prompt_tokens`、`completion_tokens`、`cached_prompt_tokens` 与
   `successful_requests_without_usage`；usage 缺失时不能把字符启发式冒充账单 token；
4. 提取/分类 cache hit/miss、`classification_unparsed` 数与 100 轮是否完整结束。

校准成本按该 provider 当日账单规则计算。完整 P 运行的外推应分别处理提取与分类，不能只拿“每轮
平均 token”盲乘；419 轮 preflight 提供精确的提取 miss/字符基数，分类部分用校准实测的
“每条提取记忆触发的 relation 请求率、解析重试率和输出 token”估算并标明不确定性。

若需要实测 P→F 的跨策略复用，再以相同 100 轮、不同 data/log tag 串行运行 frequency；不得与 P
并行。F 会共享 P 已写入的内容寻址缓存，因此它的真实增量请求才是双策略总成本的有效校准。

只有在校准完整、provider usage 可用、解析失败率可接受后，才更新预算并决定完整 `conv-26` 或
正式保留集运行。任何正式验证仍需先完成 50 对分类器人工验收、验证 ID 锁定和一次性预登记。

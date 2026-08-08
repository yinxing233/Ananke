import math
import os

from dotenv import load_dotenv

# 从 .env（或真实环境变量）读取配置。.env 已被 .gitignore 忽略，密钥不会进入 git。
# 任何敏感项缺失都不会报错，仅在真正调用真实 LLM 时才校验。
load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on", "y")


class Config:
    # 层级容量
    WORKING_CAPACITY = 50
    CONSOLIDATED_CAPACITY = 200

    # 存续检验超参数
    EXTERNAL_VALIDATION_WEIGHT = 1.0
    INTERNAL_ACTIVATION_WEIGHT = 1 / math.e  # ≈ 0.368
    MIGRATION_THRESHOLD = 3.0
    FREQUENCY_MIGRATION_THRESHOLD = 3
    # 注：LOCAL_REORG_THRESHOLD 属中→慢闸(v4 §2.5)，定义移至下方 v4 段，此处不再重复。

    # 实验组/对照组开关：persistence（默认，External Selection）或 frequency（Internal Selection 对照组）。
    # frequency 使用 total_activation：每次合格 duplicate/related/reorganization 信号均 +1；
    # duplicate 的 EV 按 distinct session 去重，但非 guided 的后续跨 session 重复仍逐次累加
    # total_activation。Frequency 不复用 internal_activation。
    WORKING_PROMOTION_STRATEGY = os.getenv("WORKING_PROMOTION_STRATEGY", "persistence")

    # ---- v3 遗留阈值（协议 v4 已弃用余弦判定，仅保留供审计/向后兼容）----
    # v4 用「余弦召回(cos≥R_RECALL) + 关系分类器」取代下述余弦阈值判定。
    # 下述常量不再驱动任何信号；仅 analyze_trajectory / 旧日志读取可能引用。
    INTERNAL_ACTIVATION_THRESHOLD = 0.6   # 遗留：v3 内部激活余弦门
    EXTERNAL_VALIDATION_THRESHOLD = 0.80  # 遗留：v3 外部验证余弦门（=v3 记忆同一性阈值）
    DEDUP_SIMILARITY_THRESHOLD = 0.80      # 遗留：v3 写入前去重余弦门
    REORG_SIMILARITY_THRESHOLD = 0.9       # 遗留：v3 重组余弦门

    # ---- v4 召回-分类两段式（协议 v4 §2）----
    # 余弦召回阈值：新记忆 m 与既有记忆 e 的余弦 ≥ R_RECALL 才进入关系分类。
    # 初值 0.65，待冒烟校准（v4 §8 冻结条件之一）。
    R_RECALL = float(os.getenv("R_RECALL", "0.65"))
    # 2026-08-08 路径 A：关系分类器固定为 LLM 五选一。
    # 不保留一个实际上未接线的 NLI 开关，避免配置看似切换、运行却仍调用 LLM。

    # 中→慢闸（consolidated→core）晋升规则（v4 §2.3/§4，Fable5 漂移1 修正后）：
    # 晋升唯一信号 = mergeable 累积 local_reorganization_trigger ≥ LOCAL_REORG_THRESHOLD
    #   （代表被反复确认/合并的稳定结构，符合原则B：CORE 只装"经受住检验"者）。
    # 晋升阻断器 = conflict_trigger > 0：被矛盾触发的记忆冻结在中层，直到矛盾被裁决
    #   （v3「被接触=被确认」的 EV 污染禁止在第二道闸复活；原 conflict_threshold≥2 晋升逻辑已删除）。
    LOCAL_REORG_THRESHOLD = 2

    # 模型
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # ---- LLM provider 配置（从 .env 读取，绝不在代码中硬编码密钥）----
    # 可选 provider：openai / deepseek / openrouter / groq / ollama / openai-compatible
    # 它们都走 OpenAI 兼容接口，仅靠 base_url + api_key + model 切换，无需改代码。
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai-compatible").lower()
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")  # 留空则使用 provider SDK 默认值
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
    # 模型家族通常可由 provider/model 推断；代理网关或私有模型名无法推断时须显式填写。
    LLM_FAMILY = os.getenv("LLM_FAMILY", "")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    # RPM 节流（I/O 韧性，不影响理论行为）：控制驱动端每分钟请求数，防撞 gemini 限流。
    # 默认 30（用户确认其 key = 30 rpm 免费层上限）；如限额更高可调 LLM_RPM 上调。
    # 纯预防性节流，与 call_llm 内 429 指数退避互补（退避=撞墙后恢复，节流=不撞墙）。
    LLM_RPM = int(os.getenv("LLM_RPM", "30"))

    # 开发开关：True 时使用 Mock LLM（不联网、不需要密钥，秒级跑通迁移/激活逻辑）
    USE_MOCK_LLM = _as_bool(os.getenv("USE_MOCK_LLM"), default=True)

    # ---- v4 §5 评估独立性：评判端主裁判（不同家族 LLM）----
    # 驱动端 = embedding + Gemini 提取；评判端 = DeepSeek/GLM 等**不同家族** LLM，
    # 结构化判定「记忆 X 是否包含回答问题 Q 所需事实：包含/部分/不包含」。
    # 默认与驱动端不同家族；嵌入模型在评估端禁止出现（防驱动-评判度量循环）。
    EVAL_LLM_PROVIDER = os.getenv("EVAL_LLM_PROVIDER", "deepseek").lower()
    EVAL_LLM_API_KEY = os.getenv("EVAL_LLM_API_KEY", "")
    EVAL_LLM_BASE_URL = os.getenv("EVAL_LLM_BASE_URL", "")
    EVAL_LLM_MODEL = os.getenv("EVAL_LLM_MODEL", "deepseek-chat")
    EVAL_LLM_FAMILY = os.getenv("EVAL_LLM_FAMILY", "")
    EVAL_LLM_RPM = int(os.getenv("EVAL_LLM_RPM", "0"))
    # B6 的部分分固定为 0.5，已不是配置项；唯一实现位于 tools/evaluate.py。

    # ---- 两级缓存（协议 v4 §8，续跑即重跑）----
    # 提取结果 + 分类对结果落盘，让换模型/换策略的重跑近乎零 API 成本，并给主测量量 D 去噪
    # （提取对所有运行一致、重叠句对分类一致 → D 退化为纯策略差测度）。
    # key = (model_tag, prompt_hash, category, normalized_input)：
    #   - model_tag / prompt_hash 任一变化自动失效；prompt_hash 由实际 prompt 模板 SHA1 算出
    #     （B3：改 prompt 模板即全量失效，不依赖手动 bump）。
    # 红线：缓存目录与 data/ 平级（cache/），任何数据清理（--clean / rm -rf data）都不得触碰。
    CACHE_ENABLED = _as_bool(os.getenv("CACHE_ENABLED"), default=True)
    CACHE_DIR = os.getenv("CACHE_DIR", "cache")
    # 以下的版本号已**不参与失效**（失效由 prompt 模板哈希自动完成，B3）。保留仅作语义标注，
    # 方便人读"这批缓存对应哪版指令"；改了 prompt 模板无需记得 bump 它们。
    CACHE_PROMPT_VERSION_EXTRACTION = os.getenv("CACHE_PROMPT_VERSION_EXTRACTION", "v1")
    CACHE_PROMPT_VERSION_PAIRS = os.getenv("CACHE_PROMPT_VERSION_PAIRS", "v1")

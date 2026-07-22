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
    # frequency 使用 total_activation（每次语义命中 cosine ≥ 0.60 即 +1，不区分来源），不复用 internal_activation。
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
    # 关系分类器方案：llm（方案乙，默认）| nli（方案甲，待接入）。
    RELATION_CLASSIFIER_SCHEME = os.getenv("RELATION_CLASSIFIER_SCHEME", "llm").lower()

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
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

    # 开发开关：True 时使用 Mock LLM（不联网、不需要密钥，秒级跑通迁移/激活逻辑）
    USE_MOCK_LLM = _as_bool(os.getenv("USE_MOCK_LLM"), default=True)

    # ---- v4 §5 评估独立性：评判端主裁判（不同家族 LLM）----
    # 驱动端 = embedding + Gemini 提取；评判端 = DeepSeek/GLM 等**不同家族** LLM，
    # 结构化判定「记忆 X 是否包含回答问题 Q 所需事实：包含/部分/不包含」。
    # 默认与驱动端不同家族；嵌入模型在评估端禁止出现（防驱动-评判度量循环）。
    EVAL_LLM_PROVIDER = os.getenv("EVAL_LLM_PROVIDER", "deepseek")
    EVAL_LLM_API_KEY = os.getenv("EVAL_LLM_API_KEY", "")
    EVAL_LLM_BASE_URL = os.getenv("EVAL_LLM_BASE_URL", "")
    EVAL_LLM_MODEL = os.getenv("EVAL_LLM_MODEL", "deepseek-chat")
    # "部分包含"计分：命中=1.0（包含），partial=该系数（待冒烟校准），不含=0.0
    EVAL_PARTIAL_CREDIT = float(os.getenv("EVAL_PARTIAL_CREDIT", "0.5"))

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
    LOCAL_REORG_THRESHOLD = 2

    # 实验组/对照组开关：persistence（默认，External Selection）或 frequency（Internal Selection 对照组）。
    # frequency 使用 total_activation（每次语义命中 cosine ≥ 0.60 即 +1，不区分来源），不复用 internal_activation。
    WORKING_PROMOTION_STRATEGY = os.getenv("WORKING_PROMOTION_STRATEGY", "persistence")

    # 语义相似度阈值
    INTERNAL_ACTIVATION_THRESHOLD = 0.6
    EXTERNAL_VALIDATION_THRESHOLD = 0.80
    DEDUP_SIMILARITY_THRESHOLD = 0.80
    REORG_SIMILARITY_THRESHOLD = 0.9

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

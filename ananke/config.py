import math


class Config:
    # 层级容量
    WORKING_CAPACITY = 50
    CONSOLIDATED_CAPACITY = 200

    # 存续检验超参数
    EXTERNAL_VALIDATION_WEIGHT = 1.0
    INTERNAL_ACTIVATION_WEIGHT = 1 / math.e  # ≈ 0.368
    MIGRATION_THRESHOLD = 3.0
    LOCAL_REORG_THRESHOLD = 2

    # 语义相似度阈值
    INTERNAL_ACTIVATION_THRESHOLD = 0.6
    EXTERNAL_VALIDATION_THRESHOLD = 0.85
    REORG_SIMILARITY_THRESHOLD = 0.9

    # 模型
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    LLM_MODEL = "deepseek-chat"  # 根据你实际用的模型修改

    # 开发开关
    USE_MOCK_LLM = True  # 调试迁移/激活逻辑时设为 True，秒级跑通

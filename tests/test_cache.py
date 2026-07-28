"""两级缓存 + 确定性 tie-break 单测（协议 v4 §8）。

零 API、零模型下载：用 CountingLLM 验证缓存命中时不调用 LLM；用平票构造验证
召回/淘汰的确定性打破规则。这些是「重放等价性」成立的代码层前提。
"""

import json

import numpy as np

from ananke.cache import LLMCache, normalize
from ananke.config import Config
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.models import LayerEnum, MemoryEntry


class CountingLLM:
    """记录调用次数的假 LLM，用于验证缓存命中时不调用。"""

    def __init__(self, response='["User likes cats"]'):
        self.response = response
        self.calls = 0
        self.cache = None  # 模拟 llm_client.cache 属性

    def call_llm(self, prompt, system_prompt=None, temperature=None):
        self.calls += 1
        return self.response


# ---- 缓存命中 / 未命中 ----


def test_extraction_cache_hit_skips_llm(tmp_path):
    """同输入第二次提取应命中缓存，不调 LLM。"""
    from ananke.extraction import extract_memories

    llm = CountingLLM('["User likes cats"]')
    llm.cache = LLMCache(tmp_path / "cache", model_tag="test|m", enabled=True)
    r1 = extract_memories("I have a cat", llm)
    assert llm.calls == 1
    r2 = extract_memories("I have a cat", llm)
    assert llm.calls == 1  # 命中，仍 1 次
    assert r1 == r2


def test_extraction_cache_different_input_misses(tmp_path):
    """不同输入应 miss，调 LLM。"""
    from ananke.extraction import extract_memories

    llm = CountingLLM('["User likes cats"]')
    llm.cache = LLMCache(tmp_path / "cache", model_tag="test|m", enabled=True)
    extract_memories("I have a cat", llm)
    extract_memories("I have a dog", llm)
    assert llm.calls == 2


def test_pairs_cache_hit_skips_llm(tmp_path):
    """分类对缓存：同 (new, existing) 句对第二次命中，不调 LLM。"""
    from ananke.relation import LLMRelationClassifier

    llm = CountingLLM("duplicate")
    llm.cache = LLMCache(tmp_path / "cache", model_tag="test|m", enabled=True)
    clf = LLMRelationClassifier(llm)
    r1 = clf.classify("I like cats", "User likes cats")
    assert llm.calls == 1
    r2 = clf.classify("I like cats", "User likes cats")
    assert llm.calls == 1  # 命中
    assert r1 == r2


# ---- 隔离性：模型 / prompt 版本 ----


def test_cache_model_tag_isolation(tmp_path):
    """不同 model_tag 的缓存不混（换模型自动失效）。"""
    c1 = LLMCache(tmp_path / "c", model_tag="gemini|flash")
    c2 = LLMCache(tmp_path / "c", model_tag="qwen|plus")
    c1.put("extraction", "key1", "v1")
    assert c2.get("extraction", "key1") is None  # 不同模型 → miss
    assert c1.get("extraction", "key1") == "v1"


def test_cache_prompt_template_isolation(tmp_path):
    """不同 prompt 模板（SHA1）的缓存不混（B3：改 prompt 即全量失效，不依赖手动 bump）。"""
    c1 = LLMCache(tmp_path / "c", model_tag="m", prompt_templates={"extraction": "template A"})
    c2 = LLMCache(tmp_path / "c", model_tag="m", prompt_templates={"extraction": "template B"})
    c1.put("extraction", "key1", "v1")
    assert c2.get("extraction", "key1") is None  # 不同 prompt 模板 → hash 不同 → miss


def test_cache_prompt_version_ignored_for_invalidation(tmp_path):
    """手动 CACHE_PROMPT_VERSION 不再参与失效（B3：失效由模板哈希自动完成）。

    LLMCache 已不接受 prompt_versions 参数——版本号只是语义标注，完全不参与 key。
    这里用「同目录、同模板、两次构造（模拟版本号变化）」验证版本无关性：
    第二次构造加载同一落盘文件，应 hit 首次写入的值。
    """
    cache_dir = tmp_path / "ver"
    c1 = LLMCache(cache_dir, model_tag="m", prompt_templates={"extraction": "T"})
    c1.put("extraction", "key1", "v1")
    # 同目录重新构造（模拟改了 prompt_versions 但仍同模板）：应加载并 hit
    c2 = LLMCache(cache_dir, model_tag="m", prompt_templates={"extraction": "T"})
    assert c2.get("extraction", "key1") == "v1"  # 版本号不参与失效 → 仍 hit


# ---- 幂等 / 禁用 ----


def test_cache_idempotent_put(tmp_path):
    """同 key 重复 put 不覆盖首次值（同输入永远返回首次结果）。"""
    c = LLMCache(tmp_path / "c", model_tag="m")
    c.put("extraction", "k", "first")
    c.put("extraction", "k", "second")  # 应忽略
    assert c.get("extraction", "k") == "first"


def test_cache_disabled_no_hit(tmp_path):
    """disabled 时 get 恒返回 None、put 不落盘。"""
    c = LLMCache(tmp_path / "c", model_tag="m", enabled=False)
    c.put("extraction", "k", "v")
    assert c.get("extraction", "k") is None


def test_cache_persists_across_instances(tmp_path):
    """缓存落盘后，新实例加载能命中（续跑即重跑的基础）。"""
    c1 = LLMCache(tmp_path / "c", model_tag="m")
    c1.put("extraction", "k", "v")
    c2 = LLMCache(tmp_path / "c", model_tag="m")  # 重新加载
    assert c2.get("extraction", "k") == "v"


# ---- §6 归一化（协议守护：单一实现来源）----


def test_normalize_section6():
    """§6 归一化：小写 + 去标点 + 折叠空白。"""
    assert normalize("User likes cats!") == "user likes cats"
    assert normalize("  User   likes  cats  ") == "user likes cats"
    assert normalize("Cats, dogs.") == "cats dogs"
    assert normalize("用户喜欢羽毛球。") == "用户喜欢羽毛球"


def test_protocol_2_6_single_norm_source():
    """协议守护（B1）：§6 记忆同一性判据必须是单一实现。

    cache.py 与 divergence_analysis.py 引用的是**同一函数对象**（ananke.text_norm.normalize），
    不得各持一份可独立漂移的拷贝——那等于协议条款出现两个实现，同 P0-A 三方矛盾病灶。
    """
    import sys
    from pathlib import Path

    from ananke.cache import normalize as cache_normalize

    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT / "tools") not in sys.path:
        sys.path.insert(0, str(ROOT / "tools"))
    import divergence_analysis as da_mod  # noqa: E402

    assert cache_normalize is da_mod._norm, (
        "cache.normalize 与 divergence_analysis._norm 不是同一函数对象；"
        "§6 归一化出现了第二份拷贝，协议判据可独立漂移。"
    )


# ---- 确定性 tie-break ----


class _FlatEmbedding:
    """所有内容映射到同一向量 → 余弦全平票，逼迫 tie-break 生效。"""

    def encode(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return np.array([[1.0, 0.0, 0.0]] * len(texts))

    def cosine_similarity(self, a, b):
        return 1.0


def test_recall_deterministic_tiebreak_by_content(tmp_path):
    """召回余弦平票时按 content 字典序取较小者（跨运行一致，非 uuid）。"""
    from ananke.pipeline import MemoryPipeline
    from ananke.relation import MockRelationClassifier, REL_DUPLICATE

    store = MemoryStore(tmp_path / "d")
    m_aaa = MemoryEntry(id="x9", content="aaa fact", session_id="s1", layer=LayerEnum.WORKING)
    m_zzz = MemoryEntry(id="x1", content="zzz fact", session_id="s1", layer=LayerEnum.WORKING)
    store.add(m_aaa)
    store.add(m_zzz)  # id 更小但 content 更大

    class FakeLLM:
        cache = None

        def call_llm(self, p, system_prompt=None, temperature=None):
            return "[]"

    emb = _FlatEmbedding()
    pipe = MemoryPipeline(
        store, emb, FakeLLM(), EventLogger(tmp_path / "l.jsonl"),
        relation_classifier=MockRelationClassifier(REL_DUPLICATE),
    )
    vecs = [emb.encode(m.content)[0] for m in store.get_working_memories()]
    cand, sim = pipe._recall("new", store.get_working_memories(), vecs)
    # 平票 → content 字典序：aaa < zzz → 选 "aaa fact"（尽管其 id 更大）
    assert cand.content == "aaa fact"


def test_eviction_deterministic_tiebreak_by_content(tmp_path):
    """淘汰分数平票时按 content 字典序淘汰较小者（跨运行一致）。"""
    from ananke.migration import enforce_working_capacity

    store = MemoryStore(tmp_path / "d")
    m_aaa = MemoryEntry(id="x9", content="aaa", session_id="s1", layer=LayerEnum.WORKING)
    m_zzz = MemoryEntry(id="x1", content="zzz", session_id="s1", layer=LayerEnum.WORKING)
    store.add(m_aaa)
    store.add(m_zzz)  # 两条 persistence_score 都 = 0 → 平票

    orig = Config.WORKING_CAPACITY
    Config.WORKING_CAPACITY = 1  # 触发淘汰 1 条
    try:
        enforce_working_capacity(store, EventLogger(tmp_path / "l.jsonl"))
        remaining = [m.content for m in store.get_working_memories()]
        # 平票 → 淘汰 content 较小者 "aaa"（尽管其 id 更大），剩 "zzz"
        assert remaining == ["zzz"]
    finally:
        Config.WORKING_CAPACITY = orig

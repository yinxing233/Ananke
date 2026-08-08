r"""两级缓存：提取结果 + 分类对结果，落盘 JSONL（协议 v4 §8，续跑即重跑）。

为什么缓存是测量前提而非省钱优化
================================
主测量量 D = (P\F) ∪ (F\P) 测「换策略后哪些记忆进巩固层」。若提取/分类非确定，
噪声渗入 D，分不清「策略差」还是「LLM 抽风」。缓存让提取对所有运行一致、重叠句对
分类一致 → D 退化为纯策略差测度。

续跑 = 重跑：从第 1 轮重放，前 N 轮全部缓存命中，第 N+1 轮起才产生新调用。这比
「状态快照 + 断点续传」更强——它附赠重放等价性测试：缓存重放的前 N 轮结果必须与
原始运行逐事件一致，不一致即暴露管线中的非确定性。

key 结构 = (model_tag, prompt_hash, category, normalized_input)
  - model_tag 含 provider+model：换模型自动失效（驱动端已 Gemini→Qwen 漂移过一次，
    若 key 不含模型标识，两个模型的提取/分类会无声混进同一运行）。
  - prompt_hash = 实际发给 LLM 的 prompt 模板 SHA1 前 8 位：改 prompt 模板即全量失效，
    **不依赖任何人手动 bump 版本号**（B3：手动版本号会忘，哈希不会）。
  - category ∈ {extraction, pairs}。
  - normalized_input：提取用 §6 归一化(输入文本)；分类用 归一化(new)||归一化(existing)。

归一化函数（§6 记忆同一性判据）的唯一来源见 ananke/text_norm.py，本模块只 import，
不得复制第二份（同 P0-A 三方矛盾病灶）。

存储值原则（C1+C2）：只缓存**合法解析出的归一化结果**
  - extraction 存规范 JSON 列表字符串；relation 存归一化标签字符串。
  - 解析失败 / 空响应 = 基础设施故障（超时 / 429 / 连接断），**不落盘、触发重试、
    最终 raise**——绝不与 "unrelated" 这个语义标签折叠（unrelated 是唯一不发光信号的
    类，每一次故障折叠都无声吞掉一个潜在 EV 或 contradict）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ananke.text_norm import normalize


# 旧缓存位置（v0.2 早期默认 data/cache）。红线：缓存是项目最贵的持久资产，
# 迁移到与 data/ 平级的 cache/ 后，任何 `rm -rf data` 都不该烧掉已付费的 LLM 调用。
LEGACY_CACHE_DIR = "data/cache"


class LLMCache:
    """两级缓存：提取(extraction) + 分类对(pairs)，落盘 JSONL，内存索引。

    幂等重放：同一 (model, prompt, input) 永远返回首次结果。
    命中/未命中计数供 run_corpus 末尾报告，并供重放等价性审计。
    """

    CATEGORIES = ("extraction", "pairs")

    def __init__(
        self,
        cache_dir: str | Path = "cache",
        model_tag: str = "",
        prompt_templates: Optional[dict] = None,
        enabled: bool = True,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.model_tag = model_tag or "unknown"
        self.enabled = enabled
        # prompt 模板 SHA1 前 8 位：改模板即全量失效（B3 自动哈希，不依赖手动 bump）。
        self.prompt_hashes = {
            c: hashlib.sha1(t.encode("utf-8")).hexdigest()[:8]
            for c, t in (prompt_templates or {}).items()
        }
        # category -> {composite_key: value}
        self._index: dict[str, dict[str, str]] = {c: {} for c in self.CATEGORIES}
        self._hits: dict[str, int] = {c: 0 for c in self.CATEGORIES}
        self._misses: dict[str, int] = {c: 0 for c in self.CATEGORIES}
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            for c in self.CATEGORIES:
                self._load(c)

    def _path(self, category: str) -> Path:
        return self.cache_dir / f"{category}.jsonl"

    def _load(self, category: str) -> None:
        path = self._path(category)
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = rec.get("key")
            val = rec.get("value")
            if key is not None and val is not None:
                self._index[category][key] = val

    def _composite_key(self, category: str, normalized_input: str) -> str:
        ph = self.prompt_hashes.get(category, "")
        return self.compose_key(self.model_tag, ph, category, normalized_input)

    @staticmethod
    def compose_key(
        model_tag: str,
        prompt_hash: str,
        category: str,
        normalized_input: str,
    ) -> str:
        """Single source for cache-key construction, including read-only preflight."""
        return f"{model_tag}|{prompt_hash}|{category}|{normalized_input}"

    @staticmethod
    def read_keys(cache_dir: str | Path, category: str) -> set[str]:
        """Read valid keys without creating or mutating the cache directory."""
        path = Path(cache_dir) / f"{category}.jsonl"
        if not path.exists():
            return set()
        keys: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = record.get("key")
            value = record.get("value")
            if isinstance(key, str) and value is not None:
                keys.add(key)
        return keys

    def get(self, category: str, normalized_input: str) -> Optional[str]:
        """查缓存。命中返回值并计 hit；未命中返回 None 并计 miss。disabled 时恒返回 None（不计 hit/miss）。"""
        if not self.enabled:
            return None
        key = self._composite_key(category, normalized_input)
        val = self._index[category].get(key)
        if val is not None:
            self._hits[category] += 1
        else:
            self._misses[category] += 1
        return val

    def put(self, category: str, normalized_input: str, value: str) -> None:
        """存缓存。幂等：key 已存在则保持首次值不覆盖（同 input 永远返回首次结果）。

        调用方职责（C1+C2）：value 必须是**合法解析出的归一化结果**（extraction=规范
        JSON 列表字符串；pairs=归一化标签）。解析失败/空响应不得调用本方法。
        """
        if not self.enabled:
            return
        key = self._composite_key(category, normalized_input)
        if key in self._index[category]:
            return
        self._index[category][key] = value
        with self._path(category).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")

    def stats(self) -> dict:
        return {
            c: {
                "hits": self._hits[c],
                "misses": self._misses[c],
                "size": len(self._index[c]),
            }
            for c in self.CATEGORIES
        }

    @classmethod
    def refresh(cls, cache_dir: str | Path = "cache") -> int:
        """清空缓存目录下所有 .jsonl（--refresh-cache 用，唯一 sanctioned 的显式删除）。

        注意：这是有意为之的「重置」动作，永远由用户显式 --refresh-cache 触发，
        不是自动行为。常规运行下缓存目录只增不删（红线）。
        """
        cache_dir = Path(cache_dir)
        n = 0
        for c in cls.CATEGORIES:
            p = cache_dir / f"{c}.jsonl"
            if p.exists():
                n += sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
                p.unlink()
        return n


class FormalRunLock:
    """Exclusive writer lock for formal P/F runs sharing one cache.

    The lock is intentionally simple and fail-closed.  The runner releases it on
    normal completion and also registers an interpreter-exit safeguard for an
    exception or Ctrl-C.  After a hard process kill, the operator must inspect
    and remove the small lock file explicitly; automatic stale-lock deletion
    would risk two formal writers.
    """

    FILENAME = ".formal-run.lock"

    def __init__(self, cache_dir: str | Path) -> None:
        self.cache_dir = Path(cache_dir)
        self.path = self.cache_dir / self.FILENAME
        self._fd: int | None = None
        self._token = str(uuid4())

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.path, flags)
        except FileExistsError as error:
            raise RuntimeError(
                f"formal cache lock already exists: {self.path}; "
                "P/F runs must be strictly serial"
            ) from error
        try:
            payload = json.dumps(
                {"pid": os.getpid(), "token": self._token},
                ensure_ascii=False,
            ).encode("utf-8")
            os.write(fd, payload)
        except Exception:
            os.close(fd)
            self.path.unlink(missing_ok=True)
            raise
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        os.close(self._fd)
        self._fd = None
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if record.get("token") == self._token:
            self.path.unlink(missing_ok=True)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def _is_hex8(s: str) -> bool:
    """判断是否为 8 位十六进制（当前 prompt 哈希段的特征）。"""
    return len(s) == 8 and all(c in "0123456789abcdef" for c in s)


def _rewrite_legacy_key(key: str, prompt_hashes: dict) -> str:
    """把旧版 key 的 version 段重写为当前 prompt 哈希段。

    旧格式：<model_tag>|<version,如 v1>|<category>|<normalized_input>
    新格式：<model_tag>|<sha1[:8]>|<category>|<normalized_input>
    version 段永远在倒数第 3 位（category 倒数第 2，input 末位；model_tag 可能含 '|'，
    故不能按固定位置取，必须倒数定位）。

    为什么要重写：v0.2-draft 生成的缓存 key 用的是 prompt 版本号（"v1"），而 B3 改为
    用模板 SHA1 哈希。若只搬文件不改 key，重放 1-253 轮时新代码算出的 key 是
    `model_tag|<hash>|...`，缓存里却是 `model_tag|v1|...` → 全部 miss → 重烧 253 轮
    额度，红线"保住已付费成果"被架空。prompt 模板内容本轮未变（只改了编码方式），
    故重写为当前哈希是正确且安全的。

    安全约束（不破坏）：
      · 若 version 段已为 8 位 hex（新格式）→ 原样返回。
      · 结构不合法（<4 段）→ 原样返回。
      · category 不在 prompt_hashes（未知类）→ 原样返回（保留物理存在，仅可能 miss）。
    """
    parts = key.split("|")
    if len(parts) < 4:
        return key
    version_seg = parts[-3]
    if _is_hex8(version_seg):
        return key  # 已是新格式，无需重写
    category = parts[-2]
    h = prompt_hashes.get(category)
    if not h:
        return key  # 未知 category，无法安全重写
    parts[-3] = h
    return "|".join(parts)


def migrate_legacy_cache(target: str | Path = "cache", prompt_templates: Optional[dict] = None) -> int:
    """把旧位置 data/cache 迁移到新平级位置（默认 cache/），保住已付费的 LLM 调用成果。

    红线：缓存目录是项目最贵的持久资产（253 轮 Qwen 调用全在里面）。早期默认
    data/cache 与数据目录同树，一次手滑 `rm -rf data` 会连缓存一起烧掉。迁移到
    与 data/ 平级后，清理数据目录不再威胁缓存。

    迁移同时把旧 key 的 version 段重写为当前 prompt 哈希段（见 _rewrite_legacy_key），
    否则旧缓存无法在新哈希 key 下命中，等于白迁移。

    幂等：目标已有 .jsonl（或已迁移过）则跳过，不覆盖、不重烧。返回迁移文件数。
    """
    src = Path(LEGACY_CACHE_DIR)
    dst = Path(target)
    if not src.exists():
        return 0
    if dst.exists() and any(dst.glob("*.jsonl")):
        return 0  # 目标已有缓存，不覆盖（防丢失 / 防重复迁移）
    prompt_hashes = {
        c: hashlib.sha1(t.encode("utf-8")).hexdigest()[:8]
        for c, t in (prompt_templates or {}).items()
    }
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in src.glob("*.jsonl"):
        lines = []
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                lines.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                lines.append(line)  # 损坏行原样保留，不静默丢弃
                continue
            key = rec.get("key")
            if isinstance(key, str):
                new_key = _rewrite_legacy_key(key, prompt_hashes)
                if new_key != key:
                    rec["key"] = new_key
            lines.append(json.dumps(rec, ensure_ascii=False))
        (dst / f.name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        f.unlink()  # 搬移语义：源已写入新位置，删除旧副本（非清理，是一次性迁移）
        n += 1
    return n

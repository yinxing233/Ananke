#!/usr/bin/env python3
"""真实语料喂入驱动：用真实 LLM + 真实嵌入模型跑一段语料，产出事件日志。

与 tools/dev_simulate.py 的区别：
- dev_simulate 用 FakeEmbedding + ScriptedLLM（合成数据，仅验证管道）；
- 本脚本用**真实 EmbeddingEngine + create_llm_client()（读 .env 的 Gemini/DeepSeek 等）**，
  产生的是真实语义下的动力学日志，可直接喂给 tools/analyze_trajectory.py 分析。

原则 B 边界：本脚本**只喂入你提供的语料**（实验者控制的外部输入），绝不自行生成
输入来"检验自己"——系统生成内容永远不计入 external_validation（由 pipeline 内部
system_guided=False 保证）。

用法：
    # 先把 Gemini key 写进 .env，设 USE_MOCK_LLM=false
    uv run python tools/run_corpus.py corpus.txt
    uv run python tools/run_corpus.py corpus_phase2.jsonl --log logs/real_events.jsonl
    # 会话感知语料：.jsonl 含 {session_id, input}；.txt 用 `# session: N` 标记
    # v0.2 分歧集对照：同语料跑两遍，仅切迁移策略（结果供 tools/divergence_analysis.py）
    uv run python tools/run_corpus.py corpus_phase2.jsonl --strategy persistence --data data/p --clean
    uv run python tools/run_corpus.py corpus_phase2.jsonl --strategy frequency --data data/f --clean
    uv run python tools/evaluate.py --data data/p --probes corpus_phase2_probes.jsonl --strategy persistence --tag p
    uv run python tools/evaluate.py --data data/f --probes corpus_phase2_probes.jsonl --strategy frequency   --tag f
    uv run python tools/divergence_analysis.py --eval-p logs/eval_p.json --eval-f logs/eval_f.json
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ananke.cache import FormalRunLock, LLMCache
from ananke.config import Config
from ananke.embedding import EmbeddingEngine
from ananke.extraction import (
    EXTRACTION_PROMPT_TEMPLATE,
    EXTRACTION_USER_PREFIX,
    _SYSTEM_PROMPT as EXTRACTION_SYSTEM_PROMPT,
    _source_context_key,
    _source_context_prompt,
)
from ananke.llm_client import create_llm_client
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline
from ananke.relation import RELATION_PROMPT_TEMPLATE


@dataclass(frozen=True)
class CorpusTurn:
    text: str
    session_id: str | None
    dia_id: str | None = None
    speaker: str | None = None
    session_datetime: str | None = None


def load_corpus(path: Path) -> list[CorpusTurn]:
    """加载语料，保留每轮 input/session/dia/speaker/date 来源。

    支持三种格式：
    - .jsonl 每行含 {session_id, input}（或 {session/text/user/content}）。
    - .txt 含 `# session: N` 标记行，标记后直至下一个标记的归该 session。
    - 纯 .txt 无标记 → 全部归默认 session "s1"（无跨 session，EV 不会触发，
      仅用于 IA/dedup 演示）。
    """
    text = path.read_text(encoding="utf-8")
    items: list[CorpusTurn] = []
    default_session = "s1"
    current_session: str | None = default_session
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            val = obj.get("input") or obj.get("text") or obj.get("user") or obj.get("content")
            sid = obj.get("session_id") or obj.get("session") or obj.get("sid")
            if isinstance(val, str) and val.strip():
                items.append(
                    CorpusTurn(
                        text=val.strip(),
                        session_id=sid,
                        dia_id=obj.get("dia_id"),
                        speaker=obj.get("speaker"),
                        session_datetime=(
                            obj.get("session_datetime")
                            or obj.get("session_date_time")
                            or obj.get("date_time")
                        ),
                    )
                )
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            marker = re.match(r"^#\s*session\s*:?\s*(\S+)\s*$", line, re.IGNORECASE)
            if marker:
                current_session = marker.group(1)
                continue
            items.append(CorpusTurn(text=line, session_id=current_session))
    return items


def _prompt_hash(template: str) -> str:
    return hashlib.sha1(template.encode("utf-8")).hexdigest()[:8]


def build_preflight_report(
    corpus: list[CorpusTurn],
    *,
    cache_dir: str | Path,
    model_tag: str,
) -> dict:
    """Read-only estimate: extraction is exact; stateful relation count is unknown."""
    extraction_hash = _prompt_hash(EXTRACTION_PROMPT_TEMPLATE)
    relation_hash = _prompt_hash(RELATION_PROMPT_TEMPLATE)
    existing_extraction = LLMCache.read_keys(cache_dir, "extraction")
    existing_pairs = LLMCache.read_keys(cache_dir, "pairs")

    keys: list[str] = []
    prompt_chars_by_key: dict[str, int] = {}
    for turn in corpus:
        normalized = _source_context_key(
            turn.text,
            turn.speaker,
            turn.session_datetime,
        )
        key = LLMCache.compose_key(
            model_tag,
            extraction_hash,
            "extraction",
            normalized,
        )
        keys.append(key)
        if key not in prompt_chars_by_key:
            user_prompt = EXTRACTION_USER_PREFIX + _source_context_prompt(
                turn.text,
                turn.speaker,
                turn.session_datetime,
            )
            prompt_chars_by_key[key] = len(EXTRACTION_SYSTEM_PROMPT) + len(user_prompt)

    unique_keys = set(keys)
    missing_keys = unique_keys - existing_extraction
    input_chars = sum(prompt_chars_by_key[key] for key in missing_keys)
    pair_prefix = f"{model_tag}|{relation_hash}|pairs|"
    current_pair_entries = sum(key.startswith(pair_prefix) for key in existing_pairs)
    return {
        "mode": "preflight_no_api",
        "model_tag": model_tag,
        "cache_dir": str(cache_dir),
        "turns": len(corpus),
        "sessions": len({turn.session_id for turn in corpus if turn.session_id}),
        "extraction": {
            "unique_keys": len(unique_keys),
            "existing_cache_hit_turns": sum(key in existing_extraction for key in keys),
            "projected_cache_hit_turns_during_run": len(keys) - len(missing_keys),
            "cache_miss_keys": len(missing_keys),
            "minimum_logical_calls": len(missing_keys),
            "actual_http_requests": None,
            "request_count_note": (
                "minimum assumes each extraction response parses on the first logical call; "
                "parse retries and HTTP 429 retries are measured only by calibration"
            ),
            "input_chars_for_misses": input_chars,
            "rough_input_tokens_char_div_4": math.ceil(input_chars / 4),
            "rough_input_tokens_char_div_3": math.ceil(input_chars / 3),
            "token_estimate_note": "rough character heuristic only; calibration uses provider usage",
            "prompt_hash": extraction_hash,
        },
        "relation": {
            "cache_miss_keys": None,
            "minimum_logical_calls": None,
            "actual_http_requests": None,
            "reason": "depends on extraction output and evolving memory state",
            "existing_pair_cache_entries_for_model_prompt": current_pair_entries,
            "prompt_hash": relation_hash,
        },
    }


def validate_run_mode(
    *,
    formal: bool,
    no_cache: bool,
    refresh_cache: bool,
    cache_enabled: bool,
    use_mock: bool,
    strategy: str | None,
    api_key_configured: bool = True,
    temperature: float = 0.0,
) -> None:
    """Fail closed on options that would invalidate a formal run."""
    if not formal:
        return
    if no_cache:
        raise ValueError("formal mode forbids --no-cache")
    if refresh_cache:
        raise ValueError("formal mode forbids --refresh-cache")
    if not cache_enabled:
        raise ValueError("formal mode requires CACHE_ENABLED=true")
    if use_mock:
        raise ValueError("formal mode requires a real driving LLM")
    if not api_key_configured:
        raise ValueError("formal mode requires LLM_API_KEY")
    if temperature != 0.0:
        raise ValueError("formal mode requires LLM_TEMPERATURE=0.0")
    if strategy is None:
        raise ValueError("formal mode requires explicit --strategy")


def _default_usage_log(event_log: str) -> str:
    path = Path(event_log)
    suffix = path.suffix or ".jsonl"
    return str(path.with_name(f"{path.stem}_llm_usage{suffix}"))


def main() -> None:
    ap = argparse.ArgumentParser(description="用真实 LLM + 真实嵌入跑语料，产出事件日志")
    ap.add_argument("corpus", help="语料文件：.txt(每行一条) 或 .jsonl(含 input 字段)")
    ap.add_argument("--log", default="logs/events.jsonl", help="事件日志输出路径")
    ap.add_argument("--data", default="data", help="记忆存储目录")
    ap.add_argument(
        "--strategy",
        default=None,
        choices=["persistence", "frequency"],
        help="覆盖迁移策略（Phase 3 对照实验用；默认用 Config.WORKING_PROMOTION_STRATEGY）",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="运行前清空 --data 目录，避免残留状态污染实验结果（GLM #7 防护）",
    )
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="禁用两级缓存（每次都调真实 LLM）；默认开启缓存（协议 v4 §8）",
    )
    ap.add_argument(
        "--refresh-cache",
        action="store_true",
        help="运行前清空两级缓存目录（提取+分类对），强制重新调用 LLM 落盘",
    )
    ap.add_argument(
        "--preflight",
        action="store_true",
        help="只读预检：精确统计提取 cache miss/字符量；不构造 LLM 客户端、不调用 API",
    )
    ap.add_argument(
        "--preflight-out",
        default=None,
        help="可选：把 --preflight JSON 报告写入指定路径",
    )
    ap.add_argument(
        "--formal",
        action="store_true",
        help="正式运行保护：强制缓存、真实模型、显式策略，并锁定共享缓存为单写者",
    )
    ap.add_argument(
        "--usage-log",
        default=None,
        help="实际 HTTP 请求/Token JSONL；默认与 --log 同名并追加 _llm_usage",
    )
    args = ap.parse_args()

    try:
        validate_run_mode(
            formal=args.formal,
            no_cache=args.no_cache,
            refresh_cache=args.refresh_cache,
            cache_enabled=Config.CACHE_ENABLED,
            use_mock=Config.USE_MOCK_LLM,
            strategy=args.strategy,
            api_key_configured=bool(Config.LLM_API_KEY),
            temperature=Config.LLM_TEMPERATURE,
        )
    except ValueError as error:
        print(f"[abort] {error}")
        raise SystemExit(2) from error

    corpus = load_corpus(Path(args.corpus))
    if not corpus:
        print(f"[warn] 语料 {args.corpus} 为空或无有效输入。")
        return

    if args.preflight:
        if args.no_cache or args.refresh_cache or args.clean:
            print(
                "[abort] --preflight 是只读模式，不可与 --no-cache/--refresh-cache/--clean 同用"
            )
            raise SystemExit(2)
        report = build_preflight_report(
            corpus,
            cache_dir=Config.CACHE_DIR,
            model_tag=f"{Config.LLM_PROVIDER}|{Config.LLM_MODEL}",
        )
        report["configuration"] = {
            "use_mock": Config.USE_MOCK_LLM,
            "cache_enabled": Config.CACHE_ENABLED,
            "api_key_configured": bool(Config.LLM_API_KEY),
            "temperature": Config.LLM_TEMPERATURE,
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.preflight_out:
            output = Path(args.preflight_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"[ok] preflight 报告 → {output}")
        return

    if args.strategy:
        Config.WORKING_PROMOTION_STRATEGY = args.strategy

    # 两级缓存控制（协议 v4 §8，续跑即重跑）：
    # --refresh-cache 清空缓存（首跑或怀疑首跑抽风被冻结时用）；
    # --no-cache 完全禁用（每次调真实 LLM，仅诊断用）。
    if args.refresh_cache:
        from ananke.cache import LLMCache

        n = LLMCache.refresh(Config.CACHE_DIR)
        print(f"[refresh-cache] 已清空 {Config.CACHE_DIR}（删除 {n} 条缓存）")
    if args.no_cache:
        Config.CACHE_ENABLED = False
        print("[cache] 已禁用两级缓存（--no-cache）")

    # 数据目录预清理防护（GLM #7）：避免残留状态污染实验结果。
    # 红线：--clean 只清数据目录，**永远不得触碰缓存目录**（cache/ 是项目最贵的持久
    # 资产，253 轮 Qwen 调用全在里面）。若 --data 误指到缓存目录，拒绝执行。
    data_path = Path(args.data)
    if data_path.resolve() == Path(Config.CACHE_DIR).resolve():
        print(f"[abort] --data 指向缓存目录 {Config.CACHE_DIR}，拒绝清理（红线：缓存只增不删）。"
              f"\n  若确需重置缓存，请用显式 --refresh-cache，而非 --clean。")
        sys.exit(4)
    if args.clean:
        if data_path.exists():
            shutil.rmtree(data_path)
            print(f"[clean] 已清空数据目录 {args.data}")
    elif data_path.exists() and any(data_path.glob("*.jsonl")):
        print(f"[warn] 数据目录 {args.data} 非空，可能存在状态污染；加 --clean 清空后重跑。")

    # 正式 P/F 共用同一缓存但必须串行；锁阻止两个 runner 竞态重复付费。
    formal_lock = FormalRunLock(Config.CACHE_DIR) if args.formal else None
    if formal_lock is not None:
        try:
            formal_lock.acquire()
        except RuntimeError as error:
            print(f"[abort] {error}")
            raise SystemExit(3) from error
        atexit.register(formal_lock.release)

    # 真实组件
    embedding = EmbeddingEngine(Config.EMBEDDING_MODEL)
    usage_log = args.usage_log or _default_usage_log(args.log)
    llm = create_llm_client(
        usage_log=usage_log,
    )  # 内部自动迁移旧 data/cache → cache/（红线：保住已付费调用）
    pipeline = MemoryPipeline(
        MemoryStore(args.data),
        embedding,
        llm,
        EventLogger(args.log),
    )

    sessions = sorted({turn.session_id for turn in corpus if turn.session_id})
    print(f"[info] 真实 LLM 模式: {type(llm).__name__} | 嵌入模型: {Config.EMBEDDING_MODEL}")
    print(f"[info] 迁移策略: {Config.WORKING_PROMOTION_STRATEGY} | 语料条数: {len(corpus)} | session 数: {len(sessions)}")
    print(f"[info] 日志 → {args.log}\n")

    for i, turn in enumerate(corpus, 1):
        pipeline.event_logger.turn = i  # 标记轮序号，供重放等价性推断原始轮数（D 内置）
        result = pipeline.process(
            turn.text,
            session_id=turn.session_id,
            dia_id=turn.dia_id,
            speaker=turn.speaker,
            session_datetime=turn.session_datetime,
        )
        n_write = len(result["written"])
        n_consol = len(result["consolidated"])
        n_core = len(result["core"])
        tag = f"[{turn.session_id}]" if turn.session_id else ""
        print(f"[{i:>3}/{len(corpus)}]{tag} +{n_write}记忆 | 升巩固层 {n_consol} | 升慢层 {n_core} | {turn.text[:30]}")

    print(f"\n[done] 完成。分析: uv run python tools/analyze_trajectory.py --log {args.log} --data {args.data}")

    # 中→慢闸阻断可观测性（v4 §2.5，PI 漂移B 回执）：conflict 阻断器在 v0.2 无解封路径，
    # 自然语料上 contradict 高频可能使中层批量永久阻断 → core 晋升率趋零（v3 死结同构复现风险）。
    # 报告阻断率/core 数供 PI 判断第二道闸是否实质瘫痪（阈值~30%→冻结前重评阻断条件）。
    # 主测量不受影响：D 只测第一道闸，evaluate 测中层+core 两层之和，阻断只改记忆在哪层。
    from ananke.migration import block_state_summary, core_exact_duplicate_summary
    bs = block_state_summary(pipeline.memory_store)
    print(f"\n[block 可观测] 中层总数={bs['consolidated_total']} | "
          f"被阻断(conflict>0)={bs['blocked_count']} | 阻断率={bs['block_rate']:.1%} | "
          f"core 晋升数={bs['core_count']}")
    if bs["consolidated_total"] and bs["block_rate"] >= 0.30:
        print(f"  [!] 阻断率≥30%：第二道闸可能实质瘫痪。冻结前须重评阻断条件"
              f"（如改 conflict_trigger>merge_trigger 相对判据）。详见协议 v4 §2.5。")

    duplicate_summary = core_exact_duplicate_summary(pipeline.memory_store)
    print(
        "\n[CORE exact duplicate 描述性指标] "
        f"CORE={duplicate_summary['core_count']} | "
        f"normalized unique={duplicate_summary['unique_normalized_count']} | "
        f"重复条目={duplicate_summary['duplicate_entry_count']} | "
        f"重复组={duplicate_summary['duplicate_group_count']} | "
        f"重复率={duplicate_summary['normalized_exact_duplicate_rate']:.1%}"
    )

    # 两级缓存统计（协议 v4 §8）：命中率高=续跑近乎零 API；miss=首跑新调用。
    cache_metrics = None
    cache = getattr(llm, "cache", None)
    if cache is not None:
        cache_metrics = cache.stats()
        print(f"\n[cache] 提取 hits={cache_metrics['extraction']['hits']}/{cache_metrics['extraction']['hits']+cache_metrics['extraction']['misses']} "
              f"(池 {cache_metrics['extraction']['size']}) | "
              f"分类对 hits={cache_metrics['pairs']['hits']}/{cache_metrics['pairs']['hits']+cache_metrics['pairs']['misses']} "
              f"(池 {cache_metrics['pairs']['size']})")

    usage = None
    usage_stats = getattr(llm, "usage_stats", None)
    if callable(usage_stats):
        usage = usage_stats()
        print(
            "[api] "
            f"逻辑调用={usage['logical_calls']} | HTTP请求={usage['http_requests']} | "
            f"成功={usage['successes']} | 429={usage['rate_limited']} | 错误={usage['errors']} | "
            f"input_tokens={usage['prompt_tokens']} | output_tokens={usage['completion_tokens']} | "
            f"usage缺失={usage['successful_requests_without_usage']} | 日志={usage['log_path']}"
        )

    # 把零请求的 cache hit/miss 与真实 HTTP/token 计量放进同一持久事件，避免只留在 stdout。
    pipeline.event_logger.log_audit(
        "run_metrics",
        completed=True,
        corpus=str(args.corpus),
        strategy=Config.WORKING_PROMOTION_STRATEGY,
        turns=len(corpus),
        sessions=len(sessions),
        cache=cache_metrics,
        api=usage,
    )

    if formal_lock is not None:
        formal_lock.release()
        atexit.unregister(formal_lock.release)


if __name__ == "__main__":
    main()

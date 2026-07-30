import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class EventLogger:
    """Append-only JSONL audit log for every state transition."""

    def __init__(self, path: str | Path = "logs/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 当前轮序号（run_corpus / replay 在每轮 process 前设置）。写入每条事件，
        # 供重放等价性测试推断原始运行实际轮数（D 内置：默认重放上限=原始轮数，跑满是
        # 显式 opt-in）。不参与业务语义，重放指纹比对时忽略。
        self.turn: Optional[int] = None
        self._transaction_records: Optional[list[Dict[str, Any]]] = None
        self._context_fields: Dict[str, Any] = {}

    def _record(self, event: str, **fields: Any) -> Dict[str, Any]:
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            **self._context_fields,
            **fields,
        }
        if self.turn is not None:
            record["turn"] = self.turn
        return record

    def _append(self, records: list[Dict[str, Any]]) -> None:
        if not records:
            return
        with self.path.open("a", encoding="utf-8") as output:
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def log(self, event: str, **fields: Any) -> Dict[str, Any]:
        record = self._record(event, **fields)
        if self._transaction_records is not None:
            self._transaction_records.append(record)
        else:
            self._append([record])
        return record

    def log_audit(self, event: str, **fields: Any) -> Dict[str, Any]:
        """Write failure audit data immediately, outside the state-event buffer."""
        record = self._record(event, **fields)
        self._append([record])
        return record

    @contextmanager
    def context(self, **fields: Any) -> Iterator[None]:
        """Attach immutable turn-source metadata to every state and audit event."""
        previous = self._context_fields
        self._context_fields = {**previous, **fields}
        try:
            yield
        finally:
            self._context_fields = previous

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Buffer state events and publish them only after the turn succeeds."""
        if self._transaction_records is not None:
            raise RuntimeError("Nested EventLogger transactions are not supported")

        self._transaction_records = []
        try:
            yield
        except Exception:
            self._transaction_records = None
            raise
        else:
            records = self._transaction_records
            self._transaction_records = None
            path_existed = self.path.exists()
            original_size = self.path.stat().st_size if path_existed else 0
            try:
                self._append(records)
            except Exception:
                if path_existed:
                    with self.path.open("r+b") as output:
                        output.truncate(original_size)
                else:
                    self.path.unlink(missing_ok=True)
                raise
        finally:
            self._transaction_records = None

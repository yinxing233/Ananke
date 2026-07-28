import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class EventLogger:
    """Append-only JSONL audit log for every state transition."""

    def __init__(self, path: str | Path = "logs/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 当前轮序号（run_corpus / replay 在每轮 process 前设置）。写入每条事件，
        # 供重放等价性测试推断原始运行实际轮数（D 内置：默认重放上限=原始轮数，跑满是
        # 显式 opt-in）。不参与业务语义，重放指纹比对时忽略。
        self.turn: Optional[int] = None

    def log(self, event: str, **fields: Any) -> Dict[str, Any]:
        record = {"timestamp": datetime.now().isoformat(), "event": event, **fields}
        if self.turn is not None:
            record["turn"] = self.turn
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

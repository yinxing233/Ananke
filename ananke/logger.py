import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class EventLogger:
    """Append-only JSONL audit log for every state transition."""

    def __init__(self, path: str | Path = "logs/events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **fields: Any) -> Dict[str, Any]:
        record = {"timestamp": datetime.now().isoformat(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return record

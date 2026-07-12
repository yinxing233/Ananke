from pathlib import Path
from typing import List, Optional

from ananke.models import LayerEnum, MemoryEntry


class MemoryStore:
    """Small JSONL-backed store. At MVP scale rewriting one layer is intentional."""

    _FILENAMES = {LayerEnum.WORKING: "working.jsonl", LayerEnum.CONSOLIDATED: "consolidated.jsonl", LayerEnum.CORE: "core.jsonl"}

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._memories = {layer: self._load(layer) for layer in LayerEnum}

    def _path(self, layer: LayerEnum) -> Path:
        return self.data_dir / self._FILENAMES[layer]

    def _load(self, layer: LayerEnum) -> List[MemoryEntry]:
        path = self._path(layer)
        if not path.exists(): return []
        return [MemoryEntry.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _persist(self, layer: LayerEnum) -> None:
        with self._path(layer).open("w", encoding="utf-8") as output:
            for memory in self._memories[layer]: output.write(memory.model_dump_json() + "\n")

    def get_memories(self, layer: LayerEnum) -> List[MemoryEntry]: return list(self._memories[layer])
    def get_working_memories(self) -> List[MemoryEntry]: return self.get_memories(LayerEnum.WORKING)
    def get_consolidated_memories(self) -> List[MemoryEntry]: return self.get_memories(LayerEnum.CONSOLIDATED)
    def get_core_memories(self) -> List[MemoryEntry]: return self.get_memories(LayerEnum.CORE)

    def add(self, memory: MemoryEntry) -> None:
        self._memories[memory.layer].append(memory); self._persist(memory.layer)

    def remove(self, memory: MemoryEntry) -> None:
        self._memories[memory.layer] = [item for item in self._memories[memory.layer] if item.id != memory.id]; self._persist(memory.layer)

    def update(self, memory: MemoryEntry) -> None:
        for index, item in enumerate(self._memories[memory.layer]):
            if item.id == memory.id:
                self._memories[memory.layer][index] = memory; self._persist(memory.layer); return
        raise KeyError(f"Unknown memory id: {memory.id}")

    def move(self, memory: MemoryEntry, target: LayerEnum) -> None:
        source = memory.layer
        self._memories[source] = [item for item in self._memories[source] if item.id != memory.id]
        memory.layer = target; self._memories[target].append(memory)
        self._persist(source); self._persist(target)

    def find(self, memory_id: str) -> Optional[MemoryEntry]:
        return next((memory for layer in LayerEnum for memory in self._memories[layer] if memory.id == memory_id), None)

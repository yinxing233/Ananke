import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, List, Optional
from uuid import uuid4

from ananke.models import LayerEnum, MemoryEntry


class MemoryStore:
    """Small JSONL-backed store. At MVP scale rewriting one layer is intentional."""

    _FILENAMES = {LayerEnum.WORKING: "working.jsonl", LayerEnum.CONSOLIDATED: "consolidated.jsonl", LayerEnum.CORE: "core.jsonl"}

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._memories = {layer: self._load(layer) for layer in LayerEnum}
        self._transaction_active = False
        self._dirty_layers: set[LayerEnum] = set()

    def _path(self, layer: LayerEnum) -> Path:
        return self.data_dir / self._FILENAMES[layer]

    def _load(self, layer: LayerEnum) -> List[MemoryEntry]:
        path = self._path(layer)
        if not path.exists(): return []
        return [MemoryEntry.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _persist(self, layer: LayerEnum) -> None:
        if self._transaction_active:
            self._dirty_layers.add(layer)
            return
        self._persist_layers([layer])

    def _serialize(self, layer: LayerEnum) -> str:
        return "".join(memory.model_dump_json() + "\n" for memory in self._memories[layer])

    def _persist_layers(self, layers) -> None:
        """Atomically replace a set of layer files, restoring originals on failure."""
        ordered = sorted(set(layers), key=lambda layer: layer.value)
        if not ordered:
            return

        originals: Dict[LayerEnum, Optional[bytes]] = {
            layer: (
                self._path(layer).read_bytes()
                if self._path(layer).exists()
                else None
            )
            for layer in ordered
        }
        prepared: Dict[LayerEnum, Path] = {}
        try:
            for layer in ordered:
                path = self._path(layer)
                temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
                temp_path.write_text(self._serialize(layer), encoding="utf-8")
                prepared[layer] = temp_path

            for layer in ordered:
                os.replace(prepared[layer], self._path(layer))
        except Exception:
            for layer in ordered:
                path = self._path(layer)
                original = originals.get(layer)
                if original is None:
                    path.unlink(missing_ok=True)
                    continue
                restore_path = path.with_name(f".{path.name}.{uuid4().hex}.rollback")
                restore_path.write_bytes(original)
                os.replace(restore_path, path)
            raise
        finally:
            for temp_path in prepared.values():
                temp_path.unlink(missing_ok=True)

    def snapshot(self) -> Dict[LayerEnum, List[MemoryEntry]]:
        """Return a deep state snapshot suitable for turn-level rollback."""
        return {
            layer: [memory.model_copy(deep=True) for memory in memories]
            for layer, memories in self._memories.items()
        }

    def restore(self, snapshot: Dict[LayerEnum, List[MemoryEntry]]) -> None:
        """Restore an earlier snapshot in memory and on disk."""
        self._memories = {
            layer: [memory.model_copy(deep=True) for memory in snapshot[layer]]
            for layer in LayerEnum
        }
        self._persist_layers(LayerEnum)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Defer persistence until a complete turn succeeds."""
        if self._transaction_active:
            raise RuntimeError("Nested MemoryStore transactions are not supported")

        snapshot = self.snapshot()
        self._transaction_active = True
        self._dirty_layers = set()
        try:
            yield
        except Exception:
            self._memories = snapshot
            raise
        else:
            dirty_layers = set(self._dirty_layers)
            self._transaction_active = False
            try:
                self._persist_layers(dirty_layers)
            except Exception:
                self._memories = snapshot
                raise
        finally:
            self._transaction_active = False
            self._dirty_layers = set()

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

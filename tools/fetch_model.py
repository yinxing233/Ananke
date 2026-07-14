"""
Fetch the embedding model used by Ananke into the local project directory.

Ananke uses `sentence-transformers/all-MiniLM-L6-v2` (an English model; the
Phase 1 / Phase 3 experiments use English corpora). The model is NOT committed
to git (`data/` is gitignored). Run this script once after cloning to obtain it.

NOTE: we download with `local_dir_use_symlinks=False` on purpose. The default
HuggingFace snapshot uses symlinks that some sandboxed / Windows environments
cannot resolve, which surfaces at load time as a missing
`config_sentence_transformers.json`. Downloading real copies avoids that failure
mode (this is the exact workaround that made the real runs succeed).

After running, ensure `.env` contains:
    EMBEDDING_MODEL=data/all-MiniLM-L6-v2
"""
from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "all-MiniLM-L6-v2"
REPO = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        REPO,
        local_dir=str(TARGET),
        local_dir_use_symlinks=False,
    )
    print(f"[fetch_model] done -> {path}")
    print("[fetch_model] ensure .env has: EMBEDDING_MODEL=data/all-MiniLM-L6-v2")


if __name__ == "__main__":
    main()

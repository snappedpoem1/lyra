"""ChromaDB persistence wrapper for Lyra Oracle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# chromadb is an optional dependency; if it fails to import we allow the
# module to load but any functionality that depends on it will raise at
# runtime. This is useful for environments where chromadb isn't
# installed or fails to build.
try:
    import chromadb
except Exception:  # pragma: no cover - fallbacks for missing package
    chromadb = None  # type: ignore

from dotenv import load_dotenv
from oracle.config import CHROMA_COLLECTION

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = CHROMA_COLLECTION or "clap_embeddings"
LEGACY_COLLECTIONS = ("clap_embeddings", "lyra_clap_v1")

VALID_WRITE_MODES = {"readonly", "plan_only", "apply_allowed"}


def get_write_mode() -> str:
    mode = os.getenv("LYRA_WRITE_MODE", "plan_only").strip().lower()
    if mode not in VALID_WRITE_MODES:
        return "plan_only"
    return mode




def _require_chromadb() -> None:
    """Raise a RuntimeError if the chromadb library is unavailable."""
    if chromadb is None:
        raise RuntimeError(
            "Chromadb package is not available; install it to use LyraChromaStore."
        )


def _normalize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
        else:
            safe[key] = str(value)
    return safe


def _safe_get_list(value: Any) -> List:
    """Safely convert a value to a list, handling numpy arrays."""
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        return value.tolist() if value.size > 0 else []
    if isinstance(value, list):
        return value
    return []


@dataclass
class LyraChromaStore:
    persist_dir: Path = Path("./chroma_storage")
    collection_name: str = DEFAULT_COLLECTION
    allow_reset: bool = False

    def __post_init__(self) -> None:
        # ensure chromadb was imported correctly before doing any work
        if chromadb is None:
            raise RuntimeError(
                "Cannot initialize LyraChromaStore because the chromadb library "
                "failed to import. Install chromadb and try again."
            )

        persist_path = Path(self.persist_dir)
        if not persist_path.is_absolute():
            persist_path = PROJECT_ROOT / persist_path
        self.persist_dir = persist_path

        try:
            self._init_client()
        except Exception:
            if not self.allow_reset:
                raise
            backup = self.persist_dir.with_name(
                f"chroma_storage_corrupt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            if self.persist_dir.exists():
                self.persist_dir.rename(backup)
            self._init_client()

    def _init_client(self) -> None:
        _require_chromadb()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        os.environ.setdefault("CHROMA_TELEMETRY", "FALSE")
        # Use default client options so all call-sites share one compatible in-process client.
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))

        preferred = (self.collection_name or CHROMA_COLLECTION or DEFAULT_COLLECTION).strip() or DEFAULT_COLLECTION
        selected_name, selected_count = self._pick_existing_collection(preferred)
        if selected_name and selected_count > 0:
            self.collection_name = selected_name
            self.collection = self.client.get_collection(name=selected_name)
            return

        self.collection_name = preferred
        self.collection = self.client.get_or_create_collection(
            name=preferred,
            metadata={
                "description": "Lyra CLAP embeddings",
                # HNSW index settings (applied at creation only; rebuild with --force-reindex to change)
                "hnsw:space": "cosine",          # Cosine similarity for CLAP vectors
                "hnsw:construction_ef": 200,     # Better index quality (default: 100)
                "hnsw:search_ef": 100,           # Better search recall (default: 10)
                "hnsw:M": 32,                    # More connections per node (default: 16)
            },
        )

    def _pick_existing_collection(self, preferred: str) -> Tuple[str, int]:
        candidates = [preferred, *[name for name in LEGACY_COLLECTIONS if name != preferred]]
        best_name = ""
        best_count = -1
        for name in candidates:
            try:
                collection = self.client.get_collection(name=name)
                count = int(collection.count() or 0)
            except Exception:
                continue
            if count > best_count:
                best_name = name
                best_count = count
        return best_name, max(best_count, 0)

    def _persist(self) -> None:
        _require_chromadb()
        if hasattr(self.client, "persist"):
            self.client.persist()

    def _writes_allowed(self) -> bool:
        _require_chromadb()
        return get_write_mode() == "apply_allowed"

    def upsert(self, track_id: str, embedding: List[float], metadata: Dict[str, Any]) -> bool:
        _require_chromadb()
        if not self._writes_allowed():
            raise RuntimeError("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed.")

        safe_meta = _normalize_metadata(metadata)
        self.collection.upsert(
            ids=[track_id],
            embeddings=[embedding],
            metadatas=[safe_meta]
        )
        self._persist()
        return True

    def batch_upsert(
        self,
        track_ids: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]]
    ) -> bool:
        _require_chromadb()
        if not self._writes_allowed():
            raise RuntimeError("WRITE BLOCKED: LYRA_WRITE_MODE must be apply_allowed.")

        safe_meta = [_normalize_metadata(meta) for meta in metadatas]
        self.collection.upsert(
            ids=track_ids,
            embeddings=embeddings,
            metadatas=safe_meta
        )
        self._persist()
        return True

    def search(self, query_embedding: List[float], n: int = 10, where: Optional[Dict[str, Any]] = None):
        _require_chromadb()
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n,
            where=where
        )

    def get_embeddings(self, track_ids: List[str]) -> Dict[str, List[float]]:
        """Fetch embeddings by track_id.

        Returns:
            Dict of track_id -> embedding vector.
        """
        _require_chromadb()
        ids = [tid for tid in track_ids if tid]
        if not ids:
            return {}

        result = self.collection.get(ids=ids, include=["embeddings"])
        out: Dict[str, List[float]] = {}
        
        # Use safe list conversion to handle numpy arrays properly
        result_ids = _safe_get_list(result.get("ids"))
        embeddings = _safe_get_list(result.get("embeddings"))

        for idx, tid in enumerate(result_ids):
            if idx >= len(embeddings):
                continue
            emb = embeddings[idx]
            if emb is None:
                continue
            # Handle numpy array or list
            if isinstance(emb, np.ndarray):
                out[str(tid)] = emb.tolist()
            else:
                out[str(tid)] = list(emb)

        return out

    def verify_persistence(self) -> bool:
        _require_chromadb()
        try:
            return self.collection.count() > 0
        except Exception:
            return False


if __name__ == "__main__":
    load_dotenv(override=True)
    store = LyraChromaStore()
    print(f"Collection '{store.collection_name}' contains {store.collection.count()} items")

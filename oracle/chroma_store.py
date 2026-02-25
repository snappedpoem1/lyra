"""ChromaDB persistence wrapper for Lyra Oracle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
from typing import Any, Dict, List, Optional

import numpy as np
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = "lyra_clap_v1"

VALID_WRITE_MODES = {"readonly", "plan_only", "apply_allowed"}


def get_write_mode() -> str:
    mode = os.getenv("LYRA_WRITE_MODE", "plan_only").strip().lower()
    if mode not in VALID_WRITE_MODES:
        return "plan_only"
    return mode


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
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        os.environ.setdefault("CHROMA_TELEMETRY", "FALSE")
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "description": "Lyra CLAP embeddings",
                # HNSW index settings (applied at creation only; rebuild with --force-reindex to change)
                "hnsw:space": "cosine",          # Cosine similarity for CLAP vectors
                "hnsw:construction_ef": 200,     # Better index quality (default: 100)
                "hnsw:search_ef": 100,           # Better search recall (default: 10)
                "hnsw:M": 32,                    # More connections per node (default: 16)
            },
        )

    def _persist(self) -> None:
        if hasattr(self.client, "persist"):
            self.client.persist()

    def _writes_allowed(self) -> bool:
        return get_write_mode() == "apply_allowed"

    def upsert(self, track_id: str, embedding: List[float], metadata: Dict[str, Any]) -> bool:
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
        try:
            return self.collection.count() > 0
        except Exception:
            return False


if __name__ == "__main__":
    load_dotenv(override=True)
    store = LyraChromaStore()
    print(f"Collection '{store.collection_name}' contains {store.collection.count()} items")

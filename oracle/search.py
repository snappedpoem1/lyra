"""Semantic search for Lyra Oracle.

Includes:
- search(): CLAP semantic-only search
- hybrid_search(): semantic search with metadata + dimensional filters
"""

from __future__ import annotations

from functools import lru_cache
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# chromadb can be troublesome on Python 3.14; import lazily
# so that lightweight operations (like remix search tests) don't fail.
try:
    from oracle.chroma_store import LyraChromaStore
except Exception:  # pragma: no cover - environment may not have chromadb or pydantic errors
    LyraChromaStore = None

from oracle.config import CHROMA_PATH
from oracle.db.schema import get_connection
# CLAPEmbedder is heavy (librosa) so import inside search when needed
from oracle.vibe_descriptors import describe_scores

# Keep query-time embedding aligned with the indexer / default CLAP model.
MODEL_NAME = "laion/larger_clap_music"
REMIX_HINT_TOKENS = (
    "remix",
    "edit",
    "rework",
    "bootleg",
    "vip",
    "mashup",
    "flip",
    "mix",
)


@lru_cache(maxsize=1)
def _get_clap_embedder():
    from oracle.embedders.clap_embedder import CLAPEmbedder

    return CLAPEmbedder(
        model_name=MODEL_NAME,
        cache_dir=os.getenv("HF_HOME"),
        use_fallback=False,
    )


@lru_cache(maxsize=1)
def _get_chroma_store():
    return LyraChromaStore(persist_dir=str(CHROMA_PATH))


def search(query_text: str, n: int = 10) -> List[Dict[str, Any]]:
    if LyraChromaStore is None:
        return fallback_text_search(query_text, n=n, reason="chromadb unavailable")

    try:
        embedder = _get_clap_embedder()
        store = _get_chroma_store()

        vector = embedder.embed_text(query_text)
        if vector is None:
            return fallback_text_search(query_text, n=n, reason="text embedding unavailable")

        results = store.search(vector.tolist(), n=n)
        ids = results.get("ids", [[]])[0]

        if not ids:
            return []

        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()

        distances = results.get("distances", [[]])[0]
        output: List[Dict[str, Any]] = []
        for idx, track_id in enumerate(ids, 1):
            score = 0.0
            if idx - 1 < len(distances):
                try:
                    # Chroma returns cosine distance where lower is better.
                    score = max(0.0, 1.0 - float(distances[idx - 1]))
                except (TypeError, ValueError):
                    score = 0.0
            cursor.execute(
                "SELECT artist, title, album, year, filepath FROM tracks WHERE track_id = ?",
                (track_id,)
            )
            row = cursor.fetchone()
            if row:
                output.append(
                    {
                        "rank": str(idx),
                        "track_id": track_id,
                        "artist": row[0] or "Unknown",
                        "title": row[1] or "Unknown",
                        "album": row[2] or "",
                        "year": row[3] or "",
                        "path": row[4] or "",
                        "score": score,
                    }
                )
            else:
                output.append({"rank": str(idx), "track_id": track_id, "path": track_id, "score": score})

        conn.close()
        return output
    except Exception as exc:
        return fallback_text_search(query_text, n=n, reason=str(exc))


def _tokenize_query(query_text: str) -> List[str]:
    return [token for token in re.findall(r"[A-Za-z0-9]+", str(query_text or "").lower()) if token]


def fallback_text_search(query_text: str, n: int = 10, reason: str = "") -> List[Dict[str, Any]]:
    """Fallback metadata search when semantic search is unavailable."""
    limit = max(1, int(n or 10))
    query_text = str(query_text or "").strip()
    query_lower = query_text.lower()
    terms = _tokenize_query(query_text)[:8]
    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    rows: List[tuple[Any, ...]] = []

    if terms:
        where_parts = ["status = 'active'"]
        params: List[Any] = []
        token_clauses = []
        for term in terms:
            like = f"%{term}%"
            token_clauses.append("(lower(artist) LIKE ? OR lower(title) LIKE ? OR lower(album) LIKE ?)")
            params.extend([like, like, like])
        where_parts.append("(" + " OR ".join(token_clauses) + ")")
        sql = f"""
            SELECT track_id, artist, title, album, year, filepath
            FROM tracks
            WHERE {' AND '.join(where_parts)}
            ORDER BY artist COLLATE NOCASE ASC, album COLLATE NOCASE ASC, title COLLATE NOCASE ASC
            LIMIT ?
        """
        cursor.execute(sql, (*params, max(limit * 25, 100)))
        rows = cursor.fetchall()

    fallback_mode = "metadata"
    if not rows:
        cursor.execute(
            """
            SELECT track_id, artist, title, album, year, filepath
            FROM tracks
            WHERE status = 'active'
            ORDER BY updated_at DESC, created_at DESC, rowid DESC
            LIMIT ?
            """,
            (max(limit * 5, 50),),
        )
        rows = cursor.fetchall()
        fallback_mode = "library"

    conn.close()

    scored_rows: List[tuple[float, tuple[Any, ...]]] = []
    for row in rows:
        artist = str(row[1] or "")
        title = str(row[2] or "")
        album = str(row[3] or "")
        text_blob = f"{artist} {title} {album}".lower()
        token_hits = sum(1 for term in terms if term in text_blob)
        exact_phrase_bonus = 1 if query_lower and query_lower in text_blob else 0
        score = 0.0
        if terms:
            score = (token_hits / len(terms)) + exact_phrase_bonus
        scored_rows.append((score, row))

    scored_rows.sort(
        key=lambda item: (
            -item[0],
            str(item[1][1] or "").lower(),
            str(item[1][3] or "").lower(),
            str(item[1][2] or "").lower(),
        )
    )

    output: List[Dict[str, Any]] = []
    for idx, (score, row) in enumerate(scored_rows[:limit], 1):
        output.append(
            {
                "rank": str(idx),
                "track_id": row[0],
                "artist": row[1] or "Unknown",
                "title": row[2] or "Unknown",
                "album": row[3] or "",
                "year": row[4] or "",
                "path": row[5] or "",
                "score": round(float(score), 4),
                "fallback_reason": reason or "metadata fallback",
                "fallback_mode": fallback_mode,
            }
        )
    return output


def find_remixes(
    artist: str | None = None,
    album: str | None = None,
    track: str | None = None,
    n: int = 100,
    include_candidates: bool = True,
    sort_by: str = "recent",
) -> List[Dict[str, Any]]:
    """Find remix-like tracks with optional artist/album/track filters.

    Uses explicit classifier labels (version_type='remix') and optional token-based
    fallback matching for tracks that have not been classified as remix yet.
    """
    limit = max(1, min(int(n or 100), 1000))

    def norm(s: Any) -> str:
        return str(s or "").strip().lower()

    where_parts: List[str] = ["t.status = 'active'"]
    params: List[Any] = []

    artist_q = norm(artist)
    album_q = norm(album)
    track_q = norm(track)

    if artist_q:
        like = f"%{artist_q}%"
        where_parts.append("(lower(t.artist) LIKE ? OR lower(t.title) LIKE ?)")
        params.extend([like, like])

    if album_q:
        where_parts.append("lower(COALESCE(t.album, '')) LIKE ?")
        params.append(f"%{album_q}%")

    if track_q:
        where_parts.append("lower(t.title) LIKE ?")
        params.append(f"%{track_q}%")

    remix_predicates = ["lower(COALESCE(t.version_type, '')) = 'remix'"]
    if include_candidates:
        for token in REMIX_HINT_TOKENS:
            remix_predicates.append("lower(t.title) LIKE ?")
            params.append(f"%{token}%")
            remix_predicates.append("lower(COALESCE(t.album, '')) LIKE ?")
            params.append(f"%{token}%")

    where_parts.append("(" + " OR ".join(remix_predicates) + ")")

    order_sql = "t.updated_at DESC, t.rowid DESC"
    sort_key = norm(sort_by)
    if sort_key in {"confidence", "score"}:
        order_sql = "t.confidence DESC, t.updated_at DESC, t.rowid DESC"
    elif sort_key in {"artist"}:
        order_sql = "lower(t.artist) ASC, lower(t.title) ASC"
    elif sort_key in {"title", "track"}:
        order_sql = "lower(t.title) ASC, lower(t.artist) ASC"

    sql = f"""
        SELECT
            t.track_id,
            t.artist,
            t.title,
            t.album,
            t.year,
            t.version_type,
            t.confidence,
            t.filepath
        FROM tracks t
        WHERE {' AND '.join(where_parts)}
        ORDER BY {order_sql}
        LIMIT ?
    """
    params.append(limit)

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    results: List[Dict[str, Any]] = []
    for row in rows:
        track_id, artist_name, title, album_name, year, version_type, confidence, filepath = row
        text_blob = f"{title or ''} {album_name or ''}".lower()
        token_hits = [tok for tok in REMIX_HINT_TOKENS if tok in text_blob]
        is_strict = norm(version_type) == "remix"
        results.append(
            {
                "track_id": str(track_id),
                "artist": artist_name or "Unknown",
                "title": title or "Unknown",
                "album": album_name or "",
                "year": year or "",
                "version_type": version_type or "",
                "confidence": float(confidence) if confidence is not None else None,
                "path": filepath or "",
                "is_strict_remix": is_strict,
                "match_type": "classified" if is_strict else "candidate",
                "matched_tokens": token_hits,
            }
        )

    return results


def hybrid_search(
    query: str | None = None,
    filters: dict[str, Any] | None = None,
    dimension_ranges: dict[str, Tuple[float, float]] | None = None,
    sort_by: str = "relevance",
    top_k: int = 20,
) -> List[Dict[str, Any]]:
    """Hybrid search combining semantic similarity with metadata and dimensional filters.

    Args:
        query: Semantic query text (optional)
        filters: Metadata filters (optional)
        dimension_ranges: Dimension range constraints, e.g. {"energy": (0.5, 1.0)}
        sort_by: relevance | year | artist | title | bpm
        top_k: Maximum results

    Returns:
        List of track dicts.
    """

    top_k = max(1, min(int(top_k or 20), 500))
    filters = filters or {}
    dimension_ranges = dimension_ranges or {}

    def norm(s: Any) -> str:
        return str(s or "").strip().lower()

    def parse_year(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(str(value).strip()[:4])
        except Exception:
            return None

    def parse_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except Exception:
            return None

    def infer_quality(item: Dict[str, Any]) -> str:
        bitrate = item.get("bitrate")
        path = norm(item.get("path"))
        if path.endswith((".flac", ".wav", ".aiff", ".alac")):
            return "lossless"
        if bitrate is not None:
            try:
                kbps = int(float(bitrate) / 1000.0) if float(bitrate) > 1000 else int(float(bitrate))
                if kbps >= 900:
                    return "lossless"
                if kbps >= 320:
                    return "320k"
                return "<320k"
            except Exception:
                pass
        return "unknown"

    # Step 1: get candidate IDs (semantic or full library slice)
    candidate_ids: List[str]
    semantic_rank: dict[str, int] = {}

    if query and str(query).strip():
        raw = search(str(query).strip(), n=max(top_k * 8, top_k))
        candidate_ids = [r.get("track_id") for r in raw if r.get("track_id")]
        for r in raw:
            tid = r.get("track_id")
            if tid and r.get("rank"):
                try:
                    semantic_rank[tid] = int(r["rank"])
                except Exception:
                    continue
    else:
        # No semantic query: fall back to DB-only ordering.
        conn = get_connection(timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT track_id FROM tracks WHERE status = 'active' ORDER BY rowid DESC LIMIT ?", (max(top_k * 8, top_k),))
        candidate_ids = [row[0] for row in cursor.fetchall() if row and row[0]]
        conn.close()

    if not candidate_ids:
        return []

    # Step 2: fetch metadata + optional scores
    placeholders = ",".join("?" for _ in candidate_ids)
    base_sql = f"""
         SELECT t.track_id, t.artist, t.title, t.album, t.year, t.genre, t.duration, t.filepath,
               t.version_type, t.confidence, t.bpm, t.bitrate, t.source, t.rowid
        FROM tracks t
        WHERE t.track_id IN ({placeholders}) AND t.status = 'active'
    """

    conn = get_connection(timeout=10.0)
    cursor = conn.cursor()
    cursor.execute(base_sql, tuple(candidate_ids))
    rows = cursor.fetchall()

    # Pull scores if table exists
    score_map: dict[str, dict[str, float]] = {}
    try:
        cursor.execute(
            f"SELECT track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia FROM track_scores WHERE track_id IN ({placeholders})",
            tuple(candidate_ids),
        )
        for row in cursor.fetchall():
            tid = row[0]
            score_map[str(tid)] = {
                "energy": row[1],
                "valence": row[2],
                "tension": row[3],
                "density": row[4],
                "warmth": row[5],
                "movement": row[6],
                "space": row[7],
                "rawness": row[8],
                "complexity": row[9],
                "nostalgia": row[10],
            }
    except Exception:
        # Missing track_scores table or incompatible schema: treat as "no scores".
        score_map = {}

    play_count_map: dict[str, int] = {}
    try:
        cursor.execute(
            f"SELECT track_id, COUNT(*) FROM playback_history WHERE track_id IN ({placeholders}) GROUP BY track_id",
            tuple(candidate_ids),
        )
        for tid, cnt in cursor.fetchall():
            play_count_map[str(tid)] = int(cnt or 0)
    except Exception:
        play_count_map = {}

    conn.close()

    results: List[Dict[str, Any]] = []
    for (
        track_id,
        artist,
        title,
        album,
        year,
        genre,
        duration,
        filepath,
        version_type,
        confidence,
        bpm,
        bitrate,
        source,
        created_rowid,
    ) in rows:
        tid = str(track_id)
        item: Dict[str, Any] = {
            "track_id": tid,
            "artist": artist or "Unknown",
            "title": title or "Unknown",
            "album": album or "",
            "year": year or "",
            "genre": genre or "",
            "duration": float(duration) if duration is not None else None,
            "path": filepath or "",
            "version_type": version_type or "",
            "confidence": float(confidence) if confidence is not None else None,
            "bpm": float(bpm) if bpm is not None else None,
            "bitrate": int(bitrate) if bitrate is not None else None,
            "source": source or "",
            "created_at": float(created_rowid) if created_rowid is not None else None,
            "played_count": int(play_count_map.get(tid, 0)),
            "relevance_rank": semantic_rank.get(tid),
            "scores": score_map.get(tid),
        }
        item["vibe"] = describe_scores(item.get("scores"))
        item["quality"] = infer_quality(item)
        results.append(item)

    # Step 3: apply metadata filters
    f_artist = norm(filters.get("artist"))
    f_title = norm(filters.get("title"))
    f_album = norm(filters.get("album"))
    f_version = norm(filters.get("version_type") or filters.get("type"))
    f_source = norm(filters.get("source"))
    f_quality = norm(filters.get("quality"))
    has_lyrics = filters.get("has_lyrics")
    is_instrumental = filters.get("is_instrumental")

    exclude_remix = bool(filters.get("exclude_remix") or filters.get("not_remix"))

    bpm_min = parse_float(filters.get("bpm_min"))
    bpm_max = parse_float(filters.get("bpm_max"))
    duration_min = parse_float(filters.get("duration_min"))
    duration_max = parse_float(filters.get("duration_max"))

    genre_filter = filters.get("genre")
    allowed_genres: Optional[List[str]] = None
    if isinstance(genre_filter, str) and genre_filter.strip():
        allowed_genres = [genre_filter.strip().lower()]
    elif isinstance(genre_filter, list):
        allowed_genres = [str(g).strip().lower() for g in genre_filter if str(g).strip()]

    y_min = parse_year(filters.get("year_min"))
    y_max = parse_year(filters.get("year_max"))

    lyrics_index: dict[tuple[str, str], bool] = {}
    if has_lyrics is True or has_lyrics is False:
        try:
            conn = get_connection(timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("SELECT artist, track, lyrics FROM track_metadata")
            for a, t, lyr in cursor.fetchall():
                lyrics_index[(norm(a), norm(t))] = bool(str(lyr or "").strip())
            conn.close()
        except Exception:
            lyrics_index = {}

    filtered: List[Dict[str, Any]] = []
    for item in results:
        if f_artist and f_artist not in norm(item.get("artist")):
            continue
        if f_title and f_title not in norm(item.get("title")):
            continue
        if f_album and f_album not in norm(item.get("album")):
            continue
        if f_version and f_version != norm(item.get("version_type")):
            continue
        if f_source and f_source != norm(item.get("source")):
            continue
        if f_quality and f_quality != norm(item.get("quality")):
            continue
        if exclude_remix and "remix" in norm(item.get("version_type")):
            continue

        if allowed_genres:
            g = norm(item.get("genre"))
            if not any(ag in g for ag in allowed_genres):
                continue

        if y_min is not None or y_max is not None:
            yr = parse_year(item.get("year"))
            if yr is None:
                continue
            if y_min is not None and yr < y_min:
                continue
            if y_max is not None and yr > y_max:
                continue

        bpm = item.get("bpm")
        if bpm_min is not None:
            if bpm is None or float(bpm) < bpm_min:
                continue
        if bpm_max is not None:
            if bpm is None or float(bpm) > bpm_max:
                continue

        duration = item.get("duration")
        if duration_min is not None:
            if duration is None or float(duration) < duration_min:
                continue
        if duration_max is not None:
            if duration is None or float(duration) > duration_max:
                continue

        if has_lyrics is True or has_lyrics is False:
            key = (norm(item.get("artist")), norm(item.get("title")))
            item_has_lyrics = bool(lyrics_index.get(key, False))
            if bool(has_lyrics) != item_has_lyrics:
                continue

        if is_instrumental is True:
            title = norm(item.get("title"))
            genre = norm(item.get("genre"))
            if "instrumental" not in title and "instrumental" not in genre:
                continue
        elif is_instrumental is False:
            title = norm(item.get("title"))
            if "instrumental" in title:
                continue

        filtered.append(item)

    # Step 4: apply dimensional ranges when we have scores
    if dimension_ranges:
        dim_filtered: List[Dict[str, Any]] = []
        for item in filtered:
            scores = item.get("scores") or {}
            ok = True
            for dim, rng in dimension_ranges.items():
                if not isinstance(rng, (list, tuple)) or len(rng) != 2:
                    continue
                lo, hi = float(rng[0]), float(rng[1])
                val = scores.get(dim)
                if val is None:
                    ok = False
                    break
                if val < lo or val > hi:
                    ok = False
                    break
            if ok:
                dim_filtered.append(item)
        filtered = dim_filtered

    # Step 5: sort
    sort_by = (sort_by or "relevance").strip().lower()
    reverse = False
    if sort_by.startswith("-"):
        reverse = True
        sort_by = sort_by[1:]

    if sort_by == "relevance":
        filtered.sort(key=lambda x: (x.get("relevance_rank") is None, x.get("relevance_rank") or 10**9), reverse=reverse)
    elif sort_by in {"added", "recently_added"}:
        filtered.sort(key=lambda x: (x.get("created_at") is None, x.get("created_at") or 0.0), reverse=(not reverse))
    elif sort_by in {"played", "most_played"}:
        filtered.sort(key=lambda x: (x.get("played_count") or 0), reverse=(not reverse))
    elif sort_by in {"least_played"}:
        filtered.sort(key=lambda x: (x.get("played_count") is None, x.get("played_count") or 0), reverse=reverse)
    elif sort_by == "year":
        filtered.sort(key=lambda x: (norm(x.get("year")) == "", norm(x.get("year"))), reverse=reverse)
    elif sort_by == "artist":
        filtered.sort(key=lambda x: norm(x.get("artist")), reverse=reverse)
    elif sort_by == "title":
        filtered.sort(key=lambda x: norm(x.get("title")), reverse=reverse)
    elif sort_by == "bpm":
        filtered.sort(key=lambda x: (x.get("bpm") is None, x.get("bpm") or 0.0), reverse=reverse)
    elif sort_by == "duration":
        filtered.sort(key=lambda x: (x.get("duration") is None, x.get("duration") or 0.0), reverse=reverse)
    elif sort_by in {"energy", "valence", "tension", "density", "warmth", "movement", "space", "rawness", "complexity", "nostalgia"}:
        filtered.sort(
            key=lambda x: ((x.get("scores") or {}).get(sort_by) is None, (x.get("scores") or {}).get(sort_by) or 0.0),
            reverse=reverse,
        )
    elif sort_by == "random":
        random.shuffle(filtered)

    return filtered[:top_k]


def _main() -> None:
    load_dotenv(override=True)
    import argparse

    parser = argparse.ArgumentParser(description="Semantic search")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--n", type=int, default=10, help="Number of results")
    args = parser.parse_args()

    results = search(args.query, n=args.n)
    for item in results:
        print(
            f"{item.get('rank')}. {item.get('artist', '')} - {item.get('title', '')}"
            f" | {item.get('album', '')} | {item.get('year', '')} | {item.get('path', '')}"
        )


if __name__ == "__main__":
    _main()

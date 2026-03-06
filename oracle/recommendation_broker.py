"""Recommendation broker for explainable multi-provider discovery."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any

from oracle.api.helpers import _load_track
from oracle.db.schema import get_connection
from oracle.enrichers.lastfm import build_track_profile
from oracle.integrations.listenbrainz import get_top_recordings_for_artist_name
from oracle.radio import Radio

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_WEIGHTS: dict[str, float] = {
    "local": 0.55,
    "lastfm": 0.2,
    "listenbrainz": 0.25,
}
DEFAULT_LIMIT = 12
SUPPORTED_MODES = {"flow", "chaos", "discovery"}
SUPPORTED_NOVELTY_BANDS = {"safe", "stretch", "chaos"}


def _clamp_score(value: Any, *, default: float = 0.0) -> float:
    """Clamp a score-like value into the inclusive ``0.0`` to ``1.0`` range."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, numeric))


def _normalize_mode(value: Any) -> str:
    """Resolve arbitrary client input into a supported broker mode."""
    mode = str(value or "flow").strip().lower()
    if mode not in SUPPORTED_MODES:
        return "flow"
    return mode


def _normalize_novelty_band(value: Any) -> str:
    """Resolve arbitrary client input into a supported novelty band."""
    band = str(value or "stretch").strip().lower()
    if band not in SUPPORTED_NOVELTY_BANDS:
        return "stretch"
    return band


def _normalize_provider_weights(raw_weights: dict[str, Any] | None) -> dict[str, float]:
    """Return normalized provider weights, falling back to defaults."""
    merged = dict(DEFAULT_PROVIDER_WEIGHTS)
    if raw_weights:
        for provider in DEFAULT_PROVIDER_WEIGHTS:
            if provider not in raw_weights:
                continue
            try:
                merged[provider] = max(0.0, float(raw_weights[provider] or 0.0))
            except (TypeError, ValueError):
                merged[provider] = DEFAULT_PROVIDER_WEIGHTS[provider]

    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_PROVIDER_WEIGHTS)
    return {
        provider: round(weight / total, 4)
        for provider, weight in merged.items()
    }


def _load_track_from_library(track_id: str) -> dict[str, Any] | None:
    """Load and enrich one library track row for API responses."""
    track = _load_track(track_id)
    if not track:
        return None
    filepath = str(track.get("filepath") or "").strip()
    track["file_exists"] = bool(filepath and Path(filepath).exists())
    return track


def _load_latest_track_id() -> str | None:
    """Return the most recently updated/added active library track ID."""
    conn = get_connection(timeout=5.0)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT track_id
            FROM tracks
            WHERE status = 'active'
            ORDER BY COALESCE(updated_at, created_at, added_at, 0) DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return str(row[0]).strip() or None


def _load_track_by_artist_title(artist: str, title: str) -> dict[str, Any] | None:
    """Find the best local library match for an artist/title pair."""
    conn = get_connection(timeout=5.0)
    try:
        cursor = conn.cursor()
        row = cursor.execute(
            """
            SELECT track_id, artist, title, album, year, version_type, confidence, duration, filepath
            FROM tracks
            WHERE status = 'active'
              AND LOWER(artist) = LOWER(?)
              AND LOWER(title) = LOWER(?)
            ORDER BY COALESCE(confidence, 0) DESC, COALESCE(updated_at, created_at, added_at, 0) DESC
            LIMIT 1
            """,
            (artist.strip(), title.strip()),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    track = {
        "track_id": row[0],
        "artist": row[1],
        "title": row[2],
        "album": row[3],
        "year": row[4],
        "version_type": row[5],
        "confidence": row[6],
        "duration": row[7],
        "filepath": row[8],
    }
    filepath = str(track.get("filepath") or "").strip()
    track["file_exists"] = bool(filepath and Path(filepath).exists())
    return track


def _listenbrainz_threshold_for_band(novelty_band: str) -> tuple[int, int]:
    """Map novelty band to ListenBrainz popularity thresholds."""
    if novelty_band == "safe":
        return 6, 500
    if novelty_band == "chaos":
        return 12, 25
    return 8, 125


def _build_provider_status(
    *,
    available: bool,
    used: bool,
    weight: float,
    message: str,
    matched_local_tracks: int = 0,
    acquisition_candidates: int = 0,
) -> dict[str, Any]:
    """Build a JSON-safe provider status payload."""
    return {
        "available": available,
        "used": used,
        "weight": round(weight, 4),
        "message": message,
        "matched_local_tracks": matched_local_tracks,
        "acquisition_candidates": acquisition_candidates,
    }


def _local_reason_for_mode(mode: str, seed_track: dict[str, Any] | None) -> str:
    """Generate a concise plain-language explanation for local signals."""
    if mode == "flow":
        if seed_track:
            return f"Local flow engine held continuity from {seed_track.get('artist', 'Unknown')} - {seed_track.get('title', 'Unknown')}."
        return "Local flow engine selected a continuity match from the current library thread."
    if mode == "chaos":
        return "Local chaos engine selected a deliberate pivot without leaving your library."
    return "Local discovery engine surfaced a low-play cut with hidden-gem potential."


def _recommend_from_local(
    *,
    mode: str,
    seed_track_id: str | None,
    limit: int,
    novelty_band: str,
    weight: float,
    seed_track: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the local provider via the canonical radio engine."""
    del novelty_band
    radio = Radio()
    safe_limit = max(1, limit * 2)

    try:
        if mode == "flow":
            if not seed_track_id:
                return [], _build_provider_status(
                    available=False,
                    used=False,
                    weight=weight,
                    message="Flow mode needs a seed track.",
                )
            rows = radio.get_flow_track(seed_track_id, count=safe_limit)
        elif mode == "chaos":
            rows = radio.get_chaos_track(seed_track_id, count=safe_limit)
        else:
            rows = radio.get_discovery_track(count=safe_limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[broker] local provider failed: %s", exc)
        return [], _build_provider_status(
            available=False,
            used=False,
            weight=weight,
            message=f"Local provider failed: {exc}",
        )

    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        track_id = str(row.get("track_id") or "").strip()
        if not track_id:
            continue
        track = _load_track_from_library(track_id)
        if not track:
            continue

        rank_bonus = 1.0 - min(index / max(len(rows), 1), 0.9)
        if mode == "flow":
            raw_score = 0.45 + 0.45 * _clamp_score(row.get("compatibility"), default=rank_bonus)
        elif mode == "chaos":
            raw_score = 0.5 + 0.35 * rank_bonus
        else:
            play_count = max(0, int(row.get("play_count") or 0))
            raw_score = 0.35 + 0.5 * (1.0 / (1.0 + math.log10(play_count + 1)))

        candidates.append(
            {
                "track": track,
                "provider": "local",
                "label": f"local-{mode}",
                "raw_score": round(raw_score, 4),
                "weighted_score": round(raw_score * weight, 4),
                "reason": _local_reason_for_mode(mode, seed_track),
            }
        )

    return candidates, _build_provider_status(
        available=True,
        used=bool(candidates),
        weight=weight,
        message=f"Local {mode} provider ready.",
        matched_local_tracks=len(candidates),
    )


def _recommend_from_lastfm(
    *,
    seed_track: dict[str, Any] | None,
    limit: int,
    weight: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Resolve local and acquisition candidates from Last.fm similar tracks."""
    if not seed_track:
        return [], [], _build_provider_status(
            available=False,
            used=False,
            weight=weight,
            message="No seed track available for Last.fm.",
        )

    if not os.getenv("LASTFM_API_KEY", "").strip():
        return [], [], _build_provider_status(
            available=False,
            used=False,
            weight=weight,
            message="LASTFM_API_KEY is not configured.",
        )

    payload = build_track_profile(
        str(seed_track.get("artist") or "").strip(),
        str(seed_track.get("title") or "").strip(),
    )
    similar_rows = payload.get("similar_tracks", []) if isinstance(payload, dict) else []
    if not isinstance(similar_rows, list) or not similar_rows:
        return [], [], _build_provider_status(
            available=True,
            used=False,
            weight=weight,
            message="Last.fm returned no similar-track results.",
        )

    local_matches: list[dict[str, Any]] = []
    acquisition_candidates: list[dict[str, Any]] = []
    for index, row in enumerate(similar_rows[: max(limit * 3, 12)]):
        if not isinstance(row, dict):
            continue
        artist = str(row.get("artist") or "").strip()
        title = str(row.get("title") or "").strip()
        if not artist or not title:
            continue
        raw_score = round(max(0.2, 1.0 - (index / max(len(similar_rows), 1))), 4)
        reason = (
            "Last.fm similar-track signal "
            f"from {seed_track.get('artist', 'Unknown')} - {seed_track.get('title', 'Unknown')}."
        )

        track = _load_track_by_artist_title(artist, title)
        if track:
            local_matches.append(
                {
                    "track": track,
                    "provider": "lastfm",
                    "label": "lastfm-similar-track",
                    "raw_score": raw_score,
                    "weighted_score": round(raw_score * weight, 4),
                    "reason": reason,
                }
            )
            continue

        acquisition_candidates.append(
            {
                "artist": artist,
                "title": title,
                "provider": "lastfm",
                "reason": reason,
                "score": round(raw_score * weight, 4),
            }
        )

    return local_matches, acquisition_candidates[:limit], _build_provider_status(
        available=True,
        used=True,
        weight=weight,
        message="Last.fm similar-track provider active.",
        matched_local_tracks=len(local_matches),
        acquisition_candidates=len(acquisition_candidates),
    )


def _recommend_from_listenbrainz(
    *,
    seed_track: dict[str, Any] | None,
    novelty_band: str,
    limit: int,
    weight: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Resolve local and acquisition candidates from ListenBrainz artist popularity."""
    if not seed_track:
        return [], [], _build_provider_status(
            available=False,
            used=False,
            weight=weight,
            message="No seed track available for ListenBrainz.",
        )

    artist_name = str(seed_track.get("artist") or "").strip()
    if not artist_name:
        return [], [], _build_provider_status(
            available=False,
            used=False,
            weight=weight,
            message="Seed track is missing artist metadata.",
        )

    fetch_count, min_listen_count = _listenbrainz_threshold_for_band(novelty_band)
    recordings = get_top_recordings_for_artist_name(artist_name, count=max(fetch_count, limit))
    if not recordings:
        return [], [], _build_provider_status(
            available=True,
            used=False,
            weight=weight,
            message="ListenBrainz returned no artist-popularity data.",
        )

    local_matches: list[dict[str, Any]] = []
    acquisition_candidates: list[dict[str, Any]] = []
    for row in recordings:
        title = str(row.get("title") or "").strip()
        artist = str(row.get("artist") or artist_name).strip()
        listen_count = max(0, int(row.get("listen_count") or 0))
        if not title or listen_count < min_listen_count:
            continue

        raw_score = round(
            0.35 + 0.45 * min(1.0, math.log10(max(listen_count, 10)) / 5.0),
            4,
        )
        reason = (
            "ListenBrainz community popularity "
            f"for {artist_name} ({novelty_band} band)."
        )
        track = _load_track_by_artist_title(artist, title)
        if track:
            local_matches.append(
                {
                    "track": track,
                    "provider": "listenbrainz",
                    "label": f"listenbrainz-{novelty_band}",
                    "raw_score": raw_score,
                    "weighted_score": round(raw_score * weight, 4),
                    "reason": reason,
                }
            )
            continue

        acquisition_candidates.append(
            {
                "artist": artist,
                "title": title,
                "provider": "listenbrainz",
                "reason": reason,
                "score": round(raw_score * weight, 4),
            }
        )

    return local_matches, acquisition_candidates[:limit], _build_provider_status(
        available=True,
        used=True,
        weight=weight,
        message="ListenBrainz community provider active.",
        matched_local_tracks=len(local_matches),
        acquisition_candidates=len(acquisition_candidates),
    )


def _merge_recommendation_candidates(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Aggregate provider signals into a single ranked list."""
    merged: dict[str, dict[str, Any]] = {}

    for candidate in candidates:
        track = candidate["track"]
        track_id = str(track.get("track_id") or "").strip()
        if not track_id:
            continue

        signal = {
            "provider": candidate["provider"],
            "label": candidate["label"],
            "score": candidate["weighted_score"],
            "raw_score": candidate["raw_score"],
            "reason": candidate["reason"],
        }

        if track_id not in merged:
            merged_track = dict(track)
            merged_track["broker_score"] = candidate["weighted_score"]
            merged_track["provider_signals"] = [signal]
            merged_track["reasons"] = [
                {
                    "type": candidate["provider"],
                    "text": candidate["reason"],
                    "score": candidate["weighted_score"],
                }
            ]
            merged_track["reason"] = candidate["reason"]
            merged_track["provenance"] = candidate["label"]
            merged[track_id] = merged_track
            continue

        existing = merged[track_id]
        existing["broker_score"] = round(
            float(existing.get("broker_score") or 0.0) + float(candidate["weighted_score"] or 0.0),
            4,
        )
        existing.setdefault("provider_signals", []).append(signal)
        existing.setdefault("reasons", []).append(
            {
                "type": candidate["provider"],
                "text": candidate["reason"],
                "score": candidate["weighted_score"],
            }
        )
        best_signal = max(existing["provider_signals"], key=lambda item: float(item.get("score") or 0.0))
        existing["reason"] = str(best_signal.get("reason") or existing.get("reason") or "")
        existing["provenance"] = ", ".join(
            sorted({str(item.get("provider") or "") for item in existing["provider_signals"] if item.get("provider")})
        )

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("broker_score") or 0.0),
            str(item.get("artist") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return ranked[:limit]


def recommend_tracks(
    *,
    seed_track_id: str | None,
    mode: str,
    novelty_band: str,
    limit: int = DEFAULT_LIMIT,
    provider_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explainable recommendations from local and external providers."""
    resolved_limit = max(1, min(int(limit), 24))
    resolved_mode = _normalize_mode(mode)
    resolved_novelty = _normalize_novelty_band(novelty_band)
    resolved_weights = _normalize_provider_weights(provider_weights)
    resolved_seed_track_id = seed_track_id or _load_latest_track_id()
    seed_track = _load_track_from_library(resolved_seed_track_id) if resolved_seed_track_id else None

    provider_status: dict[str, dict[str, Any]] = {}
    provider_candidates: list[dict[str, Any]] = []
    acquisition_candidates: list[dict[str, Any]] = []

    local_candidates, provider_status["local"] = _recommend_from_local(
        mode=resolved_mode,
        seed_track_id=resolved_seed_track_id,
        limit=resolved_limit,
        novelty_band=resolved_novelty,
        weight=resolved_weights["local"],
        seed_track=seed_track,
    )
    provider_candidates.extend(local_candidates)

    lastfm_candidates, lastfm_acquisition, provider_status["lastfm"] = _recommend_from_lastfm(
        seed_track=seed_track,
        limit=resolved_limit,
        weight=resolved_weights["lastfm"],
    )
    provider_candidates.extend(lastfm_candidates)
    acquisition_candidates.extend(lastfm_acquisition)

    listenbrainz_candidates, listenbrainz_acquisition, provider_status["listenbrainz"] = _recommend_from_listenbrainz(
        seed_track=seed_track,
        novelty_band=resolved_novelty,
        limit=resolved_limit,
        weight=resolved_weights["listenbrainz"],
    )
    provider_candidates.extend(listenbrainz_candidates)
    acquisition_candidates.extend(listenbrainz_acquisition)

    merged_candidates = _merge_recommendation_candidates(
        provider_candidates,
        limit=resolved_limit,
    )
    acquisition_ranked = sorted(
        acquisition_candidates,
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )[:resolved_limit]

    return {
        "schema_version": "2026-03-06",
        "mode": resolved_mode,
        "novelty_band": resolved_novelty,
        "seed_track_id": resolved_seed_track_id,
        "seed_track": seed_track,
        "provider_weights": resolved_weights,
        "provider_status": provider_status,
        "candidates": merged_candidates,
        "acquisition_candidates": acquisition_ranked,
    }

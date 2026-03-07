"""Recommendation broker for explainable multi-provider discovery.

Implements SPEC-004: every provider returns a normalized ProviderResult,
and the broker emits a versioned response with provider_reports,
merged recommendations with preserved evidence, and degradation summaries.
"""

from __future__ import annotations

import logging
import math
import os
import json
import time
from pathlib import Path
from typing import Any

from oracle.api.helpers import _load_track
from oracle.db.schema import get_connection, get_write_mode
from oracle.enrichers.lastfm import build_track_profile
from oracle.integrations.listenbrainz import get_top_recordings_for_artist_name
from oracle.provider_contract import (
    BROKER_SCHEMA_VERSION,
    Availability,
    Candidate,
    EvidenceItem,
    ProviderError,
    ProviderResult,
    ProviderStatus,
    ProviderTimer,
)
from oracle.provider_health import update_from_result as _update_health
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
SUPPORTED_FEEDBACK_TYPES = {"accepted", "queued", "skipped", "replayed", "acquire_requested"}
_FEEDBACK_LOOKBACK_SECONDS = 60 * 60 * 24 * 90
_FEEDBACK_SCORE_WEIGHTS: dict[str, float] = {
    "accepted": 0.18,
    "queued": 0.12,
    "replayed": 0.08,
    "skipped": -0.2,
}


def _ensure_feedback_table(conn: Any) -> None:
    """Create feedback storage lazily so the app can use it immediately."""
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT,
            artist TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            feedback_type TEXT NOT NULL,
            seed_track_id TEXT,
            mode TEXT,
            novelty_band TEXT,
            provider TEXT,
            metadata_json TEXT,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_track_created "
        "ON recommendation_feedback(track_id, created_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_feedback_created "
        "ON recommendation_feedback(feedback_type, created_at DESC)"
    )
    conn.commit()


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


def _normalize_feedback_type(value: Any) -> str:
    """Resolve arbitrary input into a supported feedback type."""
    feedback_type = str(value or "").strip().lower()
    if feedback_type not in SUPPORTED_FEEDBACK_TYPES:
        raise ValueError(
            "feedback_type must be one of accepted|queued|skipped|replayed|acquire_requested"
        )
    return feedback_type


def record_feedback(
    *,
    feedback_type: Any,
    track_id: str | None = None,
    artist: str | None = None,
    title: str | None = None,
    seed_track_id: str | None = None,
    mode: Any = None,
    novelty_band: Any = None,
    provider: Any = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a recommendation or acquisition feedback event."""
    resolved_feedback_type = _normalize_feedback_type(feedback_type)
    resolved_track_id = str(track_id or "").strip() or None
    resolved_artist = str(artist or "").strip()
    resolved_title = str(title or "").strip()
    if not resolved_track_id and (not resolved_artist or not resolved_title):
        raise ValueError("track_id or artist/title is required")

    if get_write_mode() != "apply_allowed":
        return {
            "status": "write_blocked",
            "feedback_type": resolved_feedback_type,
            "track_id": resolved_track_id,
            "artist": resolved_artist,
            "title": resolved_title,
        }

    payload = dict(metadata or {})
    conn = get_connection(timeout=10.0)
    try:
        _ensure_feedback_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO recommendation_feedback
                (track_id, artist, title, feedback_type, seed_track_id, mode, novelty_band, provider, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
            """,
            (
                resolved_track_id,
                resolved_artist,
                resolved_title,
                resolved_feedback_type,
                str(seed_track_id or "").strip() or None,
                _normalize_mode(mode) if mode is not None else None,
                _normalize_novelty_band(novelty_band) if novelty_band is not None else None,
                str(provider or "").strip() or None,
                json.dumps(payload, separators=(",", ":"), sort_keys=True) if payload else None,
            ),
        )
        conn.commit()
        feedback_id = int(cursor.lastrowid or 0)
    finally:
        conn.close()

    return {
        "status": "ok",
        "feedback_id": feedback_id,
        "feedback_type": resolved_feedback_type,
        "track_id": resolved_track_id,
        "artist": resolved_artist,
        "title": resolved_title,
    }


def _load_feedback_bias(track_ids: list[str]) -> dict[str, float]:
    """Return small ranking adjustments derived from recent user feedback."""
    normalized_track_ids = [str(track_id).strip() for track_id in track_ids if str(track_id or "").strip()]
    if not normalized_track_ids:
        return {}

    placeholders = ", ".join(["?"] * len(normalized_track_ids))
    conn = get_connection(timeout=10.0)
    try:
        _ensure_feedback_table(conn)
        cursor = conn.cursor()
        rows = cursor.execute(
            f"""
            SELECT track_id, feedback_type, COUNT(*)
            FROM recommendation_feedback
            WHERE track_id IN ({placeholders})
              AND created_at >= ?
            GROUP BY track_id, feedback_type
            """,
            (*normalized_track_ids, float(time.time() - _FEEDBACK_LOOKBACK_SECONDS)),
        ).fetchall()
    finally:
        conn.close()

    tallies: dict[str, float] = {}
    for track_id, feedback_type, count in rows:
        key = str(track_id or "").strip()
        event_type = str(feedback_type or "").strip().lower()
        weight = _FEEDBACK_SCORE_WEIGHTS.get(event_type, 0.0)
        if not key or weight == 0.0:
            continue
        tallies[key] = tallies.get(key, 0.0) + (weight * int(count or 0))

    return {
        track_id: round(max(-0.35, min(0.35, score)), 4)
        for track_id, score in tallies.items()
    }


def _apply_feedback_bias(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Blend persisted recommendation outcomes into broker ranking."""
    track_ids = [str(candidate.get("track_id") or "").strip() for candidate in candidates]
    feedback_bias = _load_feedback_bias(track_ids)
    if not feedback_bias:
        return candidates

    updated: list[dict[str, Any]] = []
    for candidate in candidates:
        track_id = str(candidate.get("track_id") or "").strip()
        bias = feedback_bias.get(track_id, 0.0)
        if bias == 0.0:
            updated.append(candidate)
            continue

        adjusted = dict(candidate)
        adjusted["feedback_bias"] = bias
        adjusted["broker_score"] = round(float(candidate.get("broker_score") or 0.0) + bias, 4)
        evidence = list(adjusted.get("evidence") or [])
        evidence.append({
            "type": "feedback_history",
            "source": "broker",
            "weight": round(abs(bias), 4),
            "text": "Past accepts and replays reinforce this pick."
            if bias > 0
            else "Past skips are suppressing this pick.",
        })
        adjusted["evidence"] = evidence
        # Keep legacy reasons for backward compat during transition
        reasons = list(adjusted.get("reasons") or [])
        reasons.append(
            {
                "type": "feedback",
                "text": "Past accepts and replays reinforce this pick."
                if bias > 0
                else "Past skips are suppressing this pick.",
                "score": bias,
            }
        )
        adjusted["reasons"] = reasons
        updated.append(adjusted)

    return sorted(
        updated,
        key=lambda item: (
            float(item.get("broker_score") or 0.0),
            str(item.get("artist") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )


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


def _local_reason_for_mode(mode: str, seed_track: dict[str, Any] | None) -> str:
    """Generate a concise plain-language explanation for local signals."""
    if mode == "flow":
        if seed_track:
            return f"Local flow engine held continuity from {seed_track.get('artist', 'Unknown')} - {seed_track.get('title', 'Unknown')}."
        return "Local flow engine selected a continuity match from the current library thread."
    if mode == "chaos":
        return "Local chaos engine selected a deliberate pivot without leaving your library."
    return "Local discovery engine surfaced a low-play cut with hidden-gem potential."


def _seed_context_str(seed_track: dict[str, Any] | None) -> str:
    """Build a human-readable seed context string."""
    if not seed_track:
        return "no seed track"
    artist = seed_track.get("artist", "Unknown")
    title = seed_track.get("title", "Unknown")
    return f"{artist} - {title}"


# ---------------------------------------------------------------------------
# Provider adapters — each returns a normalized ProviderResult
# ---------------------------------------------------------------------------


def _recommend_from_local(
    *,
    mode: str,
    seed_track_id: str | None,
    limit: int,
    novelty_band: str,
    weight: float,
    seed_track: dict[str, Any] | None,
) -> ProviderResult:
    """Run the local provider via the canonical radio engine."""
    timer = ProviderTimer()
    seed_ctx = _seed_context_str(seed_track)

    with timer:
        radio = Radio()
        safe_limit = max(1, limit * 2)

        try:
            if mode == "flow":
                if not seed_track_id:
                    return ProviderResult(
                        provider="local",
                        status=ProviderStatus.FAILED,
                        message="Flow mode needs a seed track.",
                        seed_context=seed_ctx,
                        errors=[ProviderError(code="no_seed", message="Flow mode needs a seed track.")],
                        timing_ms=timer.elapsed_ms,
                    )
                rows = radio.get_flow_track(seed_track_id, count=safe_limit)
            elif mode == "chaos":
                rows = radio.get_chaos_track(seed_track_id, count=safe_limit)
            else:
                rows = radio.get_discovery_track(count=safe_limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[broker] local provider failed: %s", exc)
            return ProviderResult(
                provider="local",
                status=ProviderStatus.FAILED,
                message=f"Local provider failed: {exc}",
                seed_context=seed_ctx,
                errors=[ProviderError(code="provider_error", message=str(exc))],
                timing_ms=timer.elapsed_ms,
            )

        candidates: list[Candidate] = []
        reason_text = _local_reason_for_mode(mode, seed_track)

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
                evidence_type = "embedding_neighbor"
                evidence_raw = row.get("compatibility")
            elif mode == "chaos":
                raw_score = 0.5 + 0.35 * rank_bonus
                evidence_type = "embedding_neighbor"
                evidence_raw = {"rank_bonus": round(rank_bonus, 4)}
            else:
                play_count = max(0, int(row.get("play_count") or 0))
                raw_score = 0.35 + 0.5 * (1.0 / (1.0 + math.log10(play_count + 1)))
                evidence_type = "low_play_discovery"
                evidence_raw = {"play_count": play_count}

            candidates.append(Candidate(
                track_id=track_id,
                artist=str(track.get("artist") or ""),
                title=str(track.get("title") or ""),
                album=track.get("album"),
                score=round(raw_score * weight, 4),
                confidence=round(raw_score, 4),
                novelty_band_fit=novelty_band,
                availability=Availability.LOCAL,
                provenance_label=f"local-{mode}",
                track_data=track,
                evidence=[EvidenceItem(
                    type=evidence_type,
                    source="local",
                    weight=round(raw_score * weight, 4),
                    text=reason_text,
                    raw_value=evidence_raw,
                )],
            ))

    if not candidates:
        return ProviderResult(
            provider="local",
            status=ProviderStatus.EMPTY,
            message=f"Local {mode} provider returned no candidates.",
            seed_context=seed_ctx,
            timing_ms=timer.elapsed_ms,
        )

    return ProviderResult(
        provider="local",
        status=ProviderStatus.OK,
        message=f"Local {mode} provider ready.",
        seed_context=seed_ctx,
        candidates=candidates,
        timing_ms=timer.elapsed_ms,
    )


def _recommend_from_lastfm(
    *,
    seed_track: dict[str, Any] | None,
    limit: int,
    weight: float,
    novelty_band: str,
) -> ProviderResult:
    """Resolve candidates from Last.fm similar tracks."""
    timer = ProviderTimer()
    seed_ctx = _seed_context_str(seed_track)

    with timer:
        if not seed_track:
            return ProviderResult(
                provider="lastfm",
                status=ProviderStatus.FAILED,
                message="No seed track available for Last.fm.",
                seed_context=seed_ctx,
                errors=[ProviderError(code="no_seed", message="No seed track available.")],
                timing_ms=timer.elapsed_ms,
            )

        if not os.getenv("LASTFM_API_KEY", "").strip():
            return ProviderResult(
                provider="lastfm",
                status=ProviderStatus.FAILED,
                message="LASTFM_API_KEY is not configured.",
                seed_context=seed_ctx,
                errors=[ProviderError(code="not_configured", message="LASTFM_API_KEY is not configured.")],
                timing_ms=timer.elapsed_ms,
            )

        try:
            payload = build_track_profile(
                str(seed_track.get("artist") or "").strip(),
                str(seed_track.get("title") or "").strip(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[broker] lastfm provider failed: %s", exc)
            return ProviderResult(
                provider="lastfm",
                status=ProviderStatus.FAILED,
                message=f"Last.fm provider failed: {exc}",
                seed_context=seed_ctx,
                errors=[ProviderError(code="provider_error", message=str(exc))],
                timing_ms=timer.elapsed_ms,
            )

        similar_rows = payload.get("similar_tracks", []) if isinstance(payload, dict) else []
        if not isinstance(similar_rows, list) or not similar_rows:
            return ProviderResult(
                provider="lastfm",
                status=ProviderStatus.EMPTY,
                message="Last.fm returned no similar-track results.",
                seed_context=seed_ctx,
                timing_ms=timer.elapsed_ms,
            )

        candidates: list[Candidate] = []
        for index, row in enumerate(similar_rows[: max(limit * 3, 12)]):
            if not isinstance(row, dict):
                continue
            artist = str(row.get("artist") or "").strip()
            title = str(row.get("title") or "").strip()
            if not artist or not title:
                continue
            raw_score = round(max(0.2, 1.0 - (index / max(len(similar_rows), 1))), 4)
            reason_text = (
                "Last.fm similar-track signal "
                f"from {seed_track.get('artist', 'Unknown')} - {seed_track.get('title', 'Unknown')}."
            )

            track = _load_track_by_artist_title(artist, title)
            if track:
                candidates.append(Candidate(
                    track_id=str(track.get("track_id") or ""),
                    artist=artist,
                    title=title,
                    album=track.get("album"),
                    score=round(raw_score * weight, 4),
                    confidence=round(raw_score, 4),
                    novelty_band_fit=novelty_band,
                    availability=Availability.LOCAL,
                    provenance_label="lastfm-similar-track",
                    track_data=track,
                    evidence=[EvidenceItem(
                        type="similar_track",
                        source="lastfm",
                        weight=round(raw_score * weight, 4),
                        text=reason_text,
                        raw_value={"match_score": row.get("match"), "rank": index},
                    )],
                ))
            else:
                candidates.append(Candidate(
                    track_id=None,
                    artist=artist,
                    title=title,
                    score=round(raw_score * weight, 4),
                    confidence=round(raw_score, 4),
                    novelty_band_fit=novelty_band,
                    availability=Availability.ACQUISITION_LEAD,
                    provenance_label="lastfm-similar-track",
                    evidence=[EvidenceItem(
                        type="similar_track",
                        source="lastfm",
                        weight=round(raw_score * weight, 4),
                        text=reason_text,
                        raw_value={"match_score": row.get("match"), "rank": index},
                    )],
                ))

    if not candidates:
        return ProviderResult(
            provider="lastfm",
            status=ProviderStatus.EMPTY,
            message="Last.fm returned no usable similar-track results.",
            seed_context=seed_ctx,
            timing_ms=timer.elapsed_ms,
        )

    return ProviderResult(
        provider="lastfm",
        status=ProviderStatus.OK,
        message="Last.fm similar-track provider active.",
        seed_context=seed_ctx,
        candidates=candidates,
        timing_ms=timer.elapsed_ms,
    )


def _recommend_from_listenbrainz(
    *,
    seed_track: dict[str, Any] | None,
    novelty_band: str,
    limit: int,
    weight: float,
) -> ProviderResult:
    """Resolve candidates from ListenBrainz artist popularity."""
    timer = ProviderTimer()
    seed_ctx = _seed_context_str(seed_track)

    with timer:
        if not seed_track:
            return ProviderResult(
                provider="listenbrainz",
                status=ProviderStatus.FAILED,
                message="No seed track available for ListenBrainz.",
                seed_context=seed_ctx,
                errors=[ProviderError(code="no_seed", message="No seed track available.")],
                timing_ms=timer.elapsed_ms,
            )

        artist_name = str(seed_track.get("artist") or "").strip()
        if not artist_name:
            return ProviderResult(
                provider="listenbrainz",
                status=ProviderStatus.FAILED,
                message="Seed track is missing artist metadata.",
                seed_context=seed_ctx,
                errors=[ProviderError(code="no_artist", message="Seed track is missing artist metadata.")],
                timing_ms=timer.elapsed_ms,
            )

        try:
            fetch_count, min_listen_count = _listenbrainz_threshold_for_band(novelty_band)
            recordings = get_top_recordings_for_artist_name(artist_name, count=max(fetch_count, limit))
        except Exception as exc:  # noqa: BLE001
            logger.warning("[broker] listenbrainz provider failed: %s", exc)
            return ProviderResult(
                provider="listenbrainz",
                status=ProviderStatus.FAILED,
                message=f"ListenBrainz provider failed: {exc}",
                seed_context=seed_ctx,
                errors=[ProviderError(code="provider_error", message=str(exc))],
                timing_ms=timer.elapsed_ms,
            )

        if not recordings:
            return ProviderResult(
                provider="listenbrainz",
                status=ProviderStatus.EMPTY,
                message="ListenBrainz returned no artist-popularity data.",
                seed_context=seed_ctx,
                timing_ms=timer.elapsed_ms,
            )

        candidates: list[Candidate] = []
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
            reason_text = (
                "ListenBrainz community popularity "
                f"for {artist_name} ({novelty_band} band)."
            )
            track = _load_track_by_artist_title(artist, title)
            if track:
                candidates.append(Candidate(
                    track_id=str(track.get("track_id") or ""),
                    artist=artist,
                    title=title,
                    album=track.get("album"),
                    score=round(raw_score * weight, 4),
                    confidence=round(raw_score, 4),
                    novelty_band_fit=novelty_band,
                    availability=Availability.LOCAL,
                    provenance_label=f"listenbrainz-{novelty_band}",
                    track_data=track,
                    evidence=[EvidenceItem(
                        type="community_popularity",
                        source="listenbrainz",
                        weight=round(raw_score * weight, 4),
                        text=reason_text,
                        raw_value={"listen_count": listen_count, "min_threshold": min_listen_count},
                    )],
                ))
            else:
                candidates.append(Candidate(
                    track_id=None,
                    artist=artist,
                    title=title,
                    score=round(raw_score * weight, 4),
                    confidence=round(raw_score, 4),
                    novelty_band_fit=novelty_band,
                    availability=Availability.ACQUISITION_LEAD,
                    provenance_label=f"listenbrainz-{novelty_band}",
                    evidence=[EvidenceItem(
                        type="community_popularity",
                        source="listenbrainz",
                        weight=round(raw_score * weight, 4),
                        text=reason_text,
                        raw_value={"listen_count": listen_count, "min_threshold": min_listen_count},
                    )],
                ))

    if not candidates:
        return ProviderResult(
            provider="listenbrainz",
            status=ProviderStatus.EMPTY,
            message="ListenBrainz returned no qualifying recordings for this band.",
            seed_context=seed_ctx,
            timing_ms=timer.elapsed_ms,
        )

    return ProviderResult(
        provider="listenbrainz",
        status=ProviderStatus.OK,
        message="ListenBrainz community provider active.",
        seed_context=seed_ctx,
        candidates=candidates,
        timing_ms=timer.elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Broker merge logic
# ---------------------------------------------------------------------------


def _merge_provider_candidates(
    provider_results: list[ProviderResult],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge candidates from multiple providers into ranked recommendations and acquisition leads."""
    merged: dict[str, dict[str, Any]] = {}
    acquisition_leads: list[dict[str, Any]] = []

    for result in provider_results:
        for candidate in result.candidates:
            if candidate.availability == Availability.ACQUISITION_LEAD:
                acquisition_leads.append({
                    "artist": candidate.artist,
                    "title": candidate.title,
                    "provider": result.provider,
                    "reason": candidate.evidence[0].text if candidate.evidence else "",
                    "score": candidate.score,
                    "evidence": [e.to_dict() for e in candidate.evidence],
                })
                continue

            track_id = str(candidate.track_id or "").strip()
            if not track_id:
                continue

            evidence_dicts = [e.to_dict() for e in candidate.evidence]
            signal = {
                "provider": result.provider,
                "label": candidate.provenance_label,
                "score": candidate.score,
                "raw_score": candidate.confidence,
                "reason": candidate.evidence[0].text if candidate.evidence else "",
            }

            if track_id not in merged:
                track = dict(candidate.track_data) if candidate.track_data else {
                    "track_id": track_id,
                    "artist": candidate.artist,
                    "title": candidate.title,
                    "album": candidate.album,
                }
                track["broker_score"] = candidate.score
                track["provider_signals"] = [signal]
                track["evidence"] = evidence_dicts
                track["reasons"] = [{
                    "type": result.provider,
                    "text": candidate.evidence[0].text if candidate.evidence else "",
                    "score": candidate.score,
                }]
                track["reason"] = candidate.evidence[0].text if candidate.evidence else ""
                track["provenance"] = candidate.provenance_label
                track["confidence"] = candidate.confidence
                track["novelty_band_fit"] = candidate.novelty_band_fit
                track["availability"] = candidate.availability.value
                track["explanation"] = _build_explanation(result.provider, candidate)
                merged[track_id] = track
                continue

            existing = merged[track_id]
            existing["broker_score"] = round(
                float(existing.get("broker_score") or 0.0) + candidate.score, 4
            )
            existing.setdefault("provider_signals", []).append(signal)
            existing.setdefault("evidence", []).extend(evidence_dicts)
            existing.setdefault("reasons", []).append({
                "type": result.provider,
                "text": candidate.evidence[0].text if candidate.evidence else "",
                "score": candidate.score,
            })
            best_signal = max(
                existing["provider_signals"],
                key=lambda s: float(s.get("score") or 0.0),
            )
            existing["reason"] = str(best_signal.get("reason") or existing.get("reason") or "")
            existing["provenance"] = ", ".join(
                sorted({
                    str(s.get("provider") or "")
                    for s in existing["provider_signals"]
                    if s.get("provider")
                })
            )
            existing["explanation"] = _build_merged_explanation(existing)

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("broker_score") or 0.0),
            str(item.get("artist") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    acquisition_ranked = sorted(
        acquisition_leads,
        key=lambda item: float(item.get("score") or 0.0),
        reverse=True,
    )

    return ranked[:limit], acquisition_ranked[:limit]


def _build_explanation(provider: str, candidate: Candidate) -> str:
    """Build a plain-language explanation for a single-provider recommendation."""
    if candidate.evidence:
        return candidate.evidence[0].text
    return f"Recommended by {provider}."


def _build_merged_explanation(merged_track: dict[str, Any]) -> str:
    """Build a plain-language explanation for a multi-provider recommendation."""
    providers = merged_track.get("provenance", "")
    reasons = merged_track.get("reasons", [])
    if len(reasons) == 1:
        return str(reasons[0].get("text") or f"Recommended by {providers}.")
    parts = [str(r.get("text") or "") for r in reasons if r.get("text")]
    if parts:
        return " ".join(parts[:2])
    return f"Recommended by {providers}."


# ---------------------------------------------------------------------------
# Public broker entry point
# ---------------------------------------------------------------------------


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

    # Run all providers and collect normalized results
    provider_results: list[ProviderResult] = []

    for result in [
        _recommend_from_local(
            mode=resolved_mode,
            seed_track_id=resolved_seed_track_id,
            limit=resolved_limit,
            novelty_band=resolved_novelty,
            weight=resolved_weights["local"],
            seed_track=seed_track,
        ),
        _recommend_from_lastfm(
            seed_track=seed_track,
            limit=resolved_limit,
            weight=resolved_weights["lastfm"],
            novelty_band=resolved_novelty,
        ),
        _recommend_from_listenbrainz(
            seed_track=seed_track,
            novelty_band=resolved_novelty,
            limit=resolved_limit,
            weight=resolved_weights["listenbrainz"],
        ),
    ]:
        _update_health(result)
        provider_results.append(result)

    # Merge candidates across providers
    merged_candidates, acquisition_leads = _merge_provider_candidates(
        provider_results,
        limit=resolved_limit,
    )

    # Apply feedback bias
    merged_candidates = _apply_feedback_bias(merged_candidates)

    # Build provider reports (SPEC-004 section 4.1)
    provider_reports = [r.to_dict() for r in provider_results]

    # Compute degradation summary
    degraded_providers = [
        r for r in provider_results
        if r.status in (ProviderStatus.DEGRADED, ProviderStatus.FAILED)
    ]
    is_degraded = bool(degraded_providers)
    degradation_summary = (
        "; ".join(f"{r.provider}: {r.message}" for r in degraded_providers)
        if degraded_providers
        else None
    )

    # Build legacy-compatible provider_status for transition period
    provider_status: dict[str, dict[str, Any]] = {}
    for r in provider_results:
        local_count = sum(
            1 for c in r.candidates
            if c.availability == Availability.LOCAL
        )
        acq_count = sum(
            1 for c in r.candidates
            if c.availability == Availability.ACQUISITION_LEAD
        )
        provider_status[r.provider] = {
            "available": r.status != ProviderStatus.FAILED,
            "used": r.status == ProviderStatus.OK,
            "weight": resolved_weights.get(r.provider, 0.0),
            "message": r.message,
            "matched_local_tracks": local_count,
            "acquisition_candidates": acq_count,
        }

    return {
        "schema_version": BROKER_SCHEMA_VERSION,
        "mode": resolved_mode,
        "novelty_band": resolved_novelty,
        "seed_track_id": resolved_seed_track_id,
        "seed_track": seed_track,
        "seed": _seed_context_str(seed_track),
        "provider_weights": resolved_weights,
        # SPEC-004 fields
        "provider_reports": provider_reports,
        "recommendations": merged_candidates,
        "degraded": is_degraded,
        "degradation_summary": degradation_summary,
        # Legacy compat fields (will be removed after Wave 6 UI transition)
        "provider_status": provider_status,
        "candidates": merged_candidates,
        "acquisition_candidates": acquisition_leads,
    }

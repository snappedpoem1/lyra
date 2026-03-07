"""Reusable explanation generation for Lyra Core legibility.

Converts raw recommendation evidence, provider signals, and feedback
history into concise, product-grade explanation text.

Explanation primitives supported:
- similarity / adjacency
- playlist fit
- emotional profile fit
- artist/era continuity
- energy / intensity movement
- novelty / familiarity balance
- replay / save / skip behavior signals
- explicit user feedback effects
- bridge logic
- momentum / sequencing logic
- session-context reasoning
- fallback reasoning when signal quality is low
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from oracle.db.schema import get_connection

logger = logging.getLogger(__name__)

# ── Evidence type → product language templates ──────────────────────────────

_EVIDENCE_TEMPLATES: dict[str, list[str]] = {
    "embedding_neighbor": [
        "Close in texture to {seed}.",
        "Holds continuity from {seed}.",
        "Sits nearby in the embedding space of {seed}.",
    ],
    "similar_track": [
        "Similar-track signal from {seed}.",
        "Connected to {seed} through listener overlap.",
        "Fans of {seed} also reach for this.",
    ],
    "community_popularity": [
        "Community-verified pick for {artist} listeners.",
        "Popular with {artist} fans ({band} band).",
        "Backed by community listening data.",
    ],
    "scout_bridge": [
        "Bridge from {seed_genre} into {bridge_genre}.",
        "Cross-genre link between {seed_genre} and {bridge_genre}.",
        "Scout found a path from {seed_genre} toward {bridge_genre}.",
    ],
    "community_weather": [
        "Trending in community listening right now.",
        "Current community momentum behind this track.",
        "Riding a wave of community attention.",
    ],
    "feedback_history": [
        "Reinforced by your past accepts and replays.",
        "Your listening history supports this pick.",
        "Pushed forward because you favored similar cuts.",
    ],
    "low_play_discovery": [
        "Low-play hidden gem from your library.",
        "Rarely played — worth rediscovering.",
        "Sitting deep in your library, waiting to surface.",
    ],
}

_FEEDBACK_NEGATIVE_TEMPLATES: list[str] = [
    "Pushed down by past skips.",
    "Your skip history is suppressing this pick.",
    "Less favored based on recent feedback.",
]

_FALLBACK_TEMPLATES: list[str] = [
    "Selected by Lyra Core from available signals.",
    "Chosen from the current library thread.",
    "Picked using the best available context.",
]

# ── Mode descriptions ───────────────────────────────────────────────────────

_MODE_CONTEXT: dict[str, str] = {
    "flow": "Maintaining listening continuity.",
    "chaos": "Deliberate pivot away from the current thread.",
    "discovery": "Surfacing low-play or unfamiliar material.",
}

# ── Novelty band descriptions ──────────────────────────────────────────────

_BAND_CONTEXT: dict[str, str] = {
    "safe": "Staying close to familiar ground.",
    "stretch": "Pushing slightly beyond the usual.",
    "chaos": "Exploring far from the comfort zone.",
}

# ── Dimension descriptors ──────────────────────────────────────────────────

_DIM_HIGH: dict[str, str] = {
    "energy": "high-energy",
    "valence": "upbeat",
    "tension": "tense",
    "density": "dense",
    "warmth": "warm",
    "movement": "kinetic",
    "space": "spacious",
    "rawness": "raw",
    "complexity": "complex",
    "nostalgia": "nostalgic",
}

_DIM_LOW: dict[str, str] = {
    "energy": "low-energy",
    "valence": "dark",
    "tension": "relaxed",
    "density": "sparse",
    "warmth": "cool",
    "movement": "still",
    "space": "intimate",
    "rawness": "polished",
    "complexity": "simple",
    "nostalgia": "contemporary",
}


def _pick_template(templates: list[str], candidate: dict[str, Any]) -> str:
    """Deterministically pick a template based on candidate identity."""
    artist = str(candidate.get("artist") or "")
    title = str(candidate.get("title") or "")
    idx = (hash(f"{artist}:{title}") % len(templates)) if templates else 0
    return templates[idx] if templates else ""


def _format_template(template: str, context: dict[str, str]) -> str:
    """Safely format a template with available context values."""
    try:
        return template.format_map({k: v for k, v in context.items() if v})
    except (KeyError, IndexError):
        return template


def _describe_top_dimensions(candidate: dict[str, Any], limit: int = 2) -> str | None:
    """Describe the most prominent emotional dimensions of a track."""
    dims: list[tuple[str, float]] = []
    for dim in _DIM_HIGH:
        val = candidate.get(dim)
        if isinstance(val, (int, float)) and val != 0:
            dims.append((dim, float(val)))

    if not dims:
        return None

    dims.sort(key=lambda d: abs(d[1]), reverse=True)
    parts: list[str] = []
    for dim, val in dims[:limit]:
        if val > 0.3:
            parts.append(_DIM_HIGH.get(dim, dim))
        elif val < -0.3:
            parts.append(_DIM_LOW.get(dim, dim))

    if not parts:
        return None
    return ", ".join(parts)


def generate_explanation(
    candidate: dict[str, Any],
    *,
    seed_track: dict[str, Any] | None = None,
    mode: str = "flow",
    novelty_band: str = "stretch",
) -> str:
    """Generate a concise, product-grade explanation for one recommendation.

    Returns a short readable string grounded in actual evidence. Falls back
    to honest heuristic phrasing when signal quality is low.

    Args:
        candidate: Merged broker candidate dict with evidence, provider_signals, etc.
        seed_track: The seed track dict, if available.
        mode: Broker mode (flow/chaos/discovery).
        novelty_band: Novelty band (safe/stretch/chaos).

    Returns:
        A one-to-two sentence explanation string.
    """
    parts: list[str] = []
    evidence_items: list[dict[str, Any]] = candidate.get("evidence") or []
    seed_artist = str((seed_track or {}).get("artist", "")).strip()
    seed_title = str((seed_track or {}).get("title", "")).strip()
    seed_label = f"{seed_artist} — {seed_title}" if seed_artist and seed_title else ""
    seed_genre = str((seed_track or {}).get("genre", "")).strip()

    context = {
        "seed": seed_label or "the current track",
        "artist": str(candidate.get("artist") or ""),
        "band": novelty_band,
        "seed_genre": seed_genre or "the current genre",
        "bridge_genre": "",
    }

    # Extract the strongest evidence item
    if evidence_items:
        strongest = max(evidence_items, key=lambda e: float(e.get("weight") or 0))
        etype = str(strongest.get("type") or "")
        raw_val = strongest.get("raw_value") or {}

        # Populate bridge genre from raw_value if scout
        if isinstance(raw_val, dict):
            context["bridge_genre"] = str(raw_val.get("bridge_genre", "")) or ""

        # Check feedback direction
        if etype == "feedback_history":
            bias = float(strongest.get("weight") or 0)
            if bias < 0:
                templates = _FEEDBACK_NEGATIVE_TEMPLATES
            else:
                templates = _EVIDENCE_TEMPLATES.get(etype, _FALLBACK_TEMPLATES)
        else:
            templates = _EVIDENCE_TEMPLATES.get(etype, _FALLBACK_TEMPLATES)

        parts.append(_format_template(_pick_template(templates, candidate), context))
    else:
        parts.append(_format_template(_pick_template(_FALLBACK_TEMPLATES, candidate), context))

    # Add dimensional flavor if available
    dim_desc = _describe_top_dimensions(candidate)
    if dim_desc:
        parts.append(f"Leans {dim_desc}.")

    # Add mode context for non-default modes
    if mode != "flow" and mode in _MODE_CONTEXT:
        parts.append(_MODE_CONTEXT[mode])

    # Add band context for non-default bands
    if novelty_band == "chaos":
        parts.append(_BAND_CONTEXT["chaos"])
    elif novelty_band == "safe":
        parts.append(_BAND_CONTEXT["safe"])

    return " ".join(parts)


def generate_explanation_chips(
    candidate: dict[str, Any],
    *,
    seed_track: dict[str, Any] | None = None,
    mode: str = "flow",
    novelty_band: str = "stretch",
) -> list[dict[str, str]]:
    """Generate compact explanation chips for UI display.

    Returns a list of chips, each with ``label`` and ``kind`` keys.
    Kinds: ``provider``, ``reason``, ``dimension``, ``confidence``,
    ``novelty``, ``feedback``, ``mode``.

    Args:
        candidate: Merged broker candidate dict.
        seed_track: The seed track dict, if available.
        mode: Broker mode.
        novelty_band: Novelty band.

    Returns:
        List of chip dicts.
    """
    chips: list[dict[str, str]] = []
    evidence_items: list[dict[str, Any]] = candidate.get("evidence") or []
    provider_signals: list[dict[str, Any]] = candidate.get("provider_signals") or []
    confidence = float(candidate.get("confidence") or 0)

    # Provider chips
    seen_providers: set[str] = set()
    for signal in provider_signals:
        provider = str(signal.get("provider") or "").strip()
        if provider and provider not in seen_providers:
            seen_providers.add(provider)
            chips.append({"label": provider, "kind": "provider"})

    if not seen_providers:
        for ev in evidence_items:
            src = str(ev.get("source") or "").strip()
            if src and src not in seen_providers:
                seen_providers.add(src)
                chips.append({"label": src, "kind": "provider"})

    # Evidence-type reason chip
    if evidence_items:
        strongest = max(evidence_items, key=lambda e: float(e.get("weight") or 0))
        etype = str(strongest.get("type") or "")
        reason_labels: dict[str, str] = {
            "embedding_neighbor": "similar texture",
            "similar_track": "similar track",
            "community_popularity": "community pick",
            "scout_bridge": "genre bridge",
            "community_weather": "trending",
            "feedback_history": "from feedback",
            "low_play_discovery": "hidden gem",
        }
        label = reason_labels.get(etype)
        if label:
            chips.append({"label": label, "kind": "reason"})

    # Dimension chip
    dim_desc = _describe_top_dimensions(candidate, limit=1)
    if dim_desc:
        chips.append({"label": dim_desc, "kind": "dimension"})

    # Confidence chip
    if confidence > 0:
        if confidence >= 0.7:
            chips.append({"label": "high confidence", "kind": "confidence"})
        elif confidence >= 0.4:
            chips.append({"label": "moderate confidence", "kind": "confidence"})
        else:
            chips.append({"label": "exploratory", "kind": "confidence"})

    # Novelty chip
    if novelty_band != "stretch":
        chips.append({"label": novelty_band, "kind": "novelty"})

    # Mode chip for non-default
    if mode != "flow":
        chips.append({"label": mode, "kind": "mode"})

    # Feedback chip
    feedback_bias = float(candidate.get("feedback_bias") or 0)
    if feedback_bias > 0.05:
        chips.append({"label": "reinforced", "kind": "feedback"})
    elif feedback_bias < -0.05:
        chips.append({"label": "dampened", "kind": "feedback"})

    return chips


def generate_why_now(
    candidate: dict[str, Any],
    *,
    seed_track: dict[str, Any] | None = None,
    mode: str = "flow",
    queue_context: dict[str, Any] | None = None,
) -> str:
    """Generate a "why now" explanation for sequencing context.

    Answers: why does this track belong at this point in the listening session?

    Args:
        candidate: The recommendation candidate.
        seed_track: Current seed track.
        mode: Broker mode.
        queue_context: Optional queue state info (length, origin, position).

    Returns:
        A concise "why now" string.
    """
    seed_artist = str((seed_track or {}).get("artist", "")).strip()
    evidence_items: list[dict[str, Any]] = candidate.get("evidence") or []

    if mode == "chaos":
        return "Deliberate pivot — breaking the pattern intentionally."

    if mode == "discovery":
        return "Discovery window — surfacing something you haven't explored."

    # Flow mode — build from context
    parts: list[str] = []

    if seed_artist:
        candidate_artist = str(candidate.get("artist") or "").strip()
        if candidate_artist.lower() == seed_artist.lower():
            parts.append(f"Continuing with {seed_artist}.")
        else:
            parts.append(f"Natural transition from {seed_artist}.")

    # Check for energy/dimension continuity
    for ev in evidence_items:
        if str(ev.get("type", "")) == "embedding_neighbor":
            parts.append("Texture stays close to the current thread.")
            break

    if not parts:
        parts.append("Fits the current listening direction.")

    queue_info = queue_context or {}
    queue_len = int(queue_info.get("length", 0))
    if queue_len > 10:
        parts.append(f"Keeping momentum across a {queue_len}-track session.")

    return " ".join(parts)


def generate_what_next(
    recommendations: list[dict[str, Any]],
    *,
    current_index: int = 0,
    mode: str = "flow",
) -> list[dict[str, str]]:
    """Generate "what next" summaries for upcoming recommendations.

    Returns a list of dicts with ``track_id``, ``artist``, ``title``,
    and ``hint`` keys describing what comes next and why.

    Args:
        recommendations: The full recommendation list.
        current_index: Current position in the list.
        mode: Broker mode.

    Returns:
        List of what-next hint dicts.
    """
    hints: list[dict[str, str]] = []
    remaining = recommendations[current_index + 1: current_index + 4]

    for i, rec in enumerate(remaining):
        artist = str(rec.get("artist") or "").strip()
        title = str(rec.get("title") or "").strip()
        track_id = str(rec.get("track_id") or "").strip()

        evidence = rec.get("evidence") or []
        if evidence:
            strongest = max(evidence, key=lambda e: float(e.get("weight") or 0))
            etype = str(strongest.get("type") or "")
        else:
            etype = ""

        if i == 0:
            position = "Up next"
        elif i == 1:
            position = "Then"
        else:
            position = "After that"

        hint_parts = [position + ":"]

        if etype == "embedding_neighbor":
            hint_parts.append("stays in the same neighborhood.")
        elif etype == "similar_track":
            hint_parts.append("connected through listener overlap.")
        elif etype == "scout_bridge":
            hint_parts.append("crosses into adjacent territory.")
        elif etype == "community_popularity":
            hint_parts.append("community-backed pick.")
        elif etype == "low_play_discovery":
            hint_parts.append("a deep cut waiting to surface.")
        else:
            hint_parts.append("Lyra Core pick.")

        hints.append({
            "track_id": track_id,
            "artist": artist,
            "title": title,
            "hint": " ".join(hint_parts),
        })

    return hints


def generate_feedback_effect_description(
    feedback_type: str,
    *,
    track_artist: str = "",
    track_title: str = "",
) -> str:
    """Generate a human-readable description of a feedback action's effect.

    Args:
        feedback_type: The feedback type string.
        track_artist: Artist of the affected track.
        track_title: Title of the affected track.

    Returns:
        A concise description of the effect.
    """
    track_label = f"{track_artist} — {track_title}" if track_artist and track_title else "this track"

    effects: dict[str, str] = {
        "accepted": f"Reinforcing direction toward {track_label}.",
        "queued": f"Noted interest in {track_label} for future recommendations.",
        "skipped": f"Reducing weight on tracks like {track_label}.",
        "replayed": f"Strengthening affinity for {track_label} and similar material.",
        "acquire_requested": f"Marked {track_label} as wanted — acquisition radar updated.",
        "keep": f"Leaning further into this direction.",
        "play": f"Rewarding this path — more like {track_label} ahead.",
        "dismiss": f"Pulling back from this direction.",
    }

    return effects.get(feedback_type, f"Feedback noted for {track_label}.")


def get_recent_feedback_effects(
    *,
    limit: int = 5,
    lookback_seconds: int = 3600,
) -> list[dict[str, Any]]:
    """Return recent feedback events with human-readable effect descriptions.

    Args:
        limit: Max events to return.
        lookback_seconds: How far back to look.

    Returns:
        List of feedback effect dicts with ``feedback_type``, ``artist``,
        ``title``, ``effect``, and ``created_at`` keys.
    """
    conn = get_connection(timeout=5.0)
    try:
        cursor = conn.cursor()
        # Check if the table exists before querying
        table_check = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recommendation_feedback'"
        ).fetchone()
        if not table_check:
            return []

        cutoff = time.time() - lookback_seconds
        rows = cursor.execute(
            """
            SELECT feedback_type, artist, title, track_id, created_at
            FROM recommendation_feedback
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()

    effects: list[dict[str, Any]] = []
    for row in rows:
        feedback_type = str(row[0] or "")
        artist = str(row[1] or "")
        title = str(row[2] or "")
        track_id = str(row[3] or "")
        created_at = float(row[4] or 0)

        effects.append({
            "feedback_type": feedback_type,
            "artist": artist,
            "title": title,
            "track_id": track_id,
            "effect": generate_feedback_effect_description(
                feedback_type, track_artist=artist, track_title=title,
            ),
            "created_at": created_at,
        })

    return effects


def summarize_feedback_direction(
    *,
    lookback_seconds: int = 7200,
) -> dict[str, Any]:
    """Summarize the overall feedback direction from recent history.

    Returns a dict with ``direction``, ``summary``, and ``signal_count`` keys.
    The direction is a short phrase like "darker / calmer / more familiar".

    Args:
        lookback_seconds: How far back to look for feedback.

    Returns:
        Direction summary dict.
    """
    conn = get_connection(timeout=5.0)
    try:
        cursor = conn.cursor()
        table_check = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recommendation_feedback'"
        ).fetchone()
        if not table_check:
            return {"direction": "", "summary": "No feedback recorded yet.", "signal_count": 0}

        cutoff = time.time() - lookback_seconds
        rows = cursor.execute(
            """
            SELECT rf.feedback_type, rf.track_id, t.energy, t.valence, t.tension,
                   t.density, t.warmth, t.movement
            FROM recommendation_feedback rf
            LEFT JOIN tracks t ON rf.track_id = t.track_id
            WHERE rf.created_at >= ?
            ORDER BY rf.created_at DESC
            LIMIT 50
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"direction": "", "summary": "No recent feedback to summarize.", "signal_count": 0}

    # Weight map for feedback types
    type_weights: dict[str, float] = {
        "accepted": 1.0, "queued": 0.7, "replayed": 1.2,
        "keep": 1.0, "play": 1.1,
        "skipped": -0.8, "dismiss": -1.0,
    }

    dim_totals: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    signal_count = 0

    for row in rows:
        fb_type = str(row[0] or "")
        weight = type_weights.get(fb_type, 0.0)
        if weight == 0.0:
            continue

        signal_count += 1
        dims = {
            "energy": row[2], "valence": row[3], "tension": row[4],
            "density": row[5], "warmth": row[6], "movement": row[7],
        }

        for dim_name, val in dims.items():
            if isinstance(val, (int, float)):
                dim_totals[dim_name] = dim_totals.get(dim_name, 0.0) + float(val) * weight
                dim_counts[dim_name] = dim_counts.get(dim_name, 0) + 1

    if not dim_totals:
        return {
            "direction": "",
            "summary": f"{signal_count} feedback signals, but no dimensional data to summarize.",
            "signal_count": signal_count,
        }

    # Compute average weighted direction per dimension
    dim_avg: dict[str, float] = {}
    for dim_name in dim_totals:
        count = dim_counts.get(dim_name, 1)
        dim_avg[dim_name] = dim_totals[dim_name] / max(count, 1)

    # Pick the strongest 2-3 directional signals
    sorted_dims = sorted(dim_avg.items(), key=lambda d: abs(d[1]), reverse=True)
    direction_parts: list[str] = []

    for dim_name, avg_val in sorted_dims[:3]:
        if abs(avg_val) < 0.1:
            continue
        if avg_val > 0:
            direction_parts.append(_DIM_HIGH.get(dim_name, dim_name))
        else:
            direction_parts.append(_DIM_LOW.get(dim_name, dim_name))

    direction = " / ".join(direction_parts) if direction_parts else "neutral drift"

    return {
        "direction": direction,
        "summary": f"Shifting toward {direction} based on {signal_count} recent signals.",
        "signal_count": signal_count,
    }

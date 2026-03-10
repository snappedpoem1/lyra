"""Arc sequencing engine.

Priority 4A: Turn a pool of scored tracks into an ordered journey.

v1 algorithm:
- For each arc position, pick the best-fitting unused track by minimizing distance
  to the arc template trajectory (dimensions defined by that template).
- Score transitions with a simple BPM proximity metric when BPM is known.

This module is intentionally self-contained and does not depend on Playlust.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


ARC_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "slow_burn": {
        "energy": [0.2, 0.3, 0.5, 0.7, 0.8, 0.7, 0.5, 0.3],
        "tension": [0.2, 0.3, 0.4, 0.6, 0.7, 0.5, 0.3, 0.2],
        "labels": ["intro", "warmup", "build", "build", "peak", "sustain", "cool", "resolve"],
    },
    "catharsis": {
        "energy": [0.2, 0.3, 0.5, 0.7, 0.95, 0.6, 0.3, 0.15],
        "tension": [0.4, 0.5, 0.6, 0.8, 0.9, 0.4, 0.2, 0.1],
        "labels": ["tension", "build", "climb", "climb", "peak", "aftermath", "cool", "peace"],
    },
    "party_wave": {
        "energy": [0.5, 0.7, 0.85, 0.8, 0.6, 0.8, 0.9, 0.7, 0.5],
        "labels": ["opener", "build", "peak1", "groove", "shift", "build2", "peak2", "cool", "close"],
    },
    "night_drive": {
        "energy": [0.3, 0.4, 0.5, 0.5, 0.6, 0.5, 0.4, 0.3, 0.2],
        "movement": [0.5, 0.6, 0.6, 0.7, 0.7, 0.6, 0.5, 0.4, 0.3],
        "space": [0.6, 0.7, 0.7, 0.8, 0.8, 0.8, 0.7, 0.7, 0.8],
        "labels": ["depart", "highway", "cruise", "cruise", "crest", "descend", "coast", "approach", "arrive"],
    },
    "morning_light": {
        "energy": [0.1, 0.2, 0.35, 0.5, 0.6, 0.65, 0.6, 0.55],
        "valence": [0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.75, 0.7],
        "warmth": [0.7, 0.7, 0.7, 0.6, 0.6, 0.5, 0.5, 0.6],
        "labels": ["wake", "stretch", "coffee", "step_out", "stride", "cruise", "maintain", "arrive"],
    },
    "heartbreak": {
        "energy": [0.6, 0.7, 0.5, 0.3, 0.2, 0.15, 0.2, 0.3, 0.4],
        "valence": [0.2, 0.15, 0.1, 0.15, 0.2, 0.25, 0.35, 0.45, 0.55],
        "tension": [0.7, 0.8, 0.6, 0.5, 0.4, 0.3, 0.2, 0.2, 0.15],
        "labels": ["anger", "rage", "crash", "numb", "grief", "bottom", "acceptance", "light", "hope"],
    },
    "focus_tunnel": {
        "energy": [0.4, 0.45, 0.45, 0.5, 0.5, 0.45, 0.45, 0.4],
        "movement": [0.5, 0.55, 0.55, 0.55, 0.55, 0.5, 0.5, 0.45],
        "density": [0.3, 0.35, 0.4, 0.4, 0.4, 0.35, 0.35, 0.3],
        "labels": ["settle", "engage", "flow", "deep", "deep", "coast", "ease", "surface"],
    },
    "celebration": {
        "energy": [0.7, 0.8, 0.85, 0.9, 0.75, 0.85, 0.95, 0.8, 0.6],
        "valence": [0.8, 0.85, 0.9, 0.9, 0.7, 0.8, 0.9, 0.85, 0.8],
        "labels": ["bang", "roll", "groove", "peak", "breather", "build", "encore", "cool", "warmth"],
    },
}


def list_arc_shapes() -> List[Dict[str, Any]]:
    return [{"id": k, "labels": v.get("labels", [])} for k, v in ARC_TEMPLATES.items()]


def _transition_score(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    bpm_score = 0.5
    bpm_a = a.get("bpm")
    bpm_b = b.get("bpm")
    if bpm_a is not None and bpm_b is not None:
        try:
            da = float(bpm_a)
            db = float(bpm_b)
            delta = abs(da - db)
            # 0 bpm diff -> 1.0; ~30 bpm diff -> ~0.22
            bpm_score = float(math.exp(-delta / 20.0))
        except Exception:
            bpm_score = 0.5

    energy_score = 0.5
    sa = (a.get("scores") or {}).get("energy")
    sb = (b.get("scores") or {}).get("energy")
    if sa is not None and sb is not None:
        try:
            delta_e = abs(float(sa) - float(sb))
            energy_score = max(0.0, 1.0 - delta_e)
        except Exception:
            energy_score = 0.5

    return round((0.7 * bpm_score) + (0.3 * energy_score), 6)


def _avg_transition_score(items: List[Dict[str, Any]]) -> float:
    if len(items) < 2:
        return 0.0
    scores = [_transition_score(items[i - 1], items[i]) for i in range(1, len(items))]
    return float(sum(scores) / len(scores)) if scores else 0.0


def _optimize_order_by_transitions(items: List[Dict[str, Any]], passes: int = 2) -> List[Dict[str, Any]]:
    """Greedy adjacent-swap optimizer to improve transition smoothness.

    Keeps arc labels/order positions fixed while swapping candidate tracks.
    """
    if len(items) < 3:
        return items

    ordered = list(items)
    for _ in range(max(1, passes)):
        improved = False
        i = 1
        while i < len(ordered) - 1:
            baseline = _avg_transition_score(ordered)
            trial = list(ordered)
            trial[i], trial[i + 1] = trial[i + 1], trial[i]
            trial_score = _avg_transition_score(trial)
            if trial_score > baseline:
                ordered = trial
                improved = True
                i += 2
            else:
                i += 1
        if not improved:
            break

    for idx, item in enumerate(ordered):
        item["arc_index"] = idx
    return ordered


def _position_targets(template: Dict[str, Any], position: int, positions: int) -> Dict[str, float]:
    targets: Dict[str, float] = {}
    denom = max(positions - 1, 1)
    t = position / denom

    for dim, traj in template.items():
        if dim == "labels":
            continue
        if not isinstance(traj, list) or len(traj) == 0:
            continue
        idx = int(round(t * (len(traj) - 1)))
        targets[dim] = float(traj[idx])

    return targets


def _fit_distance(track: Dict[str, Any], targets: Dict[str, float]) -> Optional[float]:
    scores = track.get("scores")
    if not isinstance(scores, dict) or not scores:
        return None

    dist = 0.0
    used = 0
    for dim, target in targets.items():
        val = scores.get(dim)
        if val is None:
            continue
        used += 1
        dist += abs(float(val) - float(target))

    if used == 0:
        return None

    return dist / used


def _enrich_with_genius(journey: List[Dict[str, Any]]) -> None:
    """Attach cached Genius context to journey tracks (in-place).

    Reads from enrich_cache to add release_date, description snippet,
    and annotation_count to each track dict under a ``genius`` key.
    This enriches arc narration with song context without extra API calls.
    """
    try:
        import json as _json
        from oracle.db.schema import get_connection

        track_ids = [t.get("track_id") for t in journey if t.get("track_id")]
        if not track_ids:
            return

        conn = get_connection(timeout=5.0)
        cursor = conn.cursor()

        placeholders = ",".join("?" for _ in track_ids)
        cursor.execute(
            f"SELECT lookup_key, payload_json FROM enrich_cache "
            f"WHERE provider = 'genius' AND lookup_key IN ({placeholders})",
            [f"genius:{tid}" for tid in track_ids],
        )

        cache_map: Dict[str, Dict[str, Any]] = {}
        for lookup_key, payload_json in cursor.fetchall():
            try:
                payload = _json.loads(payload_json)
                # Extract the track_id from "genius:<track_id>"
                tid = lookup_key.split(":", 1)[1] if ":" in lookup_key else lookup_key
                cache_map[tid] = payload
            except Exception:
                continue

        conn.close()

        for track in journey:
            tid = track.get("track_id", "")
            cached = cache_map.get(tid)
            if not cached:
                continue
            track["genius"] = {
                "release_date": cached.get("release_date"),
                "description": (cached.get("description") or "")[:200] or None,
                "annotation_count": cached.get("annotation_count"),
                "url": cached.get("url"),
            }
    except Exception:
        pass  # Genius enrichment is best-effort


def sequence_tracks(
    tracks: List[Dict[str, Any]],
    arc_id: str,
    *,
    count: Optional[int] = None,
    enrich_genius: bool = True,
) -> Dict[str, Any]:
    """Sequence tracks into an arc.

    Args:
        tracks: Candidate tracks. Each may include `scores` and `bpm`.
        arc_id: Template ID.
        count: Desired output length.
        enrich_genius: Attach cached Genius context to journey tracks.

    Returns:
        {arc, journey, transition_avg, used_scores}
    """
    if not tracks:
        return {"arc": arc_id, "journey": [], "transition_avg": 0.0, "used_scores": False}

    arc_id = (arc_id or "slow_burn").strip().lower()
    template = ARC_TEMPLATES.get(arc_id) or ARC_TEMPLATES["slow_burn"]

    out_len = count if count is not None else len(tracks)
    out_len = max(1, min(int(out_len), len(tracks)))

    used: set[str] = set()
    ordered: List[Dict[str, Any]] = []
    used_scores = False

    for pos in range(out_len):
        targets = _position_targets(template, pos, out_len)

        best_idx = None
        best_dist = None

        for idx, track in enumerate(tracks):
            tid = str(track.get("track_id") or "")
            if not tid or tid in used:
                continue

            dist = _fit_distance(track, targets)
            if dist is None:
                continue

            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_idx = idx

        if best_idx is None:
            # Fallback: semantic order (input order) for remaining items.
            for track in tracks:
                tid = str(track.get("track_id") or "")
                if tid and tid not in used:
                    best_idx = tracks.index(track)
                    break

        if best_idx is None:
            break

        chosen = dict(tracks[best_idx])
        tid = str(chosen.get("track_id") or "")
        if tid:
            used.add(tid)

        labels = template.get("labels") or []
        denom = max(out_len - 1, 1)
        t = pos / denom
        label_idx = int(round(t * (len(labels) - 1))) if labels else 0
        chosen["arc_index"] = pos
        chosen["arc_label"] = labels[label_idx] if labels else ""

        if chosen.get("scores"):
            used_scores = True

        ordered.append(chosen)

    # Transition optimization pass
    ordered = _optimize_order_by_transitions(ordered, passes=2)

    # Transition scores
    transitions: List[float] = []
    for i in range(1, len(ordered)):
        transitions.append(_transition_score(ordered[i - 1], ordered[i]))

    transition_avg = sum(transitions) / len(transitions) if transitions else 0.0

    if enrich_genius and ordered:
        _enrich_with_genius(ordered)

    return {
        "arc": arc_id,
        "journey": ordered,
        "transition_avg": round(float(transition_avg), 4),
        "used_scores": used_scores,
    }

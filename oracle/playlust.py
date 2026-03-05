"""
Playlust — 4-Act Emotional Arc Generator

The HALFCOCKED.EXE methodology automated.

Constructs a playlist that follows a deliberate four-act emotional journey:

    Act I   — Aggressive  (0–25%)  : Maximum density, tension, rawness.
                                      Establishes dominance. Clears the room.
    Act II  — Seductive   (25–50%) : Warmth floods in. Energy stays but
                                      tension drops. The body starts moving.
    Act III — Breakdown   (50–75%) : Everything strips back. Space opens.
                                      Introspection, nostalgia, the abyss.
    Act IV  — Sublime     (75–100%): Rising from the breakdown. Complexity
                                      and valence climb together. Transcendence.

The algorithm queries the local library's dimensional scores (not streaming
services) so the output is always tracks you actually own. Deep cuts can be
preferentially surfaced in Acts II and IV.

Usage::

    pl = Playlust()
    run = pl.generate(
        mood="volcanic shoegaze fever dream",
        duration_minutes=60,
        name="Late Night Ritual",
        use_deepcut=True,
    )

Author: Lyra Oracle — Sprint 2, F-008
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from oracle.db.schema import get_connection
from oracle.types import PlaylistRun, PlaylistTrack, TrackReason

logger = logging.getLogger(__name__)

_DIMENSIONS = [
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness",
    "complexity", "nostalgia",
]

# Average track duration assumption for track-count calculations
_AVG_TRACK_SECONDS = 240  # 4 minutes

# ─── Act Definitions ───────────────────────────────────────────────────────────

@dataclass
class PlaylustAct:
    """One act of a Playlust journey."""

    name: str
    label: str
    target: Dict[str, float]
    arc_template: str        # arc.py template key
    narrative_tone: str      # used in LLM prompt / template
    proportion: float        # fraction of total playlist (0–1)

    # Resolved by Playlust.generate
    tracks: List[Dict] = field(default_factory=list)
    track_count_target: int = 0


# The four acts — dimensional targets encode the HALFCOCKED.EXE blueprint.
# Values are 0–1 on each dimension.
ACT_DEFINITIONS: List[PlaylustAct] = [
    PlaylustAct(
        name="aggressive",
        label="Act I — Aggressive",
        target={
            "energy":     0.88,
            "valence":    0.38,
            "tension":    0.82,
            "density":    0.78,
            "warmth":     0.28,
            "movement":   0.85,
            "space":      0.30,
            "rawness":    0.80,
            "complexity": 0.58,
            "nostalgia":  0.35,
        },
        arc_template="catharsis",
        narrative_tone="confrontational, visceral, urgent",
        proportion=0.25,
    ),
    PlaylustAct(
        name="seductive",
        label="Act II — Seductive",
        target={
            "energy":     0.58,
            "valence":    0.72,
            "tension":    0.28,
            "density":    0.52,
            "warmth":     0.82,
            "movement":   0.68,
            "space":      0.55,
            "rawness":    0.32,
            "complexity": 0.52,
            "nostalgia":  0.55,
        },
        arc_template="slow_burn",
        narrative_tone="seductive, hypnotic, inviting",
        proportion=0.25,
    ),
    PlaylustAct(
        name="breakdown",
        label="Act III — Breakdown",
        target={
            "energy":     0.22,
            "valence":    0.32,
            "tension":    0.62,
            "density":    0.28,
            "warmth":     0.38,
            "movement":   0.22,
            "space":      0.85,
            "rawness":    0.42,
            "complexity": 0.42,
            "nostalgia":  0.68,
        },
        arc_template="heartbreak",
        narrative_tone="introspective, desolate, cavernous",
        proportion=0.25,
    ),
    PlaylustAct(
        name="sublime",
        label="Act IV — Sublime",
        target={
            "energy":     0.72,
            "valence":    0.82,
            "tension":    0.22,
            "density":    0.62,
            "warmth":     0.72,
            "movement":   0.62,
            "space":      0.78,
            "rawness":    0.28,
            "complexity": 0.78,
            "nostalgia":  0.48,
        },
        arc_template="morning_light",
        narrative_tone="transcendent, euphoric, resolved",
        proportion=0.25,
    ),
]

# ─── Main Class ────────────────────────────────────────────────────────────────


class Playlust:
    """
    Automated HALFCOCKED.EXE — 4-act emotional arc generator.

    Pulls tracks from the local library scored in the 10-dimensional model,
    sequences them across four acts, and returns an annotated PlaylistRun.

    Args:
        candidate_pool_multiplier: How many candidates to pull per act slot
            before sequencing (higher = better fit, slower). Default: 5.
    """

    def __init__(self, candidate_pool_multiplier: int = 5) -> None:
        self._pool_mult = candidate_pool_multiplier

    def generate(
        self,
        mood: Optional[str] = None,
        duration_minutes: int = 60,
        name: Optional[str] = None,
        taste_context: Optional[Dict[str, float]] = None,
        use_deepcut: bool = True,
        deepcut_acts: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> PlaylistRun:
        """
        Generate a full 4-act Playlust journey.

        Args:
            mood: Optional mood string to bias candidate selection (used in
                  narrative generation). Does not affect scoring directly.
            duration_minutes: Total target duration in minutes.
            name: Optional playlist name. Auto-generated if not provided.
            taste_context: Optional taste profile dict (10 dimensions, 0–1).
                           When provided, candidate selection is biased toward
                           tracks aligned with the user's taste within each act.
            use_deepcut: If True, surface deep cut candidates in Acts II and IV
                         (requires enrich_cache data from the DeepCut engine).
            deepcut_acts: Which acts to inject deep cuts into.
                          Defaults to ``["seductive", "sublime"]``.
            progress_callback: Optional callable(msg: str) for progress reporting.

        Returns:
            A ``PlaylistRun`` object with all four acts sequenced, reasons
            assigned per track, and a narrative in the ``prompt`` field.
        """
        if deepcut_acts is None:
            deepcut_acts = ["seductive", "sublime"]

        total_tracks = max(4, round((duration_minutes * 60) / _AVG_TRACK_SECONDS))
        logger.info("Playlust: generating %d-track journey (~%d min)", total_tracks, duration_minutes)

        # Clone act definitions so we can mutate track_count_target
        import copy
        acts = copy.deepcopy(ACT_DEFINITIONS)
        _assign_track_counts(acts, total_tracks)

        # Translate natural language mood → per-act dimensional overrides.
        # Works with LM Studio / any OpenAI-compatible local model; falls back
        # to a deterministic keyword heuristic when no LLM is reachable.
        if mood:
            try:
                from oracle.mood_interpreter import interpret_mood
                mood_overrides = interpret_mood(mood)
                if mood_overrides:
                    acts = _apply_mood_overrides(acts, mood_overrides)
                    logger.info("Playlust: mood overrides applied for '%s'", mood)
            except Exception as _mood_exc:
                logger.debug("Playlust: mood interpretation skipped (%s)", _mood_exc)

        playlist_tracks: List[PlaylistTrack] = []
        all_used_paths: set = set()

        for act in acts:
            if progress_callback:
                progress_callback(f"[{act.label}] Selecting {act.track_count_target} tracks...")

            candidates = self._get_act_candidates(
                act=act,
                taste_context=taste_context,
                use_deepcut=(use_deepcut and act.name in deepcut_acts),
                exclude_paths=all_used_paths,
                pool_size=act.track_count_target * self._pool_mult,
            )

            if not candidates:
                logger.warning("Playlust: no candidates for act '%s' — acts may be short", act.name)
                continue

            sequenced = self._sequence_act(candidates, act)
            act.tracks = sequenced

            rank_offset = len(playlist_tracks) + 1
            for rank_in_act, track in enumerate(sequenced, start=1):
                global_rank = rank_offset + rank_in_act - 1
                reasons = self._build_act_reasons(track, act, rank_in_act, use_deepcut)
                pt = PlaylistTrack(
                    path=track.get("filepath", ""),
                    artist=track.get("artist", "Unknown"),
                    title=track.get("title", "Unknown"),
                    rank=global_rank,
                    global_score=track.get("fit_score", 0.5),
                    reasons=reasons,
                )
                playlist_tracks.append(pt)
                all_used_paths.add(track.get("filepath", ""))

        # Generate narrative
        narrative = self._generate_narrative(acts=acts, mood=mood, total_tracks=len(playlist_tracks))

        run_name = name or _auto_name(mood, duration_minutes)
        run = PlaylistRun(
            uuid=str(uuid.uuid4()),
            prompt=narrative,
            created_at=datetime.now(timezone.utc),
            tracks=playlist_tracks,
        )

        # Persist if writes are enabled
        try:
            from oracle.ops import get_write_mode
            from oracle.vibes import save_playlist_run
            if get_write_mode() == "apply_allowed":
                save_playlist_run(run, params={
                    "mood": mood or "",
                    "duration_minutes": duration_minutes,
                    "name": run_name,
                    "use_deepcut": use_deepcut,
                }, vibe_name=run_name)
                logger.info("Playlust: run saved (%d tracks)", len(playlist_tracks))
        except Exception as exc:
            logger.debug("Playlust: run not saved: %s", exc)

        return run

    # ─── Act Candidate Selection ────────────────────────────────────────────────

    def _get_act_candidates(
        self,
        act: PlaylustAct,
        taste_context: Optional[Dict[str, float]],
        use_deepcut: bool,
        exclude_paths: set,
        pool_size: int,
    ) -> List[Dict]:
        """
        Query track_scores for candidates that fit this act's dimensional target.

        Strategy:
        1. Pull the top `pool_size * 2` tracks by L1 distance to target.
        2. If taste_context is given, bias by blending target with taste (60/40).
        3. If use_deepcut, fetch deep cut candidates from enrich_cache and
           mix them in at 30% of the pool.
        4. Exclude any tracks already used in previous acts.

        Returns:
            List of track dicts with ``fit_score`` and ``scores`` dict added.
        """
        effective_target = dict(act.target)

        # Blend with taste context if provided (taste biases each act slightly)
        if taste_context:
            for dim in _DIMENSIONS:
                if dim in taste_context and taste_context[dim] is not None:
                    effective_target[dim] = (
                        0.65 * effective_target[dim] + 0.35 * float(taste_context[dim])
                    )

        base_candidates = self._query_by_target(
            target=effective_target,
            limit=pool_size * 3,
            exclude_paths=exclude_paths,
        )

        if not use_deepcut or not base_candidates:
            return base_candidates[:pool_size]

        # Mix in deep cut candidates
        deepcut_paths = self._get_deepcut_paths(limit=pool_size)
        dc_candidates = [c for c in base_candidates if c["filepath"] in deepcut_paths]
        non_dc = [c for c in base_candidates if c["filepath"] not in deepcut_paths]

        # 30% deep cuts, 70% dimensional fit
        dc_slots = max(1, pool_size // 3)
        non_dc_slots = pool_size - dc_slots

        mixed = dc_candidates[:dc_slots] + non_dc[:non_dc_slots]
        # Sort by fit_score so best quality candidates bubble up
        mixed.sort(key=lambda x: x.get("fit_score", 0), reverse=True)
        return mixed[:pool_size]

    def _query_by_target(
        self,
        target: Dict[str, float],
        limit: int,
        exclude_paths: set,
    ) -> List[Dict]:
        """
        Pull tracks from track_scores ordered by L1 distance to target profile.

        Returns list of dicts with keys:
            track_id, filepath, artist, title, album, genre, fit_score, scores
        """
        conn = get_connection()
        c = conn.cursor()

        # Build SQL expression for L1 distance across all 10 dimensions
        dim_terms = " + ".join(
            f"ABS(COALESCE(ts.{dim}, 0.5) - {target.get(dim, 0.5):.4f})"
            for dim in _DIMENSIONS
        )

        c.execute(
            f"""SELECT t.track_id, t.filepath, t.artist, t.title, t.album, t.genre,
                       ({dim_terms}) / 10.0 AS l1_dist,
                       ts.energy, ts.valence, ts.tension, ts.density,
                       ts.warmth, ts.movement, ts.space, ts.rawness,
                       ts.complexity, ts.nostalgia
                FROM track_scores ts
                JOIN tracks t ON ts.track_id = t.track_id
                ORDER BY l1_dist ASC
                LIMIT {limit * 2}""",
        )
        rows = c.fetchall()
        conn.close()

        results = []
        for row in rows:
            (track_id, filepath, artist, title, album, genre,
             l1_dist, *dim_vals) = row

            if filepath in exclude_paths:
                continue

            fit_score = round(max(0.0, 1.0 - l1_dist), 4)
            results.append({
                "track_id": track_id or "",
                "filepath": filepath or "",
                "artist": artist or "Unknown",
                "title": title or "Unknown",
                "album": album or "",
                "genre": genre or "",
                "fit_score": fit_score,
                "scores": dict(zip(_DIMENSIONS, [float(v) if v is not None else 0.5 for v in dim_vals])),
            })

        return results[:limit]

    def _get_deepcut_paths(self, limit: int = 50) -> set:
        """Return a set of filepaths for tracks with cached deep cut scores > 0.7."""
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("PRAGMA table_info(enrich_cache)")
            cols = {row[1] for row in c.fetchall()}
            payload_col = "payload_json" if "payload_json" in cols else "payload"
            c.execute(
                f"SELECT {payload_col} FROM enrich_cache WHERE provider = 'deepcut_score' LIMIT 1000"
            )
            rows = c.fetchall()
        finally:
            conn.close()

        paths: set = set()
        for row in rows:
            try:
                payload = json.loads(row[0])
                if float(payload.get("obscurity_score", 0)) >= 0.7:
                    fp = payload.get("filepath", "")
                    if fp:
                        paths.add(fp)
                    if len(paths) >= limit:
                        break
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return paths

    # ─── Sequencing ────────────────────────────────────────────────────────────

    def _sequence_act(self, candidates: List[Dict], act: PlaylustAct) -> List[Dict]:
        """
        Sequence candidates within an act using oracle.arc.sequence_tracks.

        Adapts the track dict format to what arc.py expects
        (``track_id``, ``scores``, optional ``bpm``).

        Returns:
            Ordered list of track dicts, trimmed to act.track_count_target.
        """
        from oracle.arc import sequence_tracks

        arc_candidates = [
            {
                "track_id": t["track_id"],
                "filepath": t["filepath"],
                "artist": t["artist"],
                "title": t["title"],
                "album": t["album"],
                "genre": t["genre"],
                "fit_score": t["fit_score"],
                "scores": t.get("scores", {}),
            }
            for t in candidates
        ]

        result = sequence_tracks(
            tracks=arc_candidates,
            arc_id=act.arc_template,
            count=act.track_count_target,
            enrich_genius=False,  # speed — Playlust doesn't need genius metadata
        )

        ordered = result.get("journey", [])

        # Re-merge fit_score and any original filepath data
        filepath_map = {t["track_id"]: t for t in candidates}
        for track in ordered:
            original = filepath_map.get(track.get("track_id", ""), {})
            track.setdefault("filepath", original.get("filepath", ""))
            track.setdefault("fit_score", original.get("fit_score", 0.5))

        return ordered

    # ─── Reason Building ───────────────────────────────────────────────────────

    def _build_act_reasons(
        self, track: Dict, act: PlaylustAct, rank_in_act: int, with_deepcut: bool
    ) -> List[TrackReason]:
        """Build reasons for a single track within its act."""
        reasons: List[TrackReason] = []

        # Primary reason: act membership
        reasons.append(TrackReason(
            type=f"act:{act.name}",
            score=round(track.get("fit_score", 0.5), 3),
            text=f"{act.label} — {act.narrative_tone.split(',')[0].strip()}",
        ))

        # Dimensional fit reason
        scores = track.get("scores", {})
        target = act.target
        if scores and target:
            best_dim, best_fit = _best_dimension_fit(scores, target)
            if best_dim and best_fit > 0.85:
                reasons.append(TrackReason(
                    type=f"similar-{best_dim}",
                    score=round(best_fit, 3),
                    text=f"Strong {best_dim} match for this act ({scores.get(best_dim, 0):.2f})",
                ))

        # Deep cut reason — check enrich_cache
        try:
            from oracle.enrichers.cache import make_lookup_key, get_cached_payload
            cache_key = make_lookup_key("deepcut_score", track.get("artist", ""), track.get("title", ""))
            dc_payload = get_cached_payload("deepcut_score", cache_key, max_age_seconds=86400 * 7)
            if dc_payload and not dc_payload.get("_miss"):
                os_score = float(dc_payload.get("obscurity_score", 0))
                if os_score >= 0.7:
                    tier = "holy grail" if os_score >= 1.5 else "hidden gem" if os_score >= 1.0 else "deep cut"
                    reasons.append(TrackReason(
                        type="deep-cut",
                        score=round(min(1.0, os_score / 2), 3),
                        text=f"Acclaimed {tier} surfaced for this act",
                    ))
        except Exception:
            pass

        # Arc position reason
        arc_label = track.get("arc_label", "")
        if arc_label:
            reasons.append(TrackReason(
                type="arc-position",
                score=0.7,
                text=f"Arc position: {arc_label} within {act.name}",
            ))

        return reasons

    # ─── Narrative Generation ──────────────────────────────────────────────────

    def _generate_narrative(
        self, acts: List[PlaylustAct], mood: Optional[str], total_tracks: int
    ) -> str:
        """
        Generate a prose narrative for the playlist journey.

        Attempts LLM generation first; falls back to a template if unavailable.

        Args:
            acts: The four act definitions with their resolved tracks.
            mood: Optional mood seed string.
            total_tracks: Total track count across all acts.

        Returns:
            A narrative string suitable for the PlaylistRun.prompt field.
        """
        try:
            narrative = self._llm_narrative(acts=acts, mood=mood, total_tracks=total_tracks)
            if narrative:
                return narrative
        except Exception as exc:
            logger.debug("Playlust: LLM narrative failed (%s) — using template", exc)

        return self._template_narrative(acts=acts, mood=mood, total_tracks=total_tracks)

    def _llm_narrative(
        self, acts: List[PlaylustAct], mood: Optional[str], total_tracks: int
    ) -> Optional[str]:
        """Attempt narrative generation via the configured LLM provider."""
        try:
            from oracle.llm import generate_text
        except ImportError:
            return None

        mood_line = f'The mood seed is: "{mood}".' if mood else "No specific mood was given."

        track_lines = []
        for act in acts:
            if act.tracks:
                sample = act.tracks[:2]
                names = " / ".join(
                    f"{t.get('artist', '?')} - {t.get('title', '?')}" for t in sample
                )
                track_lines.append(f"  {act.label}: opens with {names} ...")

        tracks_preview = "\n".join(track_lines) if track_lines else "  (no tracks resolved)"

        prompt = f"""You are writing liner notes for a carefully constructed electronic music playlist.

The playlist has four acts:
  - Act I (Aggressive): confrontational, high-tension, maximum density
  - Act II (Seductive): warmth floods in, tension dissolves, hypnotic groove
  - Act III (Breakdown): everything strips back, vast space, introspection
  - Act IV (Sublime): transcendent return, euphoric complexity, resolution

{mood_line}
Total tracks: {total_tracks}

Opening acts:
{tracks_preview}

Write 3–4 sentences of evocative liner notes for this playlist. 
Be literary but not pretentious. Avoid clichés. No bullet points. 
First sentence should establish the journey. Last sentence should hint at catharsis.
"""

        try:
            text = generate_text(prompt, max_tokens=200, temperature=0.85)
            if text and len(text.strip()) > 30:
                return text.strip()
        except Exception as exc:
            logger.debug("Playlust LLM call failed: %s", exc)
        return None

    def _template_narrative(
        self, acts: List[PlaylustAct], mood: Optional[str], total_tracks: int
    ) -> str:
        """Template-based narrative fallback."""
        mood_clause = f' seeded from "{mood}"' if mood else ""
        act_summaries = []
        for act in acts:
            count = len(act.tracks)
            if count > 0:
                act_summaries.append(f"{act.label} ({count} tracks, {act.narrative_tone.split(',')[0].strip()})")

        acts_text = "; ".join(act_summaries) if act_summaries else "four acts"
        return (
            f"A {total_tracks}-track Playlust journey{mood_clause}: {acts_text}. "
            f"Built from your local library using the HALFCOCKED.EXE methodology — "
            f"aggressive confrontation giving way to seduction, descent, and final transcendence."
        )

    def get_act_definitions(self) -> List[Dict]:
        """Return the act configuration as a list of serialisable dicts."""
        return [
            {
                "name": act.name,
                "label": act.label,
                "target_profile": act.target,
                "arc_template": act.arc_template,
                "narrative_tone": act.narrative_tone,
                "proportion": act.proportion,
            }
            for act in ACT_DEFINITIONS
        ]


# ─── Module Helpers ────────────────────────────────────────────────────────────

def _assign_track_counts(acts: List[PlaylustAct], total: int) -> None:
    """Distribute total track count across acts according to their proportions."""
    assigned = 0
    for act in acts[:-1]:
        act.track_count_target = max(1, round(act.proportion * total))
        assigned += act.track_count_target
    acts[-1].track_count_target = max(1, total - assigned)


def _apply_mood_overrides(
    acts: List[PlaylustAct],
    overrides: Dict[str, Dict[str, float]],
    blend: float = 0.65,
) -> List[PlaylustAct]:
    """Blend LLM/keyword mood overrides into each act's dimensional target.

    Args:
        acts: Deep-copied ACT_DEFINITIONS (mutable).
        overrides: {act_name: {dim: float}} from interpret_mood().
        blend: Weight given to the override vs. the fixed act target.
               0.0 = ignore overrides, 1.0 = use overrides exclusively.

    Returns:
        The same acts list, with targets mutated in-place.
    """
    for act in acts:
        act_override = overrides.get(act.name)
        if not act_override:
            continue
        for dim in _DIMENSIONS:
            if dim in act_override:
                act.target[dim] = round(
                    blend * float(act_override[dim])
                    + (1.0 - blend) * act.target.get(dim, 0.5),
                    4,
                )
    return acts


def _best_dimension_fit(
    scores: Dict[str, float], target: Dict[str, float]
) -> Tuple[Optional[str], float]:
    """Return the dimension and fit score (0–1) where track most closely matches target."""
    best_dim: Optional[str] = None
    best_fit = 0.0
    for dim in _DIMENSIONS:
        if dim in scores and dim in target:
            dist = abs(float(scores[dim]) - float(target[dim]))
            fit = 1.0 - dist
            if fit > best_fit:
                best_fit = fit
                best_dim = dim
    return best_dim, best_fit


def _auto_name(mood: Optional[str], duration_minutes: int) -> str:
    """Generate a playlist name from mood and duration."""
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%Y-%m-%d")
    if mood:
        words = mood.split()[:3]
        mood_slug = "_".join(w.lower() for w in words)
        return f"playlust_{mood_slug}_{ts}"
    return f"playlust_{duration_minutes}min_{ts}"

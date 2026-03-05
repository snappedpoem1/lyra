"""MoodInterpreter — translates natural language mood into per-act dimensional targets.

The user can describe a playlist with any kind of language:

    "party in a car crash that ends in a dream"
    "haunted carnival at 3am"
    "post-apocalyptic euphoria"
    "first warm day after a brutal winter"

LM Studio / any OpenAI-compatible local model is the primary route.  The LLM
interprets the narrative arc and returns dimensional targets for each of the
four Playlust acts directly.

A deterministic keyword fallback ensures the feature works even when no LLM
is configured or reachable.

Usage::

    from oracle.mood_interpreter import interpret_mood

    overrides = interpret_mood("party in a car crash that ends in a dream")
    # Returns:
    # {
    #   "aggressive": {"energy": 0.92, "valence": 0.80, "tension": 0.55, ...},
    #   "seductive":  {"energy": 0.75, "tension": 0.78, "rawness": 0.70, ...},
    #   "breakdown":  {"space": 0.90, "energy": 0.30, "nostalgia": 0.45, ...},
    #   "sublime":    {"space": 0.88, "complexity": 0.72, "valence": 0.60, ...},
    # }
    # Merge these into Playlust ACT_DEFINITIONS before candidate selection.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_DIMENSIONS = (
    "energy", "valence", "tension", "density",
    "warmth", "movement", "space", "rawness",
    "complexity", "nostalgia",
)

_ACT_NAMES = ("aggressive", "seductive", "breakdown", "sublime")

# ---------------------------------------------------------------------------
# Keyword → dimension heuristic table
# Each token maps to per-dimension deltas applied to all acts, then
# per-act weights shape which acts the delta lands on most strongly.
# ---------------------------------------------------------------------------

_KEYWORD_DIM_BOOSTS: Dict[str, Dict[str, float]] = {
    # energy + chaos
    "party":        {"energy": 0.20, "valence": 0.18, "movement": 0.18, "density": 0.12},
    "crash":        {"tension": 0.25, "rawness": 0.22, "energy": 0.15, "valence": -0.15},
    "explosion":    {"energy": 0.25, "tension": 0.20, "rawness": 0.20, "density": 0.15},
    "riot":         {"energy": 0.22, "rawness": 0.20, "tension": 0.18, "valence": -0.10},
    "rage":         {"energy": 0.20, "rawness": 0.22, "tension": 0.20, "valence": -0.18},
    "chaos":        {"energy": 0.18, "tension": 0.20, "rawness": 0.18, "space": -0.10},
    "violence":     {"rawness": 0.22, "tension": 0.22, "energy": 0.18, "valence": -0.20},
    "war":          {"tension": 0.22, "rawness": 0.20, "energy": 0.18, "valence": -0.18},
    "fire":         {"energy": 0.20, "tension": 0.18, "rawness": 0.15},
    "breakdown":    {"tension": 0.15, "rawness": 0.12, "complexity": 0.10},
    "collapse":     {"tension": 0.18, "space": 0.12, "energy": -0.10, "valence": -0.15},
    # dream / ethereal
    "dream":        {"space": 0.22, "complexity": 0.15, "nostalgia": 0.12, "energy": -0.12, "density": -0.15},
    "ethereal":     {"space": 0.25, "complexity": 0.12, "tension": -0.10, "density": -0.18},
    "floating":     {"space": 0.20, "energy": -0.12, "movement": -0.10, "density": -0.12},
    "surreal":      {"space": 0.18, "complexity": 0.18, "tension": 0.10},
    "haze":         {"space": 0.15, "energy": -0.10, "tension": 0.08, "density": -0.12},
    "fog":          {"space": 0.15, "tension": 0.10, "energy": -0.08, "density": -0.10},
    "void":         {"space": 0.25, "energy": -0.18, "density": -0.20, "valence": -0.12},
    "transcendent": {"space": 0.20, "complexity": 0.18, "valence": 0.15, "energy": 0.10},
    "sublime":      {"space": 0.18, "complexity": 0.18, "valence": 0.15},
    "celestial":    {"space": 0.22, "complexity": 0.12, "tension": -0.10, "valence": 0.12},
    "psychedelic":  {"space": 0.18, "complexity": 0.18, "tension": 0.08, "density": 0.10},
    # dark / night
    "dark":         {"tension": 0.15, "space": 0.10, "valence": -0.15, "warmth": -0.10},
    "midnight":     {"space": 0.15, "tension": 0.12, "valence": -0.10, "energy": -0.08},
    "sinister":     {"tension": 0.20, "rawness": 0.15, "valence": -0.18},
    "haunted":      {"tension": 0.20, "space": 0.15, "nostalgia": 0.12, "valence": -0.12},
    "cursed":       {"tension": 0.18, "rawness": 0.15, "valence": -0.15},
    "horror":       {"tension": 0.22, "space": 0.12, "rawness": 0.15, "valence": -0.20},
    "demonic":      {"rawness": 0.22, "tension": 0.20, "energy": 0.15, "valence": -0.22},
    "apocalypse":   {"rawness": 0.20, "tension": 0.20, "space": 0.12, "valence": -0.15},
    # warmth / joy
    "warm":         {"warmth": 0.20, "valence": 0.15, "tension": -0.12},
    "summer":       {"valence": 0.20, "energy": 0.15, "warmth": 0.15, "movement": 0.12},
    "sun":          {"valence": 0.18, "warmth": 0.15, "energy": 0.10},
    "joy":          {"valence": 0.22, "energy": 0.15, "movement": 0.12, "tension": -0.12},
    "love":         {"warmth": 0.22, "valence": 0.18, "tension": -0.12},
    "tender":       {"warmth": 0.22, "space": 0.12, "rawness": -0.12, "density": -0.10},
    "euphoria":     {"valence": 0.25, "energy": 0.18, "movement": 0.15, "complexity": 0.10},
    "bliss":        {"valence": 0.22, "space": 0.12, "tension": -0.15, "warmth": 0.15},
    "ecstasy":      {"energy": 0.20, "valence": 0.22, "movement": 0.18, "complexity": 0.12},
    # sadness / introspection
    "sad":          {"valence": -0.20, "nostalgia": 0.18, "space": 0.12, "energy": -0.12},
    "grief":        {"valence": -0.22, "space": 0.15, "nostalgia": 0.15, "energy": -0.15},
    "loss":         {"valence": -0.18, "nostalgia": 0.18, "space": 0.12},
    "longing":      {"nostalgia": 0.22, "valence": -0.12, "space": 0.12, "warmth": 0.08},
    "melancholy":   {"nostalgia": 0.20, "valence": -0.15, "space": 0.15, "energy": -0.10},
    "desolate":     {"space": 0.22, "valence": -0.20, "energy": -0.18, "density": -0.15},
    "empty":        {"space": 0.22, "energy": -0.20, "density": -0.20, "valence": -0.12},
    # seductive / tension
    "seductive":    {"warmth": 0.18, "movement": 0.15, "tension": 0.10, "density": 0.08},
    "sensual":      {"warmth": 0.20, "movement": 0.15, "tension": 0.10, "space": 0.08},
    "lust":         {"movement": 0.18, "warmth": 0.15, "tension": 0.12, "energy": 0.08},
    "hypnotic":     {"movement": 0.15, "tension": 0.12, "density": 0.10, "complexity": 0.10},
    # nostalgia
    "memory":       {"nostalgia": 0.22, "space": 0.10, "warmth": 0.10},
    "vintage":      {"nostalgia": 0.20, "warmth": 0.12, "complexity": 0.08},
    "retro":        {"nostalgia": 0.20, "warmth": 0.10},
    "past":         {"nostalgia": 0.18, "space": 0.10},
    # kinetic
    "driving":      {"energy": 0.18, "movement": 0.20, "density": 0.12},
    "pulse":        {"energy": 0.15, "movement": 0.18, "density": 0.10},
    "frantic":      {"energy": 0.20, "tension": 0.18, "movement": 0.15, "density": 0.15},
    "sprint":       {"energy": 0.22, "movement": 0.20},
    # complex / intellectual
    "complex":      {"complexity": 0.22, "density": 0.12},
    "labyrinth":    {"complexity": 0.20, "tension": 0.12, "space": 0.10},
    "intricate":    {"complexity": 0.20, "density": 0.10},

    # -----------------------------------------------------------------------
    # Genre vocabulary
    # -----------------------------------------------------------------------
    # Electronic / club
    "edm":          {"movement": 0.25, "energy": 0.20, "density": 0.18, "space": 0.08},
    "electronic":   {"movement": 0.18, "energy": 0.15, "density": 0.15, "complexity": 0.12},
    "techno":       {"movement": 0.22, "energy": 0.18, "density": 0.20, "tension": 0.12, "warmth": -0.10},
    "house":        {"movement": 0.22, "energy": 0.15, "density": 0.15, "warmth": 0.12, "valence": 0.10},
    "rave":         {"energy": 0.25, "movement": 0.25, "density": 0.15, "tension": 0.10},
    "dnb":          {"energy": 0.25, "movement": 0.28, "tension": 0.15, "density": 0.18},
    "jungle":       {"energy": 0.22, "movement": 0.25, "density": 0.18, "rawness": 0.12},
    "trance":       {"movement": 0.20, "energy": 0.18, "space": 0.12, "valence": 0.12},
    "dubstep":      {"energy": 0.22, "rawness": 0.18, "tension": 0.15, "density": 0.18},
    "synthwave":    {"nostalgia": 0.22, "movement": 0.15, "energy": 0.10, "warmth": 0.08},
    # Heavy
    "hardcore":     {"energy": 0.28, "rawness": 0.28, "tension": 0.22, "density": 0.20, "valence": -0.12},
    "metal":        {"energy": 0.22, "rawness": 0.22, "tension": 0.18, "density": 0.15, "valence": -0.10},
    "punk":         {"energy": 0.20, "rawness": 0.25, "tension": 0.15, "valence": -0.05},
    "grunge":       {"rawness": 0.20, "tension": 0.15, "energy": 0.15, "nostalgia": 0.10},
    "industrial":   {"tension": 0.20, "rawness": 0.18, "energy": 0.15, "density": 0.15, "warmth": -0.15},
    "noise":        {"rawness": 0.25, "tension": 0.20, "density": 0.20, "energy": 0.15},
    "grime":        {"rawness": 0.18, "tension": 0.15, "energy": 0.15, "movement": 0.12},
    "drill":        {"rawness": 0.20, "tension": 0.18, "energy": 0.12, "density": 0.15},
    # Indie / alternative
    "indie":        {"warmth": 0.15, "complexity": 0.10, "nostalgia": 0.12, "valence": 0.10},
    "alternative":  {"complexity": 0.12, "rawness": 0.08, "tension": 0.08},
    "shoegaze":     {"space": 0.18, "complexity": 0.12, "density": 0.10, "nostalgia": 0.12},
    "dream pop":    {"space": 0.20, "warmth": 0.15, "nostalgia": 0.12, "energy": -0.08},
    # Hip-hop / urban
    "trap":         {"tension": 0.15, "rawness": 0.18, "energy": 0.15, "density": 0.15, "movement": 0.12},
    "rap":          {"energy": 0.15, "rawness": 0.15, "movement": 0.12, "density": 0.10},
    "hip":          {"movement": 0.15, "energy": 0.12, "density": 0.10},
    "hop":          {"movement": 0.12, "density": 0.08},
    # Organic / warm
    "jazz":         {"complexity": 0.22, "warmth": 0.15, "space": 0.10, "nostalgia": 0.12},
    "folk":         {"nostalgia": 0.20, "warmth": 0.18, "complexity": -0.05, "rawness": -0.10},
    "soul":         {"warmth": 0.20, "valence": 0.15, "nostalgia": 0.12},
    "blues":        {"nostalgia": 0.18, "warmth": 0.12, "rawness": 0.10, "tension": 0.08},
    "gospel":       {"valence": 0.20, "warmth": 0.18, "energy": 0.12, "density": 0.10},
    "reggae":       {"movement": 0.15, "warmth": 0.18, "valence": 0.12, "tension": -0.10},
    "dub":          {"space": 0.18, "warmth": 0.15, "movement": 0.12, "density": -0.10},
    # Experimental / atmospheric
    "ambient":      {"space": 0.25, "energy": -0.20, "density": -0.18, "tension": -0.10, "movement": -0.12},
    "experimental": {"complexity": 0.22, "space": 0.12, "tension": 0.10},
    "psychedelic":  {"space": 0.18, "complexity": 0.18, "tension": 0.08, "density": 0.10},
    "drone":        {"space": 0.20, "density": 0.15, "energy": -0.12, "movement": -0.15},
    "glitch":       {"complexity": 0.18, "tension": 0.15, "rawness": 0.15, "movement": 0.08},
    "wave":         {"space": 0.15, "nostalgia": 0.15, "tension": 0.10, "warmth": -0.05},
    # Mainstream
    "pop":          {"valence": 0.18, "energy": 0.12, "warmth": 0.12, "complexity": -0.08},
    "classical":    {"complexity": 0.22, "space": 0.15, "density": 0.12, "warmth": 0.10},
    "orchestral":   {"complexity": 0.20, "density": 0.12, "space": 0.10},
    "cinematic":    {"complexity": 0.18, "space": 0.15, "tension": 0.08},
    # Fusion
    "fusion":       {"complexity": 0.15, "space": 0.08},
    "hybrid":       {"complexity": 0.12, "density": 0.08},
    "crossover":    {"complexity": 0.10},

    # -----------------------------------------------------------------------
    # Structural / event vocabulary
    # -----------------------------------------------------------------------
    "drop":         {"energy": 0.28, "movement": 0.28, "density": 0.22, "tension": 0.18, "space": -0.12},
    "drops":        {"energy": 0.28, "movement": 0.28, "density": 0.22, "tension": 0.18, "space": -0.12},
    "build":        {"energy": 0.12, "movement": 0.12, "tension": 0.15, "density": 0.10},
    "buildup":      {"energy": 0.15, "movement": 0.15, "tension": 0.18, "density": 0.12},
    "hook":         {"valence": 0.15, "movement": 0.12, "energy": 0.10},
    "chorus":       {"valence": 0.15, "energy": 0.12, "density": 0.10},
    "bass":         {"energy": 0.12, "density": 0.15, "rawness": 0.10},
    "beat":         {"movement": 0.18, "energy": 0.12, "density": 0.08},
    "groove":       {"movement": 0.18, "warmth": 0.12, "tension": -0.05},
    "bounce":       {"movement": 0.15, "energy": 0.12, "valence": 0.10},
    "rhythm":       {"movement": 0.15, "complexity": 0.08},
    "stomp":        {"energy": 0.18, "movement": 0.15, "rawness": 0.10},
    "headbang":     {"energy": 0.20, "rawness": 0.18, "movement": 0.15},
    "dance":        {"movement": 0.20, "energy": 0.15, "valence": 0.12},
    "anthem":       {"energy": 0.20, "valence": 0.18, "density": 0.12, "complexity": 0.10},
    "peak":         {"energy": 0.22, "tension": 0.15, "movement": 0.18},
    "climax":       {"energy": 0.22, "tension": 0.18, "movement": 0.20},
    "punch":        {"energy": 0.18, "rawness": 0.15, "density": 0.12},
    # Texture
    "heavy":        {"energy": 0.20, "density": 0.18, "rawness": 0.15},
    "dense":        {"density": 0.20, "complexity": 0.10},
    "thick":        {"density": 0.18, "energy": 0.10},
    "lush":         {"space": 0.12, "density": 0.10, "warmth": 0.12},
    "sparse":       {"space": 0.15, "density": -0.15, "energy": -0.10},
    "distorted":    {"rawness": 0.20, "tension": 0.12, "energy": 0.10},
    "fuzzy":        {"rawness": 0.15, "tension": 0.08, "complexity": 0.08},
    "intense":      {"energy": 0.22, "tension": 0.18, "density": 0.15},
    "chill":        {"energy": -0.18, "tension": -0.18, "warmth": 0.15, "space": 0.12},
    "chilled":      {"energy": -0.18, "tension": -0.18, "warmth": 0.15, "space": 0.12},
    "slow":         {"energy": -0.15, "movement": -0.18, "space": 0.12},
    "fast":         {"energy": 0.18, "movement": 0.20, "density": 0.10},
    "epic":         {"energy": 0.18, "complexity": 0.15, "space": 0.12, "density": 0.10},
}

# Per-act weights: how much of each dimension boost lands on each act (0–1)
# "party in a car crash that ends in a dream" →
#   party energy lands on aggressive/seductive, crash tension on seductive/breakdown,
#   dream ethereal lands on breakdown/sublime
_ACT_PHASE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "aggressive": {"energy": 1.0, "tension": 0.6, "rawness": 1.0, "density": 1.0,
                   "valence": 0.6, "movement": 0.8, "warmth": 0.2, "space": 0.2,
                   "complexity": 0.4, "nostalgia": 0.2},
    "seductive":  {"energy": 0.5, "tension": 0.7, "rawness": 0.5, "density": 0.5,
                   "valence": 0.8, "movement": 1.0, "warmth": 0.9, "space": 0.4,
                   "complexity": 0.5, "nostalgia": 0.4},
    "breakdown":  {"energy": 0.3, "tension": 0.9, "rawness": 0.6, "density": 0.2,
                   "valence": 0.7, "movement": 0.2, "warmth": 0.3, "space": 1.0,
                   "complexity": 0.5, "nostalgia": 0.9},
    "sublime":    {"energy": 0.6, "tension": 0.2, "rawness": 0.2, "density": 0.5,
                   "valence": 0.9, "movement": 0.6, "warmth": 0.7, "space": 0.9,
                   "complexity": 1.0, "nostalgia": 0.5},
}

# Base act targets (mirrors ACT_DEFINITIONS in playlust.py — kept in sync)
_BASE_ACT_TARGETS: Dict[str, Dict[str, float]] = {
    "aggressive": {"energy": 0.88, "valence": 0.38, "tension": 0.82, "density": 0.78,
                   "warmth": 0.28, "movement": 0.85, "space": 0.30, "rawness": 0.80,
                   "complexity": 0.58, "nostalgia": 0.35},
    "seductive":  {"energy": 0.58, "valence": 0.72, "tension": 0.28, "density": 0.52,
                   "warmth": 0.82, "movement": 0.68, "space": 0.55, "rawness": 0.32,
                   "complexity": 0.52, "nostalgia": 0.55},
    "breakdown":  {"energy": 0.22, "valence": 0.32, "tension": 0.62, "density": 0.28,
                   "warmth": 0.38, "movement": 0.22, "space": 0.85, "rawness": 0.42,
                   "complexity": 0.42, "nostalgia": 0.68},
    "sublime":    {"energy": 0.72, "valence": 0.82, "tension": 0.22, "density": 0.62,
                   "warmth": 0.72, "movement": 0.62, "space": 0.78, "rawness": 0.28,
                   "complexity": 0.78, "nostalgia": 0.48},
}

# ---------------------------------------------------------------------------
# Arc modifiers — directional/temporal cues that redistribute intensity across acts.
# Tokens detected in the mood string scale each act's energy+movement+tension by
# the multiplier below, allowing "fading into hardocre" to build rather than stay flat.
# ---------------------------------------------------------------------------

# Things that escalate toward the later acts (energy peaks in breakdown/sublime)
_ARC_TOKENS_ESCALATE = frozenset({
    "building", "rising", "escalating", "growing", "climbing",
    "ascending", "crescendo", "mounting", "intensifying", "ramping",
    "accelerating", "exploding",
})
# Things that fade / soften after an early peak
_ARC_TOKENS_DESCEND = frozenset({
    "fading", "fade", "dissolving", "decaying", "falling",
    "dying", "drifting", "winding", "melting", "ebbing",
    "dissipating", "quieting",
})
# A big moment lands in the middle of the arc (drop / climax in breakdown)
_ARC_TOKENS_PEAK_MID = frozenset({
    "drops", "drop", "erupts", "explodes", "detonates",
    "peaks", "apex", "climax", "summit",
})

# Per-arc-token: multiplicative scale applied to (energy, movement, tension) per act.
# "escalate" → starts softer (0.82 × aggressive), gets heavier by sublime (1.15 ×)
_ARC_ACT_SCALE: Dict[str, Dict[str, float]] = {
    "escalate": {"aggressive": 0.82, "seductive": 0.95, "breakdown": 1.10, "sublime": 1.15},
    "descend":  {"aggressive": 1.12, "seductive": 1.00, "breakdown": 0.90, "sublime": 0.82},
    "peak_mid": {"aggressive": 0.90, "seductive": 1.05, "breakdown": 1.20, "sublime": 0.95},
}

_ARC_DIMS_AFFECTED = frozenset({"energy", "movement", "tension", "density", "rawness"})


def _detect_arc(tokens: list) -> Optional[str]:
    """Return 'escalate', 'descend', 'peak_mid', or None based on mood tokens."""
    token_set = set(tokens)
    # Check peak_mid first (drop/climax is most specific)
    if token_set & _ARC_TOKENS_PEAK_MID:
        return "peak_mid"
    if token_set & _ARC_TOKENS_ESCALATE:
        return "escalate"
    if token_set & _ARC_TOKENS_DESCEND:
        return "descend"
    return None


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a music intelligence assistant. Given a mood description, map it to \
dimensional emotional targets for a four-act playlist arc. Return ONLY valid \
JSON — no explanation, no markdown, no extra text.

The four acts are:
  aggressive — confrontational opening: raw energy, tension, density
  seductive  — warmth floods in: movement, groove, hypnotic
  breakdown  — collapse: vast space, nostalgia, introspective quiet
  sublime    — transcendent resolution: complexity, euphoria, space

The 10 dimensions (all 0.0–1.0):
  energy     physical power and drive
  valence    positivity / joy
  tension    anxiety, unease, dread
  density    sonic layering and compression
  warmth     intimacy, comfort, softness
  movement   rhythmic momentum
  space      openness, reverb, emptiness
  rawness    grit, unpolished edge
  complexity musical intricacy
  nostalgia  retro feeling, memory

Interpret the mood as an emotional arc across the four acts. \
High energy phrases map to higher numbers. Contradictions create interesting \
tension between acts. Narrative arcs (start → middle → end) map naturally to \
the four acts."""

_USER_PROMPT_TEMPLATE = """\
Mood: {mood}

Return JSON with this exact shape (all float values 0.0–1.0, all 10 dims \
present in each act):

{{
  "interpretation": "<one sentence describing the arc>",
  "acts": {{
    "aggressive": {{"energy": 0.0, "valence": 0.0, "tension": 0.0, "density": 0.0, "warmth": 0.0, "movement": 0.0, "space": 0.0, "rawness": 0.0, "complexity": 0.0, "nostalgia": 0.0}},
    "seductive":  {{"energy": 0.0, "valence": 0.0, "tension": 0.0, "density": 0.0, "warmth": 0.0, "movement": 0.0, "space": 0.0, "rawness": 0.0, "complexity": 0.0, "nostalgia": 0.0}},
    "breakdown":  {{"energy": 0.0, "valence": 0.0, "tension": 0.0, "density": 0.0, "warmth": 0.0, "movement": 0.0, "space": 0.0, "rawness": 0.0, "complexity": 0.0, "nostalgia": 0.0}},
    "sublime":    {{"energy": 0.0, "valence": 0.0, "tension": 0.0, "density": 0.0, "warmth": 0.0, "movement": 0.0, "space": 0.0, "rawness": 0.0, "complexity": 0.0, "nostalgia": 0.0}}
  }}
}}"""


def _llm_interpret(mood: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Call the local LLM and parse the dimensional JSON response."""
    try:
        from oracle.llm import LLMClient
        client = LLMClient.from_env()
        result = client.chat(
            messages=[{"role": "user", "content": _USER_PROMPT_TEMPLATE.format(mood=mood)}],
            system=_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=800,
            json_mode=False,  # LM Studio uses text mode + prompt-level JSON instruction
        )
        if not result.get("ok") or not result.get("text"):
            logger.debug("[MoodInterpreter] LLM returned no text: %s", result.get("error", ""))
            return None

        # Strip markdown fences if present
        raw = result["text"].strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        acts = parsed.get("acts", {})
        interpretation = parsed.get("interpretation", "")

        validated: Dict[str, Dict[str, float]] = {}
        for act in _ACT_NAMES:
            if act not in acts:
                continue
            act_dims = acts[act]
            if not isinstance(act_dims, dict):
                continue
            validated[act] = {
                dim: float(max(0.0, min(1.0, act_dims.get(dim, _BASE_ACT_TARGETS[act][dim]))))
                for dim in _DIMENSIONS
            }

        if interpretation:
            logger.info("[MoodInterpreter] LLM arc: %s", interpretation)
        logger.info("[MoodInterpreter] LLM gave overrides for acts: %s", list(validated.keys()))
        return validated if validated else None

    except Exception as exc:
        logger.debug("[MoodInterpreter] LLM path failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Keyword heuristic fallback
# ---------------------------------------------------------------------------

def _keyword_interpret(mood: str) -> Dict[str, Dict[str, float]]:
    """Deterministic keyword → dimension mapping, no LLM needed."""
    tokens = re.findall(r"[a-z]+", mood.lower())

    # Accumulate global dimension deltas from all matched keywords
    global_delta: Dict[str, float] = {dim: 0.0 for dim in _DIMENSIONS}
    matched: list = []
    for token in tokens:
        boosts = _KEYWORD_DIM_BOOSTS.get(token)
        if boosts:
            matched.append(token)
            for dim, val in boosts.items():
                global_delta[dim] = global_delta.get(dim, 0.0) + val

    # Build per-act targets by blending base + (delta × act_phase_weight)
    result: Dict[str, Dict[str, float]] = {}
    for act in _ACT_NAMES:
        phase_weights = _ACT_PHASE_WEIGHTS[act]
        base = _BASE_ACT_TARGETS[act]
        act_dims: Dict[str, float] = {}
        for dim in _DIMENSIONS:
            delta = global_delta.get(dim, 0.0) * phase_weights.get(dim, 0.5)
            raw = base[dim] + delta
            act_dims[dim] = round(max(0.0, min(1.0, raw)), 4)
        result[act] = act_dims

    # Apply arc modifiers: directional/temporal cues redistribute intensity across acts
    arc = _detect_arc(tokens)
    if arc:
        scale_map = _ARC_ACT_SCALE[arc]
        for act in _ACT_NAMES:
            factor = scale_map.get(act, 1.0)
            if factor == 1.0:
                continue
            base_targets = _BASE_ACT_TARGETS[act]
            for dim in _ARC_DIMS_AFFECTED:
                original = result[act][dim]
                # Scale the deviation from base, not the absolute value
                deviation = original - base_targets[dim]
                result[act][dim] = round(max(0.0, min(1.0, base_targets[dim] + deviation * factor)), 4)

    if matched:
        logger.debug("[MoodInterpreter] keyword matched: %s | arc: %s", matched, arc)

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def interpret_mood(
    mood: str,
    llm_blend: float = 0.65,
    try_llm: bool = True,
) -> Dict[str, Dict[str, float]]:
    """Translate a natural language mood string into per-act dimensional targets.

    Attempts LLM interpretation first; falls back to keyword heuristic so the
    feature always works regardless of LLM availability.

    Args:
        mood: Free-form mood description.
              Examples: "party in a car crash that ends in a dream",
                        "haunted carnival at 3am",
                        "euphoric breakdown at the end of the world"
        llm_blend: How strongly the LLM result overrides the keyword result
                   (0.0 = keyword only, 1.0 = LLM only).  The blend keeps
                   the keyword heuristic as a sanity anchor.
        try_llm: Set False to skip LLM entirely (useful in tests/CLI).

    Returns:
        Dict mapping act name → {dimension: float (0.0–1.0), ...}
        for all four acts and all 10 dimensions.
    """
    if not mood or not mood.strip():
        return {}

    keyword_result = _keyword_interpret(mood)

    if not try_llm:
        return keyword_result

    llm_result = _llm_interpret(mood)
    if not llm_result:
        logger.debug("[MoodInterpreter] using keyword fallback for '%s'", mood)
        return keyword_result

    # Blend: LLM carries most of the weight, keyword anchors extremes
    blended: Dict[str, Dict[str, float]] = {}
    for act in _ACT_NAMES:
        llm_act = llm_result.get(act, {})
        kw_act = keyword_result.get(act, {})
        blended[act] = {
            dim: round(
                llm_blend * llm_act.get(dim, _BASE_ACT_TARGETS[act][dim])
                + (1.0 - llm_blend) * kw_act.get(dim, _BASE_ACT_TARGETS[act][dim]),
                4,
            )
            for dim in _DIMENSIONS
        }

    return blended

"""User-friendly descriptors derived from the canonical 10 dimensions."""

from __future__ import annotations

from typing import Dict, List, Any


def _band(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def describe_scores(scores: Dict[str, float] | None) -> Dict[str, Any]:
    if not scores:
        return {"summary": "No emotional profile yet.", "tags": [], "details": {}}

    def g(key: str) -> float:
        v = scores.get(key)
        try:
            return float(v) if v is not None else 0.0
        except Exception:
            return 0.0

    energy = g("energy")
    valence = g("valence")
    tension = g("tension")
    density = g("density")
    warmth = g("warmth")
    movement = g("movement")
    space = g("space")
    rawness = g("rawness")
    complexity = g("complexity")
    nostalgia = g("nostalgia")

    # Derived metrics (kept separate from canonical dimensions)
    intensity = max(0.0, min(1.0, (energy + tension + movement) / 3.0))
    intimacy = max(0.0, min(1.0, (warmth + (1.0 - space)) / 2.0))
    polish = max(0.0, min(1.0, 1.0 - rawness))
    emotional_depth = max(0.0, min(1.0, (complexity + nostalgia + tension) / 3.0))

    mood = "uplifting" if valence >= 0.6 else "moody" if valence <= 0.4 else "balanced"
    power = "high energy" if intensity >= 0.7 else "steady energy" if intensity >= 0.45 else "chill"
    texture = "raw and gritty" if rawness >= 0.7 else "clean and polished" if polish >= 0.7 else "mixed texture"
    room = "wide/open" if space >= 0.7 else "close/intimate" if intimacy >= 0.7 else "mid-sized"
    depth = "emotionally deep" if emotional_depth >= 0.7 else "straightforward" if emotional_depth <= 0.4 else "layered"

    tags: List[str] = []
    if intensity >= 0.7:
        tags.append("adrenaline")
    if valence >= 0.65:
        tags.append("feel-good")
    if valence <= 0.35:
        tags.append("melancholic")
    if nostalgia >= 0.65:
        tags.append("nostalgic")
    if complexity >= 0.7:
        tags.append("intricate")
    if rawness >= 0.7:
        tags.append("gritty")
    if warmth >= 0.7:
        tags.append("warm")
    if space >= 0.7:
        tags.append("atmospheric")
    if movement >= 0.7:
        tags.append("driving")

    summary = f"{mood}, {power}, {depth}, {texture}, {room}"
    details = {
        "intensity": round(intensity, 3),
        "intimacy": round(intimacy, 3),
        "polish": round(polish, 3),
        "emotional_depth": round(emotional_depth, 3),
        "bands": {
            "energy": _band(energy),
            "valence": _band(valence),
            "tension": _band(tension),
            "density": _band(density),
            "warmth": _band(warmth),
            "movement": _band(movement),
            "space": _band(space),
            "rawness": _band(rawness),
            "complexity": _band(complexity),
            "nostalgia": _band(nostalgia),
        },
    }

    return {"summary": summary, "tags": tags, "details": details}


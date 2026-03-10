"""CLAP anchor phrases for dimensional scoring.

This module defines phrase sets for each emotional/sonic dimension. The scorer
embeds these phrases with the same CLAP text encoder used by the system and then
scores track embeddings by similarity to the anchors.

Anchor design principle:
- Use multiple phrases per pole to reduce prompt brittleness.
- Keep phrases concrete and audio-descriptive.
"""

from __future__ import annotations

from typing import Dict, List


ANCHORS: Dict[str, Dict[str, List[str]]] = {
    "energy": {
        "low": [
            "extremely calm peaceful quiet ambient music with silence",
            "whisper soft barely audible delicate lullaby",
            "slow quiet meditation music with no drums",
        ],
        "high": [
            "loud aggressive thrashing heavy metal with screaming",
            "explosive maximum energy EDM drop with bass",
            "fast violent punk rock mosh pit music",
        ],
    },
    "valence": {
        "low": [
            "deeply sad crying funeral dirge depressing",
            "hopeless tragic grief despair weeping",
            "dark doom miserable anguish heartbreak music",
        ],
        "high": [
            "ecstatic euphoric celebration party cheering",
            "pure joy sunshine happiness dancing laughing",
            "triumphant victorious elated bliss anthem",
        ],
    },
    "tension": {
        "low": [
            "completely relaxed peaceful resolved easy listening",
            "serene tranquil spa music gentle flowing water sounds",
            "calm comfortable content settled lullaby",
        ],
        "high": [
            "extreme tension horror suspense thriller music",
            "dissonant chaotic frantic panic anxiety attack",
            "unresolved jarring unsettling stabbing strings",
        ],
    },
    "density": {
        "low": [
            "solo acoustic guitar and nothing else",
            "single voice acapella completely bare",
            "one instrument playing alone in silence",
        ],
        "high": [
            "massive orchestra with full choir and percussion",
            "wall of sound layers upon layers of instruments",
            "dense thick heavy production with everything playing",
        ],
    },
    "warmth": {
        "low": [
            "cold robotic synthetic autotune digital glitch",
            "icy metallic harsh sterile machine music",
            "frozen clinical electronic with no soul",
        ],
        "high": [
            "warm vinyl crackle analog tape hiss soulful",
            "cozy fireside acoustic guitar and soft singing",
            "rich warm tube amp organic honey-toned",
        ],
    },
    "movement": {
        "low": [
            "frozen still drone ambient soundscape no rhythm",
            "suspended ethereal hovering in place meditation",
            "zero beat static atmosphere pure texture",
        ],
        "high": [
            "driving fast beat pounding rhythm running music",
            "irresistible groove head-bobbing dancing funk",
            "relentless propulsive unstoppable drumbeat",
        ],
    },
    "space": {
        "low": [
            "close whisper in ear intimate dry no reverb",
            "tiny bedroom recording close microphone ASMR",
            "claustrophobic tight compressed lo-fi mono",
        ],
        "high": [
            "vast cathedral echo massive reverb canyon",
            "oceanic endless horizon ambient wash spacious",
            "huge arena concert echoing into infinity",
        ],
    },
    "rawness": {
        "low": [
            "perfect studio polished crystal clear hi-fi",
            "flawless production smooth pop radio hit",
            "pristine clean mastered glossy professional",
        ],
        "high": [
            "distorted broken speaker blown out fuzzy noise",
            "garage band lo-fi cassette tape hiss crackle",
            "raw screaming unpolished punk recorded in basement",
        ],
    },
    "complexity": {
        "low": [
            "three chord simple pop song nursery rhyme",
            "basic repetitive loop with one beat pattern",
            "dead simple straightforward easy melody",
        ],
        "high": [
            "progressive jazz fusion with time signature changes",
            "virtuosic technical mathrock polyrhythm",
            "classical symphony with movements and counterpoint",
        ],
    },
    "nostalgia": {
        "low": [
            "brand new modern contemporary 2024 fresh sound",
            "futuristic cutting edge experimental new music",
            "current generation production never heard before",
        ],
        "high": [
            "sounds exactly like 1970s vinyl record oldies",
            "classic retro vintage throwback to the past",
            "old nostalgic remember when grandparent music",
        ],
    },
}

"""Track classifier for detecting junk, remixes, live recordings, and covers."""

from __future__ import annotations

import re
from typing import Dict, Tuple
from pathlib import Path

from oracle.db.schema import get_connection


# Token patterns for classification
JUNK_TOKENS = [
    "vevo", "official video", "official audio", "official music video",
    "lyrics", "lyric video", "hd", "4k", "8k", "visualizer",
    "official visualizer", "audio", "free download", "full album",
    "full ep", "full mixtape", "playlist", "compilation"
]

REMIX_TOKENS = [
    "remix", "edit", "rework", "bootleg", "vip", "flip",
    "refix", "version", "mix", "mashup", "blend"
]

LIVE_TOKENS = [
    "live", "concert", "acoustic", "unplugged", "session",
    "live at", "live from", "live session", "live performance",
    "bbc live", "kexp", "tiny desk"
]

COVER_TOKENS = [
    "cover", "rendition", "tribute", "originally by",
    "cover version", "interpretation"
]

SPECIAL_TOKENS = [
    "sped up", "speed up", "slowed", "slowed down", "reverb",
    "nightcore", "8d audio", "8d", "bass boosted", "boosted",
    "extended", "extended mix", "radio edit", "clean", "explicit",
    "instrumental", "acapella", "a cappella"
]


def _normalize_text(text: str) -> str:
    """Lowercase and strip for matching."""
    if not text:
        return ""
    return text.lower().strip()


def _detect_tokens(text: str, token_list: list) -> Tuple[bool, list]:
    """
    Check if any tokens from the list are present in text.
    
    Returns:
        (found, matched_tokens)
    """
    normalized = _normalize_text(text)
    matched = []
    
    for token in token_list:
        # Use word boundaries for better matching
        pattern = r'\b' + re.escape(token.lower()) + r'\b'
        if re.search(pattern, normalized):
            matched.append(token)
    
    return len(matched) > 0, matched


def classify_track(track_id: str) -> Dict:
    """
    Classify a track by detecting version type and confidence.
    
    Args:
        track_id: Track ID to classify
        
    Returns:
        {
            "version_type": "original"|"remix"|"live"|"cover"|"junk"|"special",
            "confidence": 0.0-1.0,
            "tokens_found": [list of matched tokens],
            "reason": explanation
        }
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get track metadata
    cursor.execute(
        "SELECT artist, title, album, filepath FROM tracks WHERE track_id = ?",
        (track_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "version_type": "unknown",
            "confidence": 0.0,
            "tokens_found": [],
            "reason": "track not found"
        }
    
    artist, title, album, filepath = row
    
    # Build combined text for analysis
    search_text_parts = []
    if title:
        search_text_parts.append(title)
    if album:
        search_text_parts.append(album)
    if filepath:
        # Include filename without extension
        filename = Path(filepath).stem
        search_text_parts.append(filename)
    
    search_text = " ".join(search_text_parts)
    
    # Priority order: junk > cover > live > remix > special > original
    # Junk detection (highest priority)
    has_junk, junk_matches = _detect_tokens(search_text, JUNK_TOKENS)
    if has_junk:
        return {
            "version_type": "junk",
            "confidence": min(0.7 + (len(junk_matches) * 0.1), 1.0),
            "tokens_found": junk_matches,
            "reason": f"Detected junk tokens: {', '.join(junk_matches)}"
        }
    
    # Cover detection
    has_cover, cover_matches = _detect_tokens(search_text, COVER_TOKENS)
    if has_cover:
        return {
            "version_type": "cover",
            "confidence": min(0.8 + (len(cover_matches) * 0.1), 1.0),
            "tokens_found": cover_matches,
            "reason": f"Detected cover tokens: {', '.join(cover_matches)}"
        }
    
    # Live detection
    has_live, live_matches = _detect_tokens(search_text, LIVE_TOKENS)
    if has_live:
        return {
            "version_type": "live",
            "confidence": min(0.7 + (len(live_matches) * 0.1), 1.0),
            "tokens_found": live_matches,
            "reason": f"Detected live tokens: {', '.join(live_matches)}"
        }
    
    # Remix detection
    has_remix, remix_matches = _detect_tokens(search_text, REMIX_TOKENS)
    if has_remix:
        return {
            "version_type": "remix",
            "confidence": min(0.7 + (len(remix_matches) * 0.1), 1.0),
            "tokens_found": remix_matches,
            "reason": f"Detected remix tokens: {', '.join(remix_matches)}"
        }
    
    # Special detection (extended, instrumental, etc.)
    has_special, special_matches = _detect_tokens(search_text, SPECIAL_TOKENS)
    if has_special:
        return {
            "version_type": "special",
            "confidence": min(0.6 + (len(special_matches) * 0.1), 0.9),
            "tokens_found": special_matches,
            "reason": f"Detected special tokens: {', '.join(special_matches)}"
        }
    
    # Default: original
    return {
        "version_type": "original",
        "confidence": 0.5,
        "tokens_found": [],
        "reason": "No special tokens detected, assuming original"
    }


def classify_and_update(track_id: str) -> Dict:
    """
    Classify track and update database with version_type and confidence.
    
    Args:
        track_id: Track ID to classify
        
    Returns:
        Classification result dict
    """
    result = classify_track(track_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Update tracks table
    cursor.execute(
        """
        UPDATE tracks 
        SET version_type = ?, confidence = ?
        WHERE track_id = ?
        """,
        (result["version_type"], result["confidence"], track_id)
    )
    
    conn.commit()
    conn.close()
    
    return result


def _llm_classify_track(artist: str, title: str, album: str, filepath: str) -> Dict:
    """Second-pass LLM classifier for ambiguous tracks.

    Called when regex gives 'original' at low confidence (0.5) — meaning no
    keywords were found, but the track could still be karaoke, tribute, or
    mislabeled. LM Studio must be running; returns None if offline.
    """
    try:
        from oracle.llm import LLMClient
        client = LLMClient.from_env()
        filename = Path(filepath).stem if filepath else ""
        context = f"Album: {album}" if album else ""
        if filename and filename not in title:
            context = f"{context} | File: {filename}".strip(" |")

        result = client.classify(
            artist=artist,
            title=title,
            categories=["original", "karaoke", "tribute", "cover", "remix",
                        "live", "instrumental", "junk", "unknown"],
            context=context,
        )
        if not result.get("ok"):
            return {}

        # Map LLM categories back to classifier schema
        cat = result.get("category", "unknown")
        if cat in ("karaoke", "tribute"):
            cat = "junk"
        return {
            "version_type": cat,
            "confidence": result.get("confidence", 0.6),
            "tokens_found": [],
            "reason": f"[LLM] {result.get('reason', '')}",
        }
    except Exception:
        return {}


def classify_library(limit: int = 0, use_llm: bool = False) -> Dict:
    """Classify all tracks in the library.

    Args:
        limit: Max tracks to classify (0 = all).
        use_llm: If True, use LLM as a second pass for regex-ambiguous tracks
                 (version_type='original' at confidence=0.5). Requires LM Studio.

    Returns:
        Summary dict with counts by version_type.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if limit > 0:
        cursor.execute(
            "SELECT track_id, artist, title, album, filepath FROM tracks LIMIT ?",
            (limit,)
        )
    else:
        cursor.execute("SELECT track_id, artist, title, album, filepath FROM tracks")

    rows = cursor.fetchall()
    conn.close()

    summary: Dict = {
        "total": len(rows),
        "original": 0, "remix": 0, "live": 0, "cover": 0,
        "junk": 0, "special": 0, "unknown": 0,
        "llm_checked": 0,
    }

    for track_id, artist, title, album, filepath in rows:
        result = classify_and_update(track_id)

        # LLM second pass: only for ambiguous originals when LM Studio is available
        if use_llm and result["version_type"] == "original" and result["confidence"] <= 0.5:
            llm_result = _llm_classify_track(artist or "", title or "",
                                             album or "", filepath or "")
            if llm_result:
                summary["llm_checked"] += 1
                if llm_result["version_type"] != "original":
                    # LLM found something regex missed — persist the update
                    conn2 = get_connection()
                    conn2.execute(
                        "UPDATE tracks SET version_type=?, confidence=? WHERE track_id=?",
                        (llm_result["version_type"], llm_result["confidence"], track_id),
                    )
                    conn2.commit()
                    conn2.close()
                    result = llm_result

        version_type = result["version_type"]
        summary[version_type] = summary.get(version_type, 0) + 1

    return summary


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    # Test classification
    import sys
    if len(sys.argv) > 1:
        track_id = sys.argv[1]
        result = classify_track(track_id)
        print(f"Track {track_id}:")
        print(f"  Version Type: {result['version_type']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Tokens: {', '.join(result['tokens_found']) if result['tokens_found'] else 'none'}")
        print(f"  Reason: {result['reason']}")
    else:
        print("Usage: python -m oracle.classifier <track_id>")

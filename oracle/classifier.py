"""Track classifier for detecting junk, remixes, live recordings, and covers."""

from __future__ import annotations

import re
<<<<<<< HEAD
from typing import Dict, Tuple
from pathlib import Path
=======
import time
from pathlib import Path
from typing import Dict, Tuple
>>>>>>> fc77b41 (Update workspace state and diagnostics)

from oracle.db.schema import get_connection


# Token patterns for classification
JUNK_TOKENS = [
    "vevo", "official video", "official audio", "official music video",
    "lyrics", "lyric video", "hd", "4k", "8k", "visualizer",
    "official visualizer", "audio", "free download", "full album",
<<<<<<< HEAD
    "full ep", "full mixtape", "playlist", "compilation"
=======
    "full ep", "full mixtape", "playlist", "compilation",
>>>>>>> fc77b41 (Update workspace state and diagnostics)
]

REMIX_TOKENS = [
    "remix", "edit", "rework", "bootleg", "vip", "flip",
<<<<<<< HEAD
    "refix", "version", "mix", "mashup", "blend"
=======
    "refix", "version", "mix", "mashup", "blend",
>>>>>>> fc77b41 (Update workspace state and diagnostics)
]

LIVE_TOKENS = [
    "live", "concert", "acoustic", "unplugged", "session",
    "live at", "live from", "live session", "live performance",
<<<<<<< HEAD
    "bbc live", "kexp", "tiny desk"
=======
    "bbc live", "kexp", "tiny desk",
>>>>>>> fc77b41 (Update workspace state and diagnostics)
]

COVER_TOKENS = [
    "cover", "rendition", "tribute", "originally by",
<<<<<<< HEAD
    "cover version", "interpretation"
=======
    "cover version", "interpretation",
>>>>>>> fc77b41 (Update workspace state and diagnostics)
]

SPECIAL_TOKENS = [
    "sped up", "speed up", "slowed", "slowed down", "reverb",
    "nightcore", "8d audio", "8d", "bass boosted", "boosted",
    "extended", "extended mix", "radio edit", "clean", "explicit",
<<<<<<< HEAD
    "instrumental", "acapella", "a cappella"
]

=======
    "instrumental", "acapella", "a cappella",
]

LLM_APPLY_CONFIDENCE_MIN = 0.80
LLM_APPLYABLE_VERSION_TYPES = {"junk", "cover", "live", "remix", "special"}
VALID_VERSION_TYPES = {"original", "remix", "live", "cover", "junk", "special", "unknown"}

>>>>>>> fc77b41 (Update workspace state and diagnostics)

def _normalize_text(text: str) -> str:
    """Lowercase and strip for matching."""
    if not text:
        return ""
    return text.lower().strip()


def _detect_tokens(text: str, token_list: list) -> Tuple[bool, list]:
<<<<<<< HEAD
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
    
=======
    """Check if any tokens from the list are present in text."""
    normalized = _normalize_text(text)
    matched = []

    for token in token_list:
        # Use word boundaries for better matching.
        pattern = r"\b" + re.escape(token.lower()) + r"\b"
        if re.search(pattern, normalized):
            matched.append(token)

    return len(matched) > 0, matched


def _map_llm_category(category: str) -> str:
    """Map raw LLM category values to classifier schema categories."""
    normalized = _normalize_text(category)
    category_map = {
        "karaoke": "junk",
        "tribute": "junk",
        "instrumental": "special",
    }
    mapped = category_map.get(normalized, normalized)
    if mapped in VALID_VERSION_TYPES:
        return mapped
    return "unknown"


def classify_track(track_id: str) -> Dict:
    """Classify a track by detecting version type and confidence."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT artist, title, album, filepath FROM tracks WHERE track_id = ?",
        (track_id,),
    )
    row = cursor.fetchone()
    conn.close()

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    if not row:
        return {
            "version_type": "unknown",
            "confidence": 0.0,
            "tokens_found": [],
<<<<<<< HEAD
            "reason": "track not found"
        }
    
    artist, title, album, filepath = row
    
    # Build combined text for analysis
=======
            "reason": "track not found",
        }

    _artist, title, album, filepath = row

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    search_text_parts = []
    if title:
        search_text_parts.append(title)
    if album:
        search_text_parts.append(album)
    if filepath:
<<<<<<< HEAD
        # Include filename without extension
        filename = Path(filepath).stem
        search_text_parts.append(filename)
    
    search_text = " ".join(search_text_parts)
    
    # Priority order: junk > cover > live > remix > special > original
    # Junk detection (highest priority)
=======
        filename = Path(filepath).stem
        search_text_parts.append(filename)

    search_text = " ".join(search_text_parts)

    # Priority order: junk > cover > live > remix > special > original
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    has_junk, junk_matches = _detect_tokens(search_text, JUNK_TOKENS)
    if has_junk:
        return {
            "version_type": "junk",
            "confidence": min(0.7 + (len(junk_matches) * 0.1), 1.0),
            "tokens_found": junk_matches,
<<<<<<< HEAD
            "reason": f"Detected junk tokens: {', '.join(junk_matches)}"
        }
    
    # Cover detection
=======
            "reason": f"Detected junk tokens: {', '.join(junk_matches)}",
        }

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    has_cover, cover_matches = _detect_tokens(search_text, COVER_TOKENS)
    if has_cover:
        return {
            "version_type": "cover",
            "confidence": min(0.8 + (len(cover_matches) * 0.1), 1.0),
            "tokens_found": cover_matches,
<<<<<<< HEAD
            "reason": f"Detected cover tokens: {', '.join(cover_matches)}"
        }
    
    # Live detection
=======
            "reason": f"Detected cover tokens: {', '.join(cover_matches)}",
        }

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    has_live, live_matches = _detect_tokens(search_text, LIVE_TOKENS)
    if has_live:
        return {
            "version_type": "live",
            "confidence": min(0.7 + (len(live_matches) * 0.1), 1.0),
            "tokens_found": live_matches,
<<<<<<< HEAD
            "reason": f"Detected live tokens: {', '.join(live_matches)}"
        }
    
    # Remix detection
=======
            "reason": f"Detected live tokens: {', '.join(live_matches)}",
        }

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    has_remix, remix_matches = _detect_tokens(search_text, REMIX_TOKENS)
    if has_remix:
        return {
            "version_type": "remix",
            "confidence": min(0.7 + (len(remix_matches) * 0.1), 1.0),
            "tokens_found": remix_matches,
<<<<<<< HEAD
            "reason": f"Detected remix tokens: {', '.join(remix_matches)}"
        }
    
    # Special detection (extended, instrumental, etc.)
=======
            "reason": f"Detected remix tokens: {', '.join(remix_matches)}",
        }

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    has_special, special_matches = _detect_tokens(search_text, SPECIAL_TOKENS)
    if has_special:
        return {
            "version_type": "special",
            "confidence": min(0.6 + (len(special_matches) * 0.1), 0.9),
            "tokens_found": special_matches,
<<<<<<< HEAD
            "reason": f"Detected special tokens: {', '.join(special_matches)}"
        }
    
    # Default: original
=======
            "reason": f"Detected special tokens: {', '.join(special_matches)}",
        }

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    return {
        "version_type": "original",
        "confidence": 0.5,
        "tokens_found": [],
<<<<<<< HEAD
        "reason": "No special tokens detected, assuming original"
=======
        "reason": "No special tokens detected, assuming original",
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    }


def classify_and_update(track_id: str) -> Dict:
<<<<<<< HEAD
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
    
=======
    """Classify track and update database with version_type and confidence."""
    result = classify_track(track_id)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tracks
        SET version_type = ?, confidence = ?
        WHERE track_id = ?
        """,
        (result["version_type"], result["confidence"], track_id),
    )
    conn.commit()
    conn.close()

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    return result


def _llm_classify_track(artist: str, title: str, album: str, filepath: str) -> Dict:
    """Second-pass LLM classifier for ambiguous tracks.

<<<<<<< HEAD
    Called when regex gives 'original' at low confidence (0.5) — meaning no
    keywords were found, but the track could still be karaoke, tribute, or
    mislabeled. LM Studio must be running; returns None if offline.
    """
    try:
        from oracle.llm import LLMClient
=======
    Called when regex gives 'original' at low confidence (0.5) - meaning no
    keywords were found, but the track could still be karaoke, tribute, or
    mislabeled. LM Studio must be running.
    """
    try:
        from oracle.llm import LLMClient

>>>>>>> fc77b41 (Update workspace state and diagnostics)
        client = LLMClient.from_env()
        filename = Path(filepath).stem if filepath else ""
        context = f"Album: {album}" if album else ""
        if filename and filename not in title:
            context = f"{context} | File: {filename}".strip(" |")

        result = client.classify(
            artist=artist,
            title=title,
<<<<<<< HEAD
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
=======
            categories=[
                "original",
                "karaoke",
                "tribute",
                "cover",
                "remix",
                "live",
                "instrumental",
                "junk",
                "unknown",
            ],
            context=context,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "version_type": "unknown",
                "confidence": 0.0,
                "raw_category": result.get("category"),
                "tokens_found": [],
                "reason": "",
                "error": result.get("reason", "llm_unavailable"),
            }

        cat = _map_llm_category(result.get("category", "unknown"))
        confidence = float(result.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        return {
            "ok": True,
            "version_type": cat,
            "confidence": confidence,
            "raw_category": result.get("category"),
            "tokens_found": [],
            "reason": f"[LLM] {result.get('reason', '')}",
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "version_type": "unknown",
            "confidence": 0.0,
            "raw_category": None,
            "tokens_found": [],
            "reason": "",
            "error": str(exc),
        }


def _record_llm_audit(
    track_id: str,
    regex_result: Dict,
    llm_result: Dict,
    applied: bool,
) -> None:
    conn = get_connection(timeout=30.0)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO llm_audit (
            track_id,
            regex_version_type,
            regex_confidence,
            llm_version_type,
            llm_confidence,
            llm_reason,
            llm_raw_category,
            llm_ok,
            llm_applied,
            llm_error,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            regex_result.get("version_type"),
            regex_result.get("confidence"),
            llm_result.get("version_type"),
            llm_result.get("confidence"),
            llm_result.get("reason", ""),
            llm_result.get("raw_category"),
            1 if llm_result.get("ok") else 0,
            1 if applied else 0,
            llm_result.get("error", ""),
            time.time(),
        ),
    )
    conn.commit()
    conn.close()
>>>>>>> fc77b41 (Update workspace state and diagnostics)


def classify_library(limit: int = 0, use_llm: bool = False) -> Dict:
    """Classify all tracks in the library.

<<<<<<< HEAD
    Args:
        limit: Max tracks to classify (0 = all).
        use_llm: If True, use LLM as a second pass for regex-ambiguous tracks
                 (version_type='original' at confidence=0.5). Requires LM Studio.

    Returns:
        Summary dict with counts by version_type.
=======
    If use_llm is True, use LLM as a second pass for regex-ambiguous tracks
    (version_type='original' at confidence=0.5). Suggestions are only applied
    when confidence is high.
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    """
    conn = get_connection()
    cursor = conn.cursor()

    if limit > 0:
        cursor.execute(
            "SELECT track_id, artist, title, album, filepath FROM tracks LIMIT ?",
<<<<<<< HEAD
            (limit,)
=======
            (limit,),
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        )
    else:
        cursor.execute("SELECT track_id, artist, title, album, filepath FROM tracks")

    rows = cursor.fetchall()
    conn.close()

    summary: Dict = {
        "total": len(rows),
<<<<<<< HEAD
        "original": 0, "remix": 0, "live": 0, "cover": 0,
        "junk": 0, "special": 0, "unknown": 0,
        "llm_checked": 0,
=======
        "original": 0,
        "remix": 0,
        "live": 0,
        "cover": 0,
        "junk": 0,
        "special": 0,
        "unknown": 0,
        "llm_checked": 0,
        "llm_suggested": 0,
        "llm_applied": 0,
        "llm_errors": 0,
>>>>>>> fc77b41 (Update workspace state and diagnostics)
    }

    for track_id, artist, title, album, filepath in rows:
        result = classify_and_update(track_id)
<<<<<<< HEAD

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
=======
        final_result = result

        # LLM second pass for low-confidence originals only.
        if use_llm and result["version_type"] == "original" and result["confidence"] <= 0.5:
            summary["llm_checked"] += 1
            llm_result = _llm_classify_track(artist or "", title or "", album or "", filepath or "")
            applied = False

            if not llm_result.get("ok"):
                summary["llm_errors"] += 1
            elif llm_result["version_type"] != "original":
                summary["llm_suggested"] += 1
                if (
                    llm_result["version_type"] in LLM_APPLYABLE_VERSION_TYPES
                    and llm_result["confidence"] >= LLM_APPLY_CONFIDENCE_MIN
                ):
                    conn2 = get_connection()
                    conn2.execute(
                        """
                        UPDATE tracks
                        SET version_type = ?, confidence = ?, updated_at = ?
                        WHERE track_id = ?
                        """,
                        (
                            llm_result["version_type"],
                            llm_result["confidence"],
                            time.time(),
                            track_id,
                        ),
                    )
                    conn2.commit()
                    conn2.close()
                    final_result = llm_result
                    applied = True
                    summary["llm_applied"] += 1

            _record_llm_audit(track_id, result, llm_result, applied)

        version_type = final_result["version_type"]
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        summary[version_type] = summary.get(version_type, 0) + 1

    return summary


if __name__ == "__main__":
    from dotenv import load_dotenv
<<<<<<< HEAD
    load_dotenv(override=True)
    
    # Test classification
    import sys
=======

    load_dotenv(override=True)

    import sys

>>>>>>> fc77b41 (Update workspace state and diagnostics)
    if len(sys.argv) > 1:
        track_id = sys.argv[1]
        result = classify_track(track_id)
        print(f"Track {track_id}:")
        print(f"  Version Type: {result['version_type']}")
        print(f"  Confidence: {result['confidence']:.2f}")
<<<<<<< HEAD
        print(f"  Tokens: {', '.join(result['tokens_found']) if result['tokens_found'] else 'none'}")
=======
        print(
            f"  Tokens: {', '.join(result['tokens_found']) if result['tokens_found'] else 'none'}"
        )
>>>>>>> fc77b41 (Update workspace state and diagnostics)
        print(f"  Reason: {result['reason']}")
    else:
        print("Usage: python -m oracle.classifier <track_id>")

"""Tests for oracle.explainability module — Wave 17 Core Legibility."""
from __future__ import annotations

from typing import Any

import pytest

from oracle.explainability import (
    generate_explanation,
    generate_explanation_chips,
    generate_feedback_effect_description,
    generate_what_next,
    generate_why_now,
)


def _candidate(
    *,
    artist: str = "Artist",
    title: str = "Title",
    track_id: str = "t-1",
    evidence: list[dict[str, Any]] | None = None,
    provider_signals: list[dict[str, Any]] | None = None,
    confidence: float = 0.6,
    feedback_bias: float = 0.0,
    **dims: float,
) -> dict[str, Any]:
    return {
        "artist": artist,
        "title": title,
        "track_id": track_id,
        "evidence": evidence or [],
        "provider_signals": provider_signals or [],
        "confidence": confidence,
        "feedback_bias": feedback_bias,
        **dims,
    }


def _seed(
    *,
    artist: str = "Seed Artist",
    title: str = "Seed Title",
    genre: str = "",
) -> dict[str, Any]:
    return {"artist": artist, "title": title, "genre": genre}


# ── generate_explanation ────────────────────────────────────────────────────


class TestGenerateExplanation:
    def test_fallback_when_no_evidence(self) -> None:
        result = generate_explanation(_candidate())
        assert isinstance(result, str)
        assert len(result) > 5

    def test_uses_evidence_template(self) -> None:
        c = _candidate(evidence=[
            {"type": "embedding_neighbor", "source": "local", "weight": 0.8, "text": "close"},
        ])
        result = generate_explanation(c, seed_track=_seed())
        assert "Seed Artist" in result or "continuity" in result or "texture" in result.lower() or "nearby" in result.lower()

    def test_includes_dimension_flavor(self) -> None:
        c = _candidate(energy=0.9, valence=-0.5)
        result = generate_explanation(c)
        assert "high-energy" in result.lower() or "dark" in result.lower()

    def test_chaos_mode_context(self) -> None:
        result = generate_explanation(_candidate(), mode="chaos")
        assert "pivot" in result.lower() or "away" in result.lower()

    def test_safe_band_context(self) -> None:
        result = generate_explanation(_candidate(), novelty_band="safe")
        assert "familiar" in result.lower() or "close" in result.lower()

    def test_feedback_negative_evidence(self) -> None:
        c = _candidate(evidence=[
            {"type": "feedback_history", "source": "feedback", "weight": -0.5, "text": "skip"},
        ])
        result = generate_explanation(c)
        assert "skip" in result.lower() or "suppress" in result.lower() or "less" in result.lower() or "pushed" in result.lower()


# ── generate_explanation_chips ──────────────────────────────────────────────


class TestGenerateExplanationChips:
    def test_returns_list(self) -> None:
        chips = generate_explanation_chips(_candidate())
        assert isinstance(chips, list)

    def test_provider_chips(self) -> None:
        c = _candidate(provider_signals=[
            {"provider": "local", "score": 0.8, "reason": "test"},
            {"provider": "lastfm", "score": 0.4, "reason": "test"},
        ])
        chips = generate_explanation_chips(c)
        labels = [ch["label"] for ch in chips if ch["kind"] == "provider"]
        assert "local" in labels
        assert "lastfm" in labels

    def test_reason_chip(self) -> None:
        c = _candidate(evidence=[
            {"type": "scout_bridge", "source": "scout", "weight": 0.7, "text": "bridge"},
        ])
        chips = generate_explanation_chips(c)
        reason_chips = [ch for ch in chips if ch["kind"] == "reason"]
        assert any("bridge" in ch["label"].lower() for ch in reason_chips)

    def test_dimension_chip(self) -> None:
        c = _candidate(energy=0.8)
        chips = generate_explanation_chips(c)
        dim_chips = [ch for ch in chips if ch["kind"] == "dimension"]
        assert any("energy" in ch["label"].lower() for ch in dim_chips)

    def test_confidence_chip_high(self) -> None:
        c = _candidate(confidence=0.85)
        chips = generate_explanation_chips(c)
        assert any(ch["kind"] == "confidence" and "high" in ch["label"] for ch in chips)

    def test_confidence_chip_exploratory(self) -> None:
        c = _candidate(confidence=0.2)
        chips = generate_explanation_chips(c)
        assert any(ch["kind"] == "confidence" and "exploratory" in ch["label"] for ch in chips)

    def test_mode_chip_chaos(self) -> None:
        chips = generate_explanation_chips(_candidate(), mode="chaos")
        assert any(ch["kind"] == "mode" and ch["label"] == "chaos" for ch in chips)

    def test_no_mode_chip_for_flow(self) -> None:
        chips = generate_explanation_chips(_candidate(), mode="flow")
        assert not any(ch["kind"] == "mode" for ch in chips)

    def test_feedback_reinforced_chip(self) -> None:
        c = _candidate(feedback_bias=0.3)
        chips = generate_explanation_chips(c)
        assert any(ch["kind"] == "feedback" and "reinforced" in ch["label"] for ch in chips)

    def test_feedback_dampened_chip(self) -> None:
        c = _candidate(feedback_bias=-0.2)
        chips = generate_explanation_chips(c)
        assert any(ch["kind"] == "feedback" and "dampened" in ch["label"] for ch in chips)


# ── generate_why_now ────────────────────────────────────────────────────────


class TestGenerateWhyNow:
    def test_chaos_mode(self) -> None:
        result = generate_why_now(_candidate(), mode="chaos")
        assert "pivot" in result.lower()

    def test_discovery_mode(self) -> None:
        result = generate_why_now(_candidate(), mode="discovery")
        assert "discovery" in result.lower() or "surfacing" in result.lower()

    def test_same_artist_continuity(self) -> None:
        c = _candidate(artist="Radiohead")
        result = generate_why_now(c, seed_track=_seed(artist="Radiohead"))
        assert "Radiohead" in result

    def test_different_artist_transition(self) -> None:
        c = _candidate(artist="Björk")
        result = generate_why_now(c, seed_track=_seed(artist="Radiohead"))
        assert "Radiohead" in result or "transition" in result.lower()

    def test_long_queue_momentum(self) -> None:
        result = generate_why_now(
            _candidate(),
            seed_track=_seed(),
            queue_context={"length": 25},
        )
        assert "25" in result or "momentum" in result.lower()


# ── generate_what_next ──────────────────────────────────────────────────────


class TestGenerateWhatNext:
    def test_returns_up_to_three(self) -> None:
        recs = [
            _candidate(track_id=f"t-{i}", artist=f"A{i}", title=f"T{i}")
            for i in range(6)
        ]
        hints = generate_what_next(recs, current_index=0)
        assert len(hints) <= 3

    def test_hint_structure(self) -> None:
        recs = [
            _candidate(track_id="t-0"),
            _candidate(track_id="t-1", artist="NextArtist", title="NextTitle"),
        ]
        hints = generate_what_next(recs, current_index=0)
        assert len(hints) == 1
        h = hints[0]
        assert h["track_id"] == "t-1"
        assert h["artist"] == "NextArtist"
        assert h["title"] == "NextTitle"
        assert "Up next" in h["hint"]

    def test_empty_when_at_end(self) -> None:
        recs = [_candidate(track_id="t-0")]
        hints = generate_what_next(recs, current_index=0)
        assert hints == []

    def test_with_evidence_type(self) -> None:
        recs = [
            _candidate(track_id="t-0"),
            _candidate(
                track_id="t-1",
                evidence=[{"type": "scout_bridge", "weight": 0.9}],
            ),
        ]
        hints = generate_what_next(recs, current_index=0)
        assert "territory" in hints[0]["hint"].lower() or "adjacent" in hints[0]["hint"].lower()


# ── generate_feedback_effect_description ────────────────────────────────────


class TestFeedbackEffectDescription:
    def test_accepted(self) -> None:
        result = generate_feedback_effect_description(
            "accepted", track_artist="Boards of Canada", track_title="Dayvan Cowboy",
        )
        assert "Boards of Canada" in result
        assert "Dayvan Cowboy" in result

    def test_dismiss(self) -> None:
        result = generate_feedback_effect_description("dismiss")
        assert "pulling" in result.lower() or "back" in result.lower()

    def test_unknown_type_fallback(self) -> None:
        result = generate_feedback_effect_description("unknown_type")
        assert "feedback" in result.lower()

    def test_no_track_info(self) -> None:
        result = generate_feedback_effect_description("keep")
        assert isinstance(result, str)
        assert len(result) > 5

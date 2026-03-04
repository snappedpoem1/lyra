"""Structured playlist result models."""

from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel


class TrackReason(BaseModel):
    type: str
    score: float
    text: str


class PlaylistTrack(BaseModel):
    track_id: str = ""
    path: str
    artist: str
    title: str
    rank: int
    global_score: float
    reasons: List[TrackReason]


class PlaylistRun(BaseModel):
    uuid: str
    prompt: str
    created_at: datetime
    tracks: List[PlaylistTrack]

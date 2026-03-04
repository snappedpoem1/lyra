# SPEC-001: Playlist & Vibe Schema V1

## 1. Objective
Transform Lyra from a file-list generator into a 'Music Intelligence' system.
We are moving from unstructured lists to a structured 'PlaylistRun' model that supports Explainability.

## 2. The Core Concept: 'The Why'
Every track in a generated playlist must have an attached list of **Reasons**.
A 'Reason' consists of:
- 'type': (e.g., 'lyrical_match', 'bpm_transition', 'artist_affinity')
- 'score': (0.0 to 1.0 relevance)
- 'description': (Human readable text, e.g., 'Matches the energetic mood')

## 3. Database Schema Changes ('oracle/db/schema.py')

### 3.1 New Tables

#### Table: 'playlist_runs'
| Column | Type | Description |
| :--- | :--- | :--- |
| 'id' | INTEGER PK | Auto-increment ID |
| 'uuid' | TEXT | Unique run ID |
| 'prompt' | TEXT | The raw user prompt |
| 'params' | JSON | The exact search parameters used |
| 'created_at' | DATETIME | ISO timestamp |
| 'is_saved_vibe'| BOOLEAN | If true, this shows up in the 'Vibe Library' |
| 'vibe_name' | TEXT | (Optional) Name given by user |

#### Table: 'playlist_tracks'
| Column | Type | Description |
| :--- | :--- | :--- |
| 'run_id' | INTEGER | FK to 'playlist_runs.id' |
| 'track_path' | TEXT | FK to 'media.path' |
| 'rank' | INTEGER | 1-based order in the playlist |
| 'score' | FLOAT | Global relevance score |
| 'reasons' | JSON | **CRITICAL**: The structured evidence list |

## 4. Python Data Models ('oracle/types.py')

Create a new file 'oracle/types.py' to hold Pydantic models:

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TrackReason(BaseModel):
    type: str
    score: float
    text: str

class PlaylistTrack(BaseModel):
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
```

## 5. Implementation Instructions

1.  **Modify 'oracle/db/schema.py'**: Add 'playlist_runs' and 'playlist_tracks' tables.
2.  **Create 'oracle/types.py'**: Implement the Pydantic models above.
3.  **Constraint**: Do not delete 'vibe_tracks' yet.
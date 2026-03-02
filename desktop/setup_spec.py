import os

# 1. Define the directory and file path
spec_dir = os.path.join("docs", "specs")
spec_file = os.path.join(spec_dir, "SPEC-001_PLAYLIST_SCHEMA.md")

# 2. Define the content lines (safer than one giant string)
lines = [
    "# SPEC-001: Playlist & Vibe Schema V1",
    "",
    "## 1. Objective",
    "Transform Lyra from a file-list generator into a 'Music Intelligence' system.",
    "We are moving from unstructured lists to a structured 'PlaylistRun' model that supports Explainability.",
    "",
    "## 2. The Core Concept: 'The Why'",
    "Every track in a generated playlist must have an attached list of **Reasons**.",
    "A 'Reason' consists of:",
    "- 'type': (e.g., 'lyrical_match', 'bpm_transition', 'artist_affinity')",
    "- 'score': (0.0 to 1.0 relevance)",
    "- 'description': (Human readable text, e.g., 'Matches the energetic mood')",
    "",
    "## 3. Database Schema Changes ('oracle/db/schema.py')",
    "",
    "### 3.1 New Tables",
    "",
    "#### Table: 'playlist_runs'",
    "| Column | Type | Description |",
    "| :--- | :--- | :--- |",
    "| 'id' | INTEGER PK | Auto-increment ID |",
    "| 'uuid' | TEXT | Unique run ID |",
    "| 'prompt' | TEXT | The raw user prompt |",
    "| 'params' | JSON | The exact search parameters used |",
    "| 'created_at' | DATETIME | ISO timestamp |",
    "| 'is_saved_vibe'| BOOLEAN | If true, this shows up in the 'Vibe Library' |",
    "| 'vibe_name' | TEXT | (Optional) Name given by user |",
    "",
    "#### Table: 'playlist_tracks'",
    "| Column | Type | Description |",
    "| :--- | :--- | :--- |",
    "| 'run_id' | INTEGER | FK to 'playlist_runs.id' |",
    "| 'track_path' | TEXT | FK to 'media.path' |",
    "| 'rank' | INTEGER | 1-based order in the playlist |",
    "| 'score' | FLOAT | Global relevance score |",
    "| 'reasons' | JSON | **CRITICAL**: The structured evidence list |",
    "",
    "## 4. Python Data Models ('oracle/types.py')",
    "",
    "Create a new file 'oracle/types.py' to hold Pydantic models:",
    "",
    "```python",
    "from pydantic import BaseModel",
    "from typing import List, Optional",
    "from datetime import datetime",
    "",
    "class TrackReason(BaseModel):",
    "    type: str",
    "    score: float",
    "    text: str",
    "",
    "class PlaylistTrack(BaseModel):",
    "    path: str",
    "    artist: str",
    "    title: str",
    "    rank: int",
    "    global_score: float",
    "    reasons: List[TrackReason]",
    "",
    "class PlaylistRun(BaseModel):",
    "    uuid: str",
    "    prompt: str",
    "    created_at: datetime",
    "    tracks: List[PlaylistTrack]",
    "```",
    "",
    "## 5. Implementation Instructions",
    "",
    "1.  **Modify 'oracle/db/schema.py'**: Add 'playlist_runs' and 'playlist_tracks' tables.",
    "2.  **Create 'oracle/types.py'**: Implement the Pydantic models above.",
    "3.  **Constraint**: Do not delete 'vibe_tracks' yet.",
]

# 3. Write the file
try:
    os.makedirs(spec_dir, exist_ok=True)
    with open(spec_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"✅ SUCCESS: Spec written to {spec_file}")
    print("="*60)
    print("👇 COPY THIS PROMPT FOR YOUR AI 👇")
    print("="*60)
    print("I have injected a new architecture specification at `docs/specs/SPEC-001_PLAYLIST_SCHEMA.md`.")
    print("Please perform the following Core Task:")
    print("1. Read `docs/specs/SPEC-001_PLAYLIST_SCHEMA.md` carefully.")
    print("2. Create the new file `oracle/types.py` with the Pydantic models defined in Section 4.")
    print("3. Update `oracle/db/schema.py` to include the two new tables defined in Section 3.")
    print("Constraint: Do not delete the existing `vibe_tracks` table yet.")
    print("="*60)

except Exception as e:
    print(f"❌ ERROR: {e}")
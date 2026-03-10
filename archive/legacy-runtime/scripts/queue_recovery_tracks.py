"""Queue corrupt/missing album tracks for re-acquisition."""
import argparse
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from oracle.db.schema import get_connection
from datetime import datetime, timezone


def clean_title(filename: str) -> str:
    stem = re.sub(r"\.\w+$", "", filename)
    stem = re.sub(r"^\d+[-_]", "", stem)
    stem = re.sub(r"^Silverstein\s*-\s*", "", stem, flags=re.I)
    return stem.replace("_", " ").strip()


MISSING = [
    ("Circa Survive", "Juturna", ["Act Appalled", "We're All Thieves"]),
    ("Coheed and Cambria", "No World for Tomorrow", [
        "The Reaping", "No World for Tomorrow", "The Hound (of Blood and Rank)",
        "Feathers", "The Running Free", "Mother Superior",
        "Gravemakers & Gunslingers", "Justice in Murder",
        "The End Complete I: The Fall of House Atlantic",
        "The End Complete II: Radio Bye Bye",
        "The End Complete III: The Music at the End",
    ]),
    ("Sevdaliza", "Ison", ["Marilyn Monroe", "Human"]),
    ("Shai Hulud", "Hearts Once Nourished With Hope And Compassion",
     ["Outside the Boundaries of a Friend"]),
    ("Silverstein", "Discovering the Waterfront",
     ["Smile in Your Sleep", "My Heroine", "Already Dead"]),
    ("Sir Sly", "Don't You Worry, Honey", ["High", "&Run"]),
    ("Sleeping With Sirens", "Sleeping With Sirens on Audiotree Live",
     ["If I'm James Dean, You're Audrey Hepburn", "If You Can't Hang"]),
    ("Poppy", "Negative Spaces", ["new way out"]),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Queue known missing tracks for re-acquisition.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write rows to acquisition_queue. Default is dry-run.",
    )
    parser.add_argument(
        "--source",
        default="recovery",
        help="Source label written to acquisition_queue (default: recovery).",
    )
    args = parser.parse_args()

    conn = get_connection()
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    queued = 0

    for artist, album, tracks in MISSING:
        for title in tracks:
            if args.apply:
                c.execute(
                    """INSERT INTO acquisition_queue
                       (artist, title, album, source, status, added_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (artist, title, album, args.source, "pending", now),
                )
            queued += 1
            prefix = "Queued" if args.apply else "Would queue"
            print(f"  {prefix}: {artist} - {title}")

    if args.apply:
        conn.commit()
    conn.close()
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\nMode: {mode}")
    print(f"Total tracks: {queued}")


if __name__ == "__main__":
    main()

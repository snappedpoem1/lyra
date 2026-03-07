# SPEC-010 — MBID Identity Spine

**Wave:** 10  
**Session:** S-20260307-11  
**Status:** Accepted  
**Author:** Lyra Oracle  

---

## 1. Problem Statement

2,455 active tracks in `lyra_registry.db`. Of those:

| Column | Populated |
|--------|-----------|
| `recording_mbid` | 4 / 2,455 |
| `artist_mbid`    | 3 / 2,455 |
| `release_group_mbid` | 0 / 2,455 |

Without MBIDs, the following subsystems are degraded or broken:

- **Credits** (`track_credits`): `CreditMapper.map_batch()` references `tracks.musicbrainz_id` (column does not exist) and the fuzzy fallback `map_batch_search` returns 0 credits for most tracks because production relations are only available via MBID lookup.
- **Release context** / **artwork**: no `release_group_mbid` means no Cover Art Archive lookups.
- **Canonical bio enrichment**: `validate_artist()` and `get_release_groups()` already exist but are called on-demand only; no batch coverage.

---

## 2. Goals

1. Populate `recording_mbid`, `artist_mbid`, `release_mbid`, `release_group_mbid`, `isrc` for every active track.
2. Fix `CreditMapper.map_batch()` to reference `recording_mbid` (not the nonexistent `musicbrainz_id`).
3. After MBID population, `CreditMapper.map_batch()` produces real credits for all matched tracks.
4. Provide `oracle mbid resolve` / `oracle mbid stats` CLI commands.

**Non-goals:**

- Cover Art Archive download (later — additive).
- Live-orbit (setlist.fm / Ticketmaster) — never mandatory.
- Acoustic fingerprinting (AcoustID) — Wave 12+.

---

## 3. Data Model

No schema migration required. All target columns already exist on `tracks`:

```sql
recording_mbid      TEXT
artist_mbid         TEXT
release_mbid        TEXT
release_group_mbid  TEXT
isrc                TEXT
last_enriched_at    REAL   -- unix timestamp, set on every write
```

`enrich_cache` table also exists and will be used for caching MB lookups with a 30-day TTL.

---

## 4. New Module: `oracle/enrichers/mb_identity.py`

### 4.1 `MBIdentityResolver`

```
class MBIdentityResolver:
    resolve_batch(limit, min_confidence, only_missing) → ResolveResult
    stats() → MBIDStats
```

**`resolve_batch` algorithm:**

1. Query `tracks` for rows where `recording_mbid IS NULL OR recording_mbid = ''` (when `only_missing=True`), ordered by `last_played DESC NULLS LAST` (most-played first = highest value first).
2. For each track: call `enrich_by_text(artist, title, album, duration)` — already rate-limited to 1.1s/req by `musicbrainz.py`.
3. If `RecordingMatch.confidence >= min_confidence`:
   - Write `recording_mbid`, `artist_mbid`, `isrc`, `last_enriched_at` to `tracks`.
   - If `release_group_mbid` is available from the match, write it too.
   - Cache the `RecordingMatch` in `enrich_cache` with key `mb_text:{track_id}` and TTL 30 days.
4. If no match: write `last_enriched_at` anyway so we don't retry too soon (prevents hammering MB on unresolvable tracks); log a warning.
5. Return `ResolveResult(resolved, skipped, no_match, failed, total_eligible)`.

**Rate limiting:**  
`enrich_by_text()` already enforces `MB_MIN_INTERVAL_SECONDS` (1.1s). No additional sleep needed.

**Resume-safety:**  
`only_missing=True` means runs are idempotent — already-resolved tracks are skipped. Can be killed and resumed.

### 4.2 `MBIDStats`

```python
@dataclass
class MBIDStats:
    total_active: int
    recording_mbid_count: int
    artist_mbid_count: int
    release_group_mbid_count: int
    isrc_count: int
    coverage_pct: float   # recording_mbid / total_active * 100
```

---

## 5. Fix: `oracle/enrichers/credit_mapper.py`

`CreditMapper.map_batch()` references `tracks.musicbrainz_id` — this column does not exist. Fix:

- Replace all `musicbrainz_id` references with `recording_mbid` in `map_batch()`.

No other changes to `CreditMapper`.

---

## 6. CLI Interface

New top-level command `mbid` with two subcommands:

```
oracle mbid resolve [--limit N] [--min-confidence F] [--all]
oracle mbid stats
```

| Argument | Default | Notes |
|----------|---------|-------|
| `--limit N` | 100 | Max tracks per run |
| `--min-confidence F` | 0.65 | RecordingMatch.confidence threshold |
| `--all` | off | Re-resolve even already-resolved tracks |

Output example:

```
MBID Resolve Pass
  Total eligible : 2451
  Resolved       : 98
  No match       : 2
  Skipped        : 0
  Failed         : 0
```

`oracle mbid stats` prints the `MBIDStats` table.

---

## 7. Tests

File: `tests/test_mb_identity.py`

| Test | Description |
|------|-------------|
| `test_resolve_batch_writes_mbids` | Happy path: `enrich_by_text` mocked → resolver writes all 4 MBID columns |
| `test_resolve_batch_skips_existing` | `only_missing=True`: tracks with `recording_mbid` already set are skipped |
| `test_resolve_batch_handles_no_match` | `enrich_by_text` returns `None` → no_match counter incremented, `last_enriched_at` written |
| `test_resolve_batch_handles_exception` | `enrich_by_text` raises → failed counter incremented, continues |
| `test_stats_returns_correct_counts` | Inserts known rows, asserts `MBIDStats` fields |

---

## 8. Execution Plan

1. Write spec ✓ (this document)
2. Implement `oracle/enrichers/mb_identity.py`
3. Fix `credit_mapper.map_batch()` column reference
4. Wire `oracle mbid` CLI commands in `oracle/cli.py`
5. Write `tests/test_mb_identity.py` — run `python -m pytest -q`
6. Run `oracle mbid resolve --limit 500` (≈10 min wall-clock at 1.1s/req)
7. Run `oracle credits enrich --limit 200` — should now produce real credits
8. Update `docs/PROJECT_STATE.md`, `docs/MISSING_FEATURES_REGISTRY.md`, session log
9. Commit `[S-20260307-11] feat: Wave 10 MBID identity spine`

---

## 9. Acceptance Criteria

- [ ] `python -m pytest -q` passes (≥ 188 tests)
- [ ] `oracle mbid stats` shows `recording_mbid_count > 0` after a resolve pass
- [ ] `CreditMapper.map_batch()` no longer raises on missing `musicbrainz_id` column
- [ ] `oracle credits enrich --limit 10` returns non-zero credits for resolved tracks
- [ ] `docs/PROJECT_STATE.md` updated with new MBID coverage numbers

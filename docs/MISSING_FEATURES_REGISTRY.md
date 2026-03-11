# Lyra Gap Registry

Last audited: March 10, 2026 (updated same session)

This file tracks the backend and product gaps that still keep Lyra from matching its intended identity.

## Active Gap Matrix

| ID | Area | Status | Implemented Now | Missing Or Partial | Legacy Sources To Inspect Next |
| --- | --- | --- | --- | --- | --- |
| G-060 | Native acquisition parity | partial, active | Rust owns canonical acquisition planning for single tracks, albums, and discographies; persisted plan state; queue lifecycle tracking; missing-world lead handoff; and canonical junk rejection before persistence. The legacy Python bridge is quarantined behind explicit opt-in. | Native end-to-end acquisition execution and validator/ingest-confidence parity are still incomplete; the optional migration bridge still exists for fallback/migration use | `archive/legacy-runtime/oracle/acquisition.py`, `archive/legacy-runtime/oracle/acquirers/waterfall.py`, `archive/legacy-runtime/oracle/acquirers/validator.py` |
| G-066 | Provider auth and transport autonomy | partial, active | Provider config, provider validation, backend cache/retry transport, backend-owned Spotify auth bootstrap/exchange, and backend-owned Spotify session persistence/refresh exist in Rust | Cross-provider auth proof remains uneven, and Spotify still needs broader packaged/runtime proof beyond local tests | `archive/legacy-runtime/oracle/provider_contract.py`, `archive/legacy-runtime/oracle/api/auth.py`, `archive/legacy-runtime/lyra_api.py` |
| G-064 | Discovery graph and bridge depth | partial, active | Rust backend supports local graph/co-play/shared-genre routes, scout exits, bridge/discovery route variants, ListenBrainz weather, non-local acquisition leads, and a curated lineage/member/offshoot baseline. `artist_intelligence.rs` now provides a MusicBrainz relationship ingestor: resolves library artists to MBIDs, fetches member-of/subgroup/influence edges, persists verified rows into `artist_lineage_edges`. | MB ingestion pipeline exists and is wired to `LyraCore`; library-wide ingestion run still pending. Verified edges are not yet feeding into bridge/discovery routes at query time. | `archive/legacy-runtime/oracle/graph_builder.py`, `archive/legacy-runtime/oracle/scout.py`, `archive/legacy-runtime/oracle/lore.py` |
| G-063 | Composer and playlist intelligence depth | partial, active | Prompt-to-draft, bridge, discovery, steer, explain, route memory, and structured reason payloads exist in Rust. `track_audio_features.rs` now provides pure-Rust audio analysis: lofty tag reads for BPM/key, rodio/symphonia PCM decode for RMS energy, peak, dynamic range, and energy volatility. Schema in `track_audio_features` table. | Audio extraction pipeline is wired to `LyraCore`; library-wide run is still pending. Composer evidence layer is not yet consuming `track_audio_features` rows to upgrade vibe claims from heuristic to PCM-backed. | `archive/legacy-runtime/oracle/playlust.py`, `archive/legacy-runtime/oracle/arc.py`, `archive/legacy-runtime/oracle/mood_interpreter.py`, `archive/legacy-runtime/oracle/vibes.py` |
| G-061 | Explainability and provenance breadth | partial, active | `explain_track`, recommendation payloads, and acquisition leads now emit structured evidence items with evidence categories, anchors, and overall evidence grades | Explainability is still uneven across backend surfaces; provenance/evidence language is much stronger in broker/explain flows but not yet universal | `archive/legacy-runtime/oracle/explain.py`, `archive/legacy-runtime/oracle/explainability.py`, `archive/legacy-runtime/oracle/enrichers/unified.py` |
| G-062 | Curation workflows | largely complete | Duplicate review, keeper selection, quarantine, cleanup preview, and undo depth are present in the canonical runtime | Deeper file-system repair workflows remain intentionally out of scope for now | `archive/legacy-runtime/oracle/duplicates.py`, `archive/legacy-runtime/oracle/curator.py`, `archive/legacy-runtime/oracle/organizer.py` |
| G-065 | Packaged desktop confidence | partial | The backend now has an isolated app-data runtime proof plus a focused verification script (`scripts/backend_runtime_confidence.ps1`) in addition to the existing dev-environment tests | Clean-machine packaged validation and long-session soak proof are still missing | packaged validation scripts and soak artifacts |

## Execution Order

1. `G-060` Native acquisition parity
2. `G-066` Provider auth and transport autonomy
3. `G-064` Discovery graph and bridge depth
4. `G-063` Composer and playlist intelligence depth
5. `G-061` Explainability and provenance breadth
6. `G-065` Packaged desktop confidence

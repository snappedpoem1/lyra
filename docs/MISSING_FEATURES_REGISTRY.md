# Lyra Gap Registry

Last audited: March 8, 2026

This file tracks active gaps only.

## Active Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-060 | Acquisition workflow parity | partial | Lifecycle UI/controls and preflight are now in place, but lifecycle transitions are still best-effort because acquisition phases are delegated to Python waterfall subprocesses | Emit authoritative structured stage events from waterfall (or port pipeline to Rust) so UI progress is source-of-truth |
| G-061 | Enrichment provenance and confidence | partial | Enrichment providers run and panels exist, but source confidence and MBID-first identity views are not consistently surfaced | Add confidence/provenance payloads to commands and render them in Library/Artist views |
| G-062 | Curation workflows | partial | Duplicate detection exists, but no canonical review/apply workflow for duplicate resolution, naming cleanup preview, or rollback metadata | Implement curation plan surfaces and safe apply/rollback flow |
| G-063 | Playlist intelligence parity | partial | Recommendations + AI playlist seed are present, but act-based playlist generation and persisted reason payloads are not restored to canonical runtime | Add run-based generation with track-level reason persistence and explainability UI |
| G-064 | Discovery graph depth | partial | Artist profile and simple local connections exist, but play-similar/bridge and richer graph-driven discovery modes are still missing | Add graph-backed related artist actions and deeper discovery modes |
| G-065 | Packaged desktop confidence | partial | Local checks pass, but installer and long-session proof remain open for latest workflow additions | Run packaged build + blank-machine installer + soak after workflow parity hardens |

## Execution Order

1. Acquisition workflow parity (G-060)
2. Enrichment provenance and MBID-first surfaces (G-061)
3. Curation workflow implementation (G-062)
4. Playlist intelligence parity (G-063)
5. Discovery graph depth (G-064)
6. Packaged validation and soak (G-065)

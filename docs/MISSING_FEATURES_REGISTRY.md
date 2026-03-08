# Lyra Gap Registry

Last audited: March 8, 2026

This file tracks active gaps only.

## Active Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-050 | Rust playback backend | partial | Command-complete playback surface exists in Rust, but wave 1 currently uses an honest playback stub instead of production-grade audio output | Implement a real Rust audio backend and keep the current command contract stable |
| G-051 | Scan/import metadata depth | partial | Library root persistence and first-pass scan/import are live, but metadata extraction is still shallow and duration detection is not yet robust | Add richer file metadata parsing, duration detection, and normalization |
| G-052 | Playlist editing depth | partial | Playlist creation, detail, and queue-from-playlist are live, but editing and sequencing actions are still minimal | Add add/remove/reorder flows and queue-to-playlist actions |
| G-053 | Provider migration depth | partial | Supported `.env` provider keys are imported into Rust-owned provider config records, but provider validation and secure secret handling are still minimal | Add provider-specific validation, protection strategy, and first live Rust provider adapters |
| G-054 | Enrichment/oracle migration | partial | Rust-owned acquisition, enrichment, and oracle contracts now exist architecturally, but runtime parity with legacy Python systems is not yet implemented | Port selected enrichers and recommendation/oracle flows into Rust-owned modules |
| G-055 | Packaged desktop confidence | partial | Rust core, SvelteKit frontend, and Tauri host build locally, but packaged installer validation and long-session hardening remain open | Run packaged desktop build validation and installer smoke once playback is hardened |

## Execution Order

1. Replace the playback stub with real Rust audio.
2. Improve scan/import quality and playlist editing.
3. Expand provider migration quality and secret handling.
4. Port selected enrichment and oracle features.
5. Reopen packaged desktop validation once runtime behavior stabilizes.

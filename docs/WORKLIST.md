# Worklist

Last updated: March 10, 2026

## Execution Rule

Prioritize backend work that makes Lyra feel like a music-intelligence system, not just a competent local player.
Do not let UI polish or shell work outrun backend truth.

Use `docs/BACKEND_ACCEPTANCE_MATRIX.md` as the backend release gate.

## Priority Order

1. `G-060` Native acquisition parity
2. `G-066` Provider auth and transport autonomy
3. `G-064` Discovery graph and bridge depth
4. `G-063` Composer and playlist intelligence depth
5. `G-061` Explainability and provenance breadth
6. `G-065` Packaged desktop confidence

## Active Lane

### Backend Truth Hardening

- [x] Audit backend truth against the current Lyra/Cassette product promise
- [x] Create `docs/BACKEND_ACCEPTANCE_MATRIX.md`
- [x] Add backend verification for canonical junk rejection
- [x] Add backend verification for Spotify session persistence/refresh without UI dependency
- [x] Add backend verification for prompt-to-playlist draft generation from backend state
- [x] Add backend verification for evidence-bearing graph explainability
- [x] Add backend verification that EDM-drop prompts do not overclaim current capability
- [x] Add backend verification for provider transport cache fallback
- [x] Quarantine the legacy Python acquisition bridge so the canonical backend path is Rust-first
- [x] Add first-class album/discography acquisition planning with canonical release filtering
- [x] Add canonical Spotify authorization-code exchange and session bootstrap
- [x] Add a first lineage/member/offshoot backend baseline and use it in route and explanation logic
- [ ] Add deeper audio-feature-backed evidence for strong vibe claims
- [x] Add isolated app-data backend runtime confidence proof
- [ ] Run packaged clean-machine and long-session backend confidence proof

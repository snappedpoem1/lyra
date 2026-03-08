# Lyra Gap Registry

Last audited: March 8, 2026

This file tracks active product gaps only.

## Gap Framing

The most important open gaps are not generic player bugs.
They are the missing or incomplete differentiators that should make Lyra feel like a self-owned music intelligence and curation system.

Each gap below distinguishes between:

- missing in the canonical runtime
- partially implemented in Python but not yet ported
- implemented at a low level but not yet surfaced clearly in the canonical UI

## Active Gap Matrix

| ID | Area | Status | Evidence | What Needs To Happen |
| --- | --- | --- | --- | --- |
| G-070 | Explainable intelligence | partial | Canonical Rust/Svelte surfaces expose limited recommendation reasons, but the broader reasoning and feedback-effect model described in Python recommendation/explainability logic is not yet ported or surfaced consistently | Port and surface richer reason chains, evidence payloads, and user-visible "why this surfaced" explanations |
| G-071 | Playlist authorship and narrative generation | partial | Canonical app can save and build playlists, but authored act/narrative generation with durable reason payloads is not yet a first-class workflow. Python contains richer vibe/playlust/explain flows | Port playlist-generation logic with persisted reason payloads and explicit authored-journey UI |
| G-072 | Graph and constellation discovery | partial | Canonical app has artist and recommendation surfaces, but graph-backed exploration, bridge workflows, and constellation-style navigation remain thin. Python contains graph builder, scout, and broker discovery behavior | Port graph/discovery process logic and expose graph-aware discovery actions in the native UI |
| G-073 | Visible scoring, provenance, and confidence | partial | Some enrichment and taste signals exist in Rust, but provenance/confidence are not consistently visible and dimensional scoring is not yet a cohesive user-facing system. Python contains scorer, provider evidence, and enriched process logic | Normalize confidence/provenance contracts in Rust and expose score context wherever it materially affects decisions |
| G-074 | Taste memory and session memory | partial | Canonical runtime has early taste profile support, but deeper memory, backfill, and steering logic remain incomplete. Python contains richer taste update, backfill, worker, and recommendation feedback behavior | Port taste/session memory logic and make recommendation steering visible to the user |
| G-075 | Curation and stewardship workflows | partial | Canonical runtime supports library and playlist basics, but safe duplicate resolution, cleanup preview/apply, and rollback-aware curation are not yet fully restored. Python contains duplicates/curator/organizer behavior | Port curation workflows with fidelity to existing process semantics |
| G-076 | Acquisition and ingest intelligence depth | partial | Canonical acquisition exists, but prioritization, ingest confidence, and solved workflow behavior from Python are not yet fully represented. Python still contains meaningful waterfall, guard, validator, and prioritization logic | Port the missing acquisition and ingest process behaviors instead of keeping only a thin queue UI |
| G-077 | Packaging and long-session confidence | partial | Native runtime is materially functional, but clean-machine installer proof and long-session validation remain open | Complete packaged validation and soak testing without letting this eclipse identity-feature work |

## Integration And Config Reality

Feature work is not blocked by a blank configuration story.
The repo already has:

- repo-root `.env` loading on Python surfaces
- Rust `.env` import into `provider_configs`
- provider capability metadata in Rust
- provider validation hooks in Rust
- OS keyring support in Rust

Future agents should treat provider/config plumbing as existing infrastructure to reuse and normalize, not as a future prerequisite.

## Execution Order

1. Explainable intelligence
2. Playlist authorship and narrative generation
3. Graph and constellation discovery
4. Visible scoring, provenance, and confidence
5. Taste memory and session memory
6. Curation workflows
7. Acquisition and ingest depth
8. Packaging and long-session confidence

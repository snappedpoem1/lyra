# Lyra Roadmap

Last updated: March 8, 2026

## Mission Lock

Lyra is a vibe-to-journey music intelligence, discovery, and curation platform with native playback.

The native runtime is real.
The roadmap now exists to deepen Lyra identity, not to keep re-proving that a desktop shell can play audio.

Canonical runtime:

- Tauri 2 desktop shell
- SvelteKit frontend
- Rust application core
- SQLite local store

## Decision Lock

1. No Python in canonical startup, playback, queue, library, or settings flow.
2. No localhost backend dependency.
3. Rust owns runtime state, DB, retrieval, sequencing, provider config, and native integration.
4. SvelteKit owns the active UI layer.
5. LLMs may help parse and explain intent, but deterministic retrieval and sequencing stay local.
6. Legacy Python intelligence must be mined before replacing product behavior.

## Current Milestone

The first real composer pipeline is landed in the canonical runtime:

- typed `PlaylistIntent`
- local/cloud LLM provider abstraction
- deterministic local reranking and sequencing
- visible phases and provider mode in the UI
- persisted reason payloads

This is the start of the intelligence contract, not the end state.

## Forward Roadmap

### Wave 1 - Composer Depth

- broaden prompt handling beyond playlist drafting
- add richer refinement loops
- deepen local semantic retrieval and bridge scoring

### Wave 2 - Discovery And Bridge Intelligence

- bridge-track prompts
- adjacency exploration with explanation
- shared composer/discovery reasoning surfaces

### Wave 3 - Explainability Breadth

- inferred-vs-explicit reasoning visibility
- durable reason payloads across more product surfaces
- honest provider/degraded-state visibility

### Wave 4 - Taste Steering

- user steer and feedback loops that actually affect future output
- visible taste memory and session-memory controls

### Wave 5 - Infrastructure Follow-Through

- remaining acquisition runtime hardening
- curation workflows
- packaged desktop confidence

Infrastructure still matters, but it is no longer the message of the roadmap.

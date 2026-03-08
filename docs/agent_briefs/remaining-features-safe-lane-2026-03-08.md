# Remaining Features Safe Lane

Date: 2026-03-08
Session: `S-20260308-03`
Role: parallel lane owner
Status: active

## Duty Set

This lane is responsible for:

- isolated acquisition modules in `crates/lyra-core/src/acquisition.rs`
- isolated Discover-route work in `desktop/renderer-app/src/routes/discover/*`
- coordination notes for cross-agent file ownership

## Owned Files

- `crates/lyra-core/src/acquisition.rs`
- `desktop/renderer-app/src/routes/discover/+page.svelte`
- `desktop/renderer-app/src/routes/discover/*`
- `docs/agent_briefs/remaining-features-safe-lane-2026-03-08.md`
- `docs/sessions/2026-03-08-isolated-remaining-features.md`

## Forbidden Files

- `crates/lyra-core/src/commands.rs`
- `crates/lyra-core/src/enrichment.rs`
- `crates/lyra-core/src/lib.rs`
- `crates/lyra-core/src/providers.rs`
- `desktop/renderer-app/src-tauri/src/main.rs`
- `desktop/renderer-app/src/lib/tauri.ts`
- `desktop/renderer-app/src/lib/types.ts`
- `desktop/renderer-app/src/routes/library/+page.svelte`
- `desktop/renderer-app/src/routes/settings/+page.svelte`
- `docs/PROJECT_STATE.md`
- `docs/WORKLIST.md`

## Delivered So Far

- acquisition queue summary state primitives in `acquisition.rs`
- acquisition source breakdown primitives in `acquisition.rs`
- acquisition summary tests in `acquisition.rs`

## Integration Note

If another agent later exposes acquisition dashboard commands or UI, they should consume the new queue summary and source-breakdown helpers from `acquisition.rs` rather than re-deriving this state in shared files.

# Session Log - S-20260307-17

**Date:** 2026-03-07
**Goal:** Fix real parity acceptance runner robustness bugs and validate the acceptance lane
**Agent(s):** GitHub Copilot / Claude Code / Codex / Manual

---

## Context

The parity hardening acceptance runner was being used as the main runtime stability proof, but review of the current script found three real robustness bugs:

- child PowerShell scripts were invoked without checking `$LASTEXITCODE`, so the parent runner could continue after a failed build or failed smoke gate
- playback reactivation in the soak path used a fixed sleep instead of waiting for a real `"playing"` state transition
- sidecar startup inherited stale `LYRA_DATA_ROOT` / `LYRA_USE_LEGACY_DATA_ROOT` environment values and only stopped a pre-existing listener when `/api/health` was already healthy

The goal of this session was to harden the acceptance runner itself without crossing into broader active-wave implementation work.

---

## Work Done

Bullet list of completed work:

- [x] Added `Invoke-CheckedPowerShellScript` to make child script failures fatal in the parity acceptance runner.
- [x] Changed playback reactivation to wait for `Wait-PlayerStatus -Statuses @("playing")` instead of sleeping and assuming success.
- [x] Cleared inherited `LYRA_DATA_ROOT` and `LYRA_USE_LEGACY_DATA_ROOT` before sidecar launch, then reapplied only the explicit flags for the current run.
- [x] Added `Stop-ExistingBackendListener` so any process still holding port `5000` is stopped before deterministic sidecar startup, even if `/api/health` is unhealthy.
- [x] Re-ran a bounded parity acceptance pass and confirmed smoke, restart recovery, SSE validation, and soak mutations all passed.

---

## Commits

| SHA (short) | Message |
|---|---|
| `-` | `No commit yet (local changes only)` |

---

## Key Files Changed

- `scripts/parity_hardening_acceptance.ps1` - hardened child-script execution, playback transition waiting, listener cleanup, and sidecar env isolation.
- `docs/SESSION_INDEX.md` - added the session row for this hardening pass.
- `docs/sessions/2026-03-07-parity-runner-hardening.md` - recorded the scoped runner fixes and validation.

---

## Result

Yes. The parity acceptance runner now fails fast when prerequisite child scripts fail, waits on real playback state transitions during soak mutations, and starts the sidecar under deterministic port and data-root conditions. A bounded validation run succeeded after the changes.

---

## State Updates Made

- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/WORKLIST.md` updated
- [ ] `docs/MISSING_FEATURES_REGISTRY.md` updated (if applicable)
- [x] `docs/SESSION_INDEX.md` row added
- [x] Tests pass: `powershell -ExecutionPolicy Bypass -File scripts\parity_hardening_acceptance.ps1 -SkipSidecarBuild -SkipInstallerProof -UseLegacyDataRoot -SoakSeconds 20 -CheckpointIntervalSeconds 10 -ActionIntervalSeconds 8 -StartupTimeoutSeconds 90`

---

## Next Action

Use the hardened runner for the longer parity soak when the release-gate lane resumes, or keep fixing only similarly isolated acceptance-lane issues.


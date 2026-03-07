# Build and Release Brief

Date: 2026-03-06
Wave: 2

This lane is now locally implemented in session `S-20260306-23`.

## Implemented Scope

- Electron archival
- CI/release-gate automation
- build manifest and reproducibility guidance
- packaged host and installed-layout validation governance

## Guardrails

- do not rewrite runtime/data-root behavior in this lane
- do not absorb product/UI depth work here

## Required Validation

- Windows-first CI PR checks
- renderer `npm run test:ci` in CI to avoid watch-mode hangs
- packaged host smoke
- installed-layout validation
- build manifest generation
- docs updates for any build-authority changes

## Session Obligations

- open a dedicated session
- update roadmap/state/worklist/registry if build authority or release-gate truth changes

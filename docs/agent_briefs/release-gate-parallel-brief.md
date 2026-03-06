# Release-Gate Parallel Brief

Date: 2026-03-06
Session: S-20260306-12

Use this brief for a second agent while the main line continues on packaged/runtime proof.

## Objective 1: Clean-Machine Packaged Proof

Verify Lyra launches and functions on a separate Windows machine or clean VM without relying on host-global installs.

What to verify:

- packaged host launches
- bundled `lyra_backend.exe` starts automatically
- bundled `streamrip`, `spotdl`, `ffmpeg`, and `ffprobe` are discoverable
- backend health becomes `ok`
- basic playback shell opens without Docker dependency

Suggested commands:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\packaged_host_smoke.ps1 -RebuildHost
python -m oracle doctor
```

Deliverables:

- exact machine/VM environment
- pass/fail for first launch
- screenshots of first launch if failure occurs
- failing paths or missing runtime assets
- any stderr, popup, or health-check error text

## Objective 2: Packaged Streamrip Acquisition Proof

Run one real packaged/runtime-backed tier-2 acquisition and capture the full result.

What to verify:

- request enters `acquisition_queue`
- tier-2 `streamrip` is selected or reached
- audio file materializes on disk
- ingest/reintegration marks the queue row correctly

Useful evidence to collect:

- artist/title/album tested
- queue row status before and after
- resolved bundled `rip.exe` path
- resulting file path
- whether ingest watcher marked completion

## Constraints

- do not delete `lyra_registry.db`
- do not wipe `chroma_storage/`
- do not perform destructive migrations
- do not change core architecture while validating

## Expected Output

Provide a short report with:

1. environment
2. commands run
3. result
4. exact blockers
5. recommended next fix if something failed

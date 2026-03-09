# Archive

This directory contains tracked historical artifacts that are not part of Lyra's active
canonical runtime.

## Layout

- `historical-docs/` - historical reports and one-off documentation.
- `legacy-runtime/` - legacy Python/runtime scripts, historical data exports, and prior runtime bundles.
- `legacy-ops/` - non-canonical operational infrastructure kept for reference.
- `legacy-archive/` - prior archive snapshots preserved as tracked history.

## Policy

- Legacy and historical human-readable files stay tracked here.
- `.gitignore` is reserved for environment secrets, caches, and machine-generated noise.
- Active canonical runtime remains in:
  - `crates/`
  - `desktop/`
  - `docs/`
  - `scripts/`

# Prowlarr Config Template (Safe)

This folder is a **template** for a local Prowlarr runtime config.

✅ Committed to Git:
- Only safe placeholders
- No API keys
- No machine-specific runtime state

❌ NOT committed to Git:
- `Lyra_Oracle_System/config/prowlarr/` (runtime folder)
- databases, logs, keys, pid files

## How to use
If you need a bootstrap, copy this template folder to:
`Lyra_Oracle_System/config/prowlarr/`

Example (Git Bash):
cp -r "Lyra_Oracle_System/config/prowlarr.template" "Lyra_Oracle_System/config/prowlarr"

Then restart Prowlarr and configure via UI.

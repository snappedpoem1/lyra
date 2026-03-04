# Worklist

Last updated: March 4, 2026

This file is the short operational list of what is done and what still needs work.

## To Done

- Documentation stack rewritten around audited repo reality.
- Historical exports, prototype notes, and old workspace material distilled into reference docs.
- README replaced with a cleaner current-project description.
- `.claude` memory and agent reference files synchronized to one source-of-truth order.
- Legacy roadmap and planning files marked as historical.
- VS Code workspace auto-start added for Docker-backed services on folder open.
- Dead `prowlarr` and `lidarr` image pins removed from `docker-compose.yml`.
- Desktop text search rewired to `/api/search` instead of vibe generation.
- Desktop command palette rewired to `/api/agent/query` instead of a hardcoded stub.
- Constellation fixture masking removed for normal runtime; fixture fallback now only happens in explicit fixture mode.
- Home, Oracle, and playlist detail routes now surface constellation backend failures instead of hiding them.
- Flask runtime now attempts to auto-start the BeefWeb playback bridge when the API starts and BeefWeb is reachable.

## To Do

- Verify real playback ingestion with foobar2000 + BeefWeb and confirm `playback_history` starts filling.
- Decide whether command-palette agent responses should trigger app-side actions, not just display backend intent.
- Deepen graph edge types so constellation and discovery have richer cultural context.
- Clean up duplicate or legacy containers such as `lyra_node` and `lyra_transport`.
- Decide whether runtime artifacts should remain in-repo or move to a dedicated runtime root.

## Blocked Or External

- Playback ingestion cannot be proven complete without a live foobar2000 + BeefWeb session.
- Some acquisition/runtime validation still depends on whichever Docker services and credentials are active on the machine at the time.

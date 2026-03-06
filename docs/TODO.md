# TODO

Last reset: March 5, 2026 (after gap-closure sweep)

Fresh operational TODO list. Resolved items were removed so this file can
capture only new findings and forgotten features from this point forward.

## Now

- [ ] Install/configure streamrip CLI (`rip`) and verify one successful tier-2 waterfall acquisition.
- [ ] Continue `python -m oracle structure analyze --limit 50` batches until `track_structure` coverage is materially useful.
- [ ] Keep running `python -m oracle credits enrich --limit 30` until shrine credit depth is meaningfully populated.

## Next

- [ ] Continue staged similarity builds with safe worker settings:
  `python -m oracle graph similarity-edges --limit-artists 500 --top-k 20 --workers 2 --request-pause 0.20 --commit-every 400`
- [ ] Improve Spotify-history to local-track fuzzy matching and re-run playlist parity checks.
- [ ] Run explicit foobar2000 + BeefWeb live-session proof and capture before/after `playback_history`.

## Decisions

- [ ] Decide Spotify export scope (`ship` vs `cancel`) and document decision.
- [ ] Decide runtime/source separation migration plan and target directory contract.

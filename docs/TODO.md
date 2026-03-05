# TODO

Last updated: March 5, 2026

Operational TODO list ordered easy to hard.

## Now

- [ ] Install `librosa` in the active runtime and re-run `python -m oracle structure analyze --limit 50`.
- [ ] Keep running `python -m oracle credits enrich --limit 30` until shrine credit coverage is meaningful.
- [ ] Continue staged similarity builds with safe worker settings:
  `python -m oracle graph similarity-edges --limit-artists 500 --top-k 20 --workers 2 --request-pause 0.20 --commit-every 400`

## Next

- [ ] Debug why ListenBrainz discovery currently inserts `0` queue rows (`source='listenbrainz_community'`).
- [ ] Improve Spotify-history to local-track fuzzy matching and re-run playlist parity checks.
- [ ] Run explicit foobar2000 + BeefWeb live-session proof and capture before/after `playback_history`.

## Decisions

- [ ] Decide Spotify export scope (`ship` vs `cancel`) and document decision.
- [ ] Decide runtime/source separation migration plan and target directory contract.

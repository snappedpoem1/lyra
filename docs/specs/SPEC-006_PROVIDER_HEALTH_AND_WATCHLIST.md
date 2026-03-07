# SPEC-006: Provider Health, Diagnostics, and Upstream Watchlist

## 1. Objective

Create a lightweight contract for provider health visibility and upstream-break awareness so recommendation/data-source integrations do not silently rot.

This spec complements `SPEC-004` and is intentionally docs/diagnostics-first.

## 2. Provider Health Contract

Each provider should expose a health summary with:

- `provider`
- `enabled`
- `status`
- `last_success_at`
- `last_error_at`
- `last_error_summary`
- `rate_limit_state` when relevant
- `cache_state` when relevant

Status values:

- `healthy`
- `degraded`
- `unavailable`
- `disabled`

## 3. Diagnostics Exposure

Provider health must be available to:

- backend diagnostics output
- doctor/status tooling where appropriate
- later renderer/system diagnostics panels

Do not bury provider-health truth only in logs.

## 4. Upstream Watchlist

Maintain a repo watchlist doc or section for upstream risk sources:

- Spotify policy and endpoint restrictions
- MusicBrainz API/rate-limit or schema changes
- ListenBrainz recommendation/playlist/core API changes
- Cover Art Archive availability/rate-limit behavior
- setlist.fm API-key and response-shape changes

Each watchlist item should track:

- provider/source
- why it matters to Lyra
- current integration use
- risk level
- last reviewed date

## 5. Alerting and Logging Rules

- Provider failures should emit structured logs with provider key and summary.
- Repeated degraded states should be visible in diagnostics, not just one-off exceptions.
- Silent fallback to weaker providers must still leave a visible degraded summary in broker output.

## 6. Non-Goals

- This spec does not require external monitoring infrastructure.
- This spec does not require paging/alerting services.
- This spec does not force network calls from diagnostics if cached health is sufficient.

## 7. Validation

Required checks:

1. Healthy provider state is visible.
2. Degraded provider state is visible after simulated timeout or empty-response fallback.
3. Doctor/system diagnostics can surface at least summary provider health later without changing the contract again.
4. Watchlist documentation exists and is easy to update.

## 8. Acceptance Criteria

This spec is satisfied when Lyra has one documented contract for provider health/degradation visibility and one maintained upstream watchlist process for high-risk external dependencies.

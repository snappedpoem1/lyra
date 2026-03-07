# SPEC-005: UI Provenance and Degraded-State Surfaces

## 1. Objective

Expose recommendation provenance, confidence, and degraded-provider state directly in the UI so Lyra feels explainable instead of magical.

This spec is for the later product-surface wave and depends on the provider/evidence payload defined in `SPEC-004`.

## 2. Required Surfaces

The first required provenance surfaces are:

- Oracle route
- Unified workspace Oracle pane
- playlist detail route
- right-rail/detail surfaces
- now-playing insight surface

## 3. Required UI Elements

Each recommendation card or surfaced recommendation row must support:

- provider/source chips
- confidence band or confidence label
- plain-language “why this” summary
- degraded/failure state indicator when provider coverage is weak
- expandable technical trace/details view

## 4. Plain-Language Copy Rules

The default visible explanation must:

- be short
- be grounded in real evidence
- not invent unsupported claims
- favor one or two strongest signals instead of dumping all evidence

Examples:

- “Similar listener cluster and strong local embedding fit.”
- “Shared work lineage and release-group proximity.”
- “Community-popular around this thread, but local confidence is moderate.”

## 5. Degraded-State Rules

If providers are degraded or unavailable, the UI must not silently flatten the output.

Required degraded states:

- provider unavailable
- provider reachable but empty
- local resolution weak
- broker narrowed to fallback providers only

These states must be renderable from API output alone.

## 6. Interaction Rules

- Default cards stay compact.
- Technical trace/details remain collapsed by default.
- Provider chips should be visible without opening a details view.
- Degraded-state warnings must be visible before the user acts on the recommendation.

## 7. Non-Goals

- This spec does not redesign all route layouts.
- This spec does not require a new global panel.
- This spec does not permit detached aesthetic changes with no explainability value.

## 8. Validation

Required checks:

1. Provider chips render for local-only recommendations.
2. Mixed-provider recommendations show merged provenance correctly.
3. Degraded states are visible when provider reports are degraded or failed.
4. Plain-language rationale matches the underlying evidence payload.
5. Renderer tests/build and docs checks pass.

## 9. Acceptance Criteria

This spec is satisfied when the key recommendation surfaces can render provenance, confidence, and degraded-state signals directly from the broker contract without ad hoc UI inference.

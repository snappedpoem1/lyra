# Workflow Needs (Legacy Parity)

Last updated: March 8, 2026

This document captures workflow behaviors still expected from legacy Python/ChatGPT planning artifacts and maps them to canonical Rust/Tauri/Svelte implementation needs.

## Acquisition Workflow

1. End-to-end staged ingest loop:
- acquire -> stage -> scan/import -> organize -> index must be visible in UI with per-item progress and errors
2. Queue controls:
- retry failed, clear completed, and optional prioritization bands
3. Safety checks:
- disk-space preflight and downloader/tool availability checks before processing

## Enrichment Workflow

1. Explicit enrichment lifecycle:
- initial enrich, refresh/force enrich, and source-level status visibility per track
2. MBID identity spine completion:
- promote `artist_mbid` and `recording_mbid` to first-class fields in artist/track views
3. Confidence display:
- show enrichment confidence and source provenance in UI

## Curation Workflow

1. Duplicate handling workflow:
- cluster review -> choose keeper -> quarantine/delete duplicates
2. Filename/path cleanup workflow:
- preview changes before apply, with operation summary
3. Organization plans:
- dry-run curation plan with rollback metadata

## Playlist Intelligence Workflow

1. Act/narrative playlist generation:
- generate by intent with explicit phases/acts and track-level reasons
2. Explainability:
- persist and display "why this track is here" reason payloads
3. Save/apply:
- convert generated runs into saved playlists and queue actions directly

## Artist/Discovery Workflow

1. Artist graph:
- related-artist edges should be inspectable and actionable ("play similar", "queue bridge")
2. Discovery modes:
- recommendations, deep cuts, and community weather should expose mode + source provenance
3. Session memory:
- recent interactions should feed next recommendations and be visible to user


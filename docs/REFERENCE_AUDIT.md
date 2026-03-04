# External Reference Audit

Last audited: March 4, 2026

This document records the types of historical reference material that informed the project audit and how they should be used.

It intentionally avoids listing personal machine paths or detailed archive inventories that do not need to live in a public repo.

## Source Types Reviewed

### Conversation Archives

Historical conversation archives included notes, attached markdowns, playlist experiments, planning material, and related working files.

Usefulness:

- product language
- playlist methodology
- project-history recovery
- older design intent

Do not use as:

- proof of current implementation status
- proof that a feature is finished

### Historical Prototype Workspaces

Earlier project workspaces contained Spotify-derived data, experiments, and prototype-era scripts.

Usefulness:

- historical data provenance
- earlier design and implementation experiments
- clues about abandoned or merged directions

Do not use as:

- the current repo source of truth

### Downloaded Data And Tooling Artifacts

Downloaded archives and installers provided evidence of:

- Spotify export source material
- playback-related tooling
- dependency breadcrumbs

Usefulness:

- runtime dependency context
- provenance for imported data and workflows

Do not use as:

- the repo's active runtime state
- proof that a dependency is fully integrated

## How These Sources Map To The Current Repo

### Playlist Methodology Material

What it tells us:

- the emotional-arc and curated-playlist direction predates the current repo implementation

How it maps now:

- Playlust and playlist explainability are implemented in the repo
- the historical material is useful for future quality tuning, not for completion claims

### Spotify Export Material

What it tells us:

- there is substantial Spotify listening-history and library data available

How it maps now:

- Spotify history and library data are useful for taste seeding and gap analysis
- export back out to Spotify is still a separate unfinished capability

### Old Phase Docs And Earlier READMEs

What they tell us:

- earlier docs often described intended or earlier states of the project

How they map now:

- some align with current code
- some overclaim completion
- some are simply old and should stay historical

## Source Of Truth Policy

When sources disagree, use this order:

1. current repo code
2. current local data
3. current memory files
4. audited docs in `docs/`
5. historical references

## Documentation Consequence

Historical materials remain valuable as:

- design memory
- methodology references
- data provenance
- dependency breadcrumbs

They should not be treated as implementation truth without code confirmation.

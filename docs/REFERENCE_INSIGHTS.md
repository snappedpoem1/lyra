# Reference-Derived Insights

Last distilled: March 4, 2026

This document converts useful historical material into project information.

It is intentionally written as information, not file archaeology.

## 1. Playlist Methodology

The strongest recurring idea across the historical references is that Lyra's playlist system should not act like a plain result bucket. It should act like authored movement through an emotional and cultural space.

The most consistent structure is a four-act arc:

1. Aggressive
2. Seductive
3. Breakdown
4. Sublime

Useful implications for the current project:

- playlists should have narrative shape, not just relevance ranking
- transitions matter as much as individual tracks
- deep cuts and side paths matter more than obvious hits
- cross-genre bridge tracks are part of the design, not noise in the results
- per-track reasoning is a core differentiator, not decoration

This directly supports the existing direction in [`oracle/playlust.py`](../archive/legacy-runtime/oracle/playlust.py), [`oracle/explain.py`](../archive/legacy-runtime/oracle/explain.py), and the playlist persistence schema.

## 2. Product Principles

The most useful product-level ideas from the references are:

- playlist-first, not dashboard-first
- local-library ownership should feel sacred and inspectable
- now-playing should feel ceremonial, not incidental
- search should feel like excavation, not generic filtering
- recommendation quality should be visible through reasoning, not hidden behind magic
- metadata should serve story and control, not just administration

These principles are still useful for guiding frontend and API decisions.

## 3. Search And Discovery Lessons

Historical research materials strongly favored:

- deep-cut discovery over obvious-chart retrieval
- adjacent-artist exploration over same-genre repetition
- taste-aware pivots rather than generic similarity
- scene, influence, and collaboration context

Useful consequence for the current repo:

- the graph should become richer in edge types
- deep cut results should be easier to surface in the UI
- search and discovery should share a more coherent mental model

## 4. Vibes System Lessons

Older implementation notes around vibes are still useful in a few ways:

- save -> build -> materialize -> refresh is a good lifecycle
- materialized playlists are valuable because they turn semantic curation into owned filesystem artifacts
- playlist files and folder views are not just export features; they are part of the ownership story

This still aligns with the current repo even though the newer system has moved beyond the older phase framing.

## 5. Acquisition Lessons

Old acquisition documents are useful mostly as design background:

- queue-driven processing is the right shape
- staging and validation steps matter
- acquisition is only useful when it reintegrates into search, indexing, and curation

Useful consequence for current work:

- acquisition docs should describe the live waterfall and reintegration path, not just source connectors

## 6. Enrichment Lessons

Older enrichment materials consistently emphasized:

- MusicBrainz for canonical identity
- AcoustID for verification when tags are weak
- Last.fm for tags and popularity context
- Genius for lyric/context surfaces

Useful consequence for current work:

- enrichment should be documented as layered confidence, not one perfect source
- artist context quality should be described honestly as source-dependent

## 7. Spotify Data Provenance

Historical materials make it clear that Spotify exports are an important source of taste and collection context.

Useful current interpretations:

- Spotify history is a taste-seeding source
- Spotify library/export data is useful for gap analysis and acquisition targeting
- Spotify export back out from Lyra is still a separate capability and should not be assumed complete

## 8. Frontend Direction Lessons

The most useful archived frontend guidance can be summarized as:

- avoid turning Lyra into a generic music dashboard
- do not let backend module names become the user-facing information architecture
- center the experience around playlist detail, queue, search, oracle pivots, and now playing
- support mood, ritual, and explainability without burying control

Useful consequence for the current desktop app:

- remove silent fixture masking from flagship routes
- make the real interaction loop clearer
- keep the interface focused on listening, curation, and discovery

## 9. What To Forget

Some reference material is useful only as history and should not shape current truth claims:

- old "phase complete" language
- older READMEs that claim broad completion
- prototype-era assumptions about the web UI being the main product surface
- any document that marks implemented repo features as missing without a code check

## 10. Working Rule

Use external references for:

- methodology
- product tone
- historical intent
- data provenance

Do not use them alone for:

- implementation status
- feature completion claims
- current architecture truth
- current runtime state

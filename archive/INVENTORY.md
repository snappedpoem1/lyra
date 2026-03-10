# Archive Inventory

Generated: 2026-03-09 20:21:16 -04:00

## Scope
- Commit `dad2a3f` `[S-20260309-05] refactor: normalize root and archive legacy artifacts`
- Commit `fa0d377` `[S-20260309-05] refactor: archive all legacy python surfaces`

## Current Archive Layout
- Total files under `archive/` (tracked + pending): 242
- `archive/(archive-root)`: 2 files
- `archive/historical-docs`: 1 files
- `archive/legacy-archive`: 1 files
- `archive/legacy-ops`: 7 files
- `archive/legacy-runtime`: 231 files

## Legacy Markdown Files In Archive
- `archive/historical-docs/FEATURE_TEST_REPORT.md`
- `archive/INVENTORY.md`
- `archive/legacy-runtime/Lyra_Oracle_System/config/prowlarr.template/README.md`
- `archive/legacy-runtime/oracle/AGENTS.md`
- `archive/README.md`

## Python Files Outside Archive
- None (`*.py` files are fully segregated into `archive/`).

## Move Manifest (What Was -> What Is)
```text
R100	FEATURE_TEST_REPORT.md	archive/historical-docs/FEATURE_TEST_REPORT.md
R100	docker-compose.yml	archive/legacy-ops/docker-compose.yml
R100	docker/essentia/Dockerfile	archive/legacy-ops/docker/essentia/Dockerfile
R100	docker/essentia/requirements.txt	archive/legacy-ops/docker/essentia/requirements.txt
R100	docker/essentia/service.py	archive/legacy-ops/docker/essentia/service.py
R100	docker/qobuz/Dockerfile	archive/legacy-ops/docker/qobuz/Dockerfile
R100	docker/qobuz/requirements.txt	archive/legacy-ops/docker/qobuz/requirements.txt
R100	docker/qobuz/service.py	archive/legacy-ops/docker/qobuz/service.py
R100	Lyra_Oracle_System/config/prowlarr.template/.gitkeep	archive/legacy-runtime/Lyra_Oracle_System/config/prowlarr.template/.gitkeep
R100	Lyra_Oracle_System/config/prowlarr.template/README.md	archive/legacy-runtime/Lyra_Oracle_System/config/prowlarr.template/README.md
R100	Lyra_Oracle_System/config/prowlarr.template/config.example.xml	archive/legacy-runtime/Lyra_Oracle_System/config/prowlarr.template/config.example.xml
R100	Spotify Extended Streaming History/ReadMeFirst_ExtendedStreamingHistory.pdf	archive/legacy-runtime/Spotify Extended Streaming History/ReadMeFirst_ExtendedStreamingHistory.pdf
R100	Spotify Extended Streaming History/Streaming_History_Audio_2021-2022_1.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2021-2022_1.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2021_0.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2021_0.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2022-2023_3.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2022-2023_3.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2022_2.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2022_2.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2023-2024_4.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2023-2024_4.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2024-2025_6.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2024-2025_6.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2024_5.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2024_5.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2025-2026_8.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2025-2026_8.json
R100	Spotify Extended Streaming History/Streaming_History_Audio_2025_7.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Audio_2025_7.json
R100	Spotify Extended Streaming History/Streaming_History_Video_2021-2026.json	archive/legacy-runtime/Spotify Extended Streaming History/Streaming_History_Video_2021-2026.json
R100	_drain_loop.sh	archive/legacy-runtime/_drain_loop.sh
R100	boot_oracle.bat	archive/legacy-runtime/boot_oracle.bat
R100	boot_oracle.py	archive/legacy-runtime/boot_oracle.py
R100	oracle.bat	archive/legacy-runtime/oracle.bat
R100	pytest.ini	archive/legacy-runtime/pytest.ini
R100	requirements-full.txt	archive/legacy-runtime/requirements-full.txt
R100	requirements.txt	archive/legacy-runtime/requirements.txt
R100	setup_spec_002.py	archive/legacy-runtime/setup_spec_002.py
R100	spotify_import.py	archive/legacy-runtime/spotify_import.py
R100	desktop/setup_spec.py	archive/legacy-runtime/desktop/setup_spec.py
R100	lyra_api.py	archive/legacy-runtime/lyra_api.py
R100	oracle/AGENTS.md	archive/legacy-runtime/oracle/AGENTS.md
R100	oracle/__init__.py	archive/legacy-runtime/oracle/__init__.py
R100	oracle/__main__.py	archive/legacy-runtime/oracle/__main__.py
R100	oracle/acquirers/__init__.py	archive/legacy-runtime/oracle/acquirers/__init__.py
R100	oracle/acquirers/bootstrap_status.py	archive/legacy-runtime/oracle/acquirers/bootstrap_status.py
R100	oracle/acquirers/guard.py	archive/legacy-runtime/oracle/acquirers/guard.py
R100	oracle/acquirers/guarded_import.py	archive/legacy-runtime/oracle/acquirers/guarded_import.py
R100	oracle/acquirers/magnet_sources.py	archive/legacy-runtime/oracle/acquirers/magnet_sources.py
R100	oracle/acquirers/qobuz.py	archive/legacy-runtime/oracle/acquirers/qobuz.py
R100	oracle/acquirers/realdebrid.py	archive/legacy-runtime/oracle/acquirers/realdebrid.py
R100	oracle/acquirers/smart_pipeline.py	archive/legacy-runtime/oracle/acquirers/smart_pipeline.py
R100	oracle/acquirers/spotdl.py	archive/legacy-runtime/oracle/acquirers/spotdl.py
R100	oracle/acquirers/streamrip.py	archive/legacy-runtime/oracle/acquirers/streamrip.py
R100	oracle/acquirers/taste_prioritizer.py	archive/legacy-runtime/oracle/acquirers/taste_prioritizer.py
R100	oracle/acquirers/validator.py	archive/legacy-runtime/oracle/acquirers/validator.py
R100	oracle/acquirers/waterfall.py	archive/legacy-runtime/oracle/acquirers/waterfall.py
R100	oracle/acquirers/ytdlp.py	archive/legacy-runtime/oracle/acquirers/ytdlp.py
R100	oracle/acquisition.py	archive/legacy-runtime/oracle/acquisition.py
R100	oracle/agent.py	archive/legacy-runtime/oracle/agent.py
R100	oracle/anchors.py	archive/legacy-runtime/oracle/anchors.py
R100	oracle/api/__init__.py	archive/legacy-runtime/oracle/api/__init__.py
R100	oracle/api/app.py	archive/legacy-runtime/oracle/api/app.py
R100	oracle/api/auth.py	archive/legacy-runtime/oracle/api/auth.py
R100	oracle/api/blueprints/__init__.py	archive/legacy-runtime/oracle/api/blueprints/__init__.py
R100	oracle/api/blueprints/acquire.py	archive/legacy-runtime/oracle/api/blueprints/acquire.py
R100	oracle/api/blueprints/agent.py	archive/legacy-runtime/oracle/api/blueprints/agent.py
R100	oracle/api/blueprints/companion.py	archive/legacy-runtime/oracle/api/blueprints/companion.py
R100	oracle/api/blueprints/core.py	archive/legacy-runtime/oracle/api/blueprints/core.py
R100	oracle/api/blueprints/discovery.py	archive/legacy-runtime/oracle/api/blueprints/discovery.py
R100	oracle/api/blueprints/enrich.py	archive/legacy-runtime/oracle/api/blueprints/enrich.py
R100	oracle/api/blueprints/horizon.py	archive/legacy-runtime/oracle/api/blueprints/horizon.py
R100	oracle/api/blueprints/ingest.py	archive/legacy-runtime/oracle/api/blueprints/ingest.py
R100	oracle/api/blueprints/intelligence.py	archive/legacy-runtime/oracle/api/blueprints/intelligence.py
R100	oracle/api/blueprints/library.py	archive/legacy-runtime/oracle/api/blueprints/library.py
R100	oracle/api/blueprints/oracle_actions.py	archive/legacy-runtime/oracle/api/blueprints/oracle_actions.py
R100	oracle/api/blueprints/pipeline.py	archive/legacy-runtime/oracle/api/blueprints/pipeline.py
R100	oracle/api/blueprints/player.py	archive/legacy-runtime/oracle/api/blueprints/player.py
R100	oracle/api/blueprints/playlists.py	archive/legacy-runtime/oracle/api/blueprints/playlists.py
R100	oracle/api/blueprints/radio.py	archive/legacy-runtime/oracle/api/blueprints/radio.py
R100	oracle/api/blueprints/recommendations.py	archive/legacy-runtime/oracle/api/blueprints/recommendations.py
R100	oracle/api/blueprints/search.py	archive/legacy-runtime/oracle/api/blueprints/search.py
R100	oracle/api/blueprints/vibes.py	archive/legacy-runtime/oracle/api/blueprints/vibes.py
R100	oracle/api/cors.py	archive/legacy-runtime/oracle/api/cors.py
R100	oracle/api/helpers.py	archive/legacy-runtime/oracle/api/helpers.py
R100	oracle/api/registry.py	archive/legacy-runtime/oracle/api/registry.py
R100	oracle/api/scheduler.py	archive/legacy-runtime/oracle/api/scheduler.py
R100	oracle/arc.py	archive/legacy-runtime/oracle/arc.py
R100	oracle/architect.py	archive/legacy-runtime/oracle/architect.py
R100	oracle/audit.py	archive/legacy-runtime/oracle/audit.py
R100	oracle/bootstrap.py	archive/legacy-runtime/oracle/bootstrap.py
R100	oracle/catalog.py	archive/legacy-runtime/oracle/catalog.py
R100	oracle/chroma_store.py	archive/legacy-runtime/oracle/chroma_store.py
R100	oracle/classifier.py	archive/legacy-runtime/oracle/classifier.py
R100	oracle/cli.py	archive/legacy-runtime/oracle/cli.py
R100	oracle/companion/__init__.py	archive/legacy-runtime/oracle/companion/__init__.py
R100	oracle/companion/pulse.py	archive/legacy-runtime/oracle/companion/pulse.py
R100	oracle/config.py	archive/legacy-runtime/oracle/config.py
R100	oracle/curator.py	archive/legacy-runtime/oracle/curator.py
R100	oracle/data_root_migration.py	archive/legacy-runtime/oracle/data_root_migration.py
R100	oracle/db/__init__.py	archive/legacy-runtime/oracle/db/__init__.py
R100	oracle/db/migrations/002_god_mode.py	archive/legacy-runtime/oracle/db/migrations/002_god_mode.py
R100	oracle/db/migrations/__init__.py	archive/legacy-runtime/oracle/db/migrations/__init__.py
R100	oracle/db/schema.py	archive/legacy-runtime/oracle/db/schema.py
R100	oracle/deepcut.py	archive/legacy-runtime/oracle/deepcut.py
R100	oracle/dna.py	archive/legacy-runtime/oracle/dna.py
R100	oracle/doctor.py	archive/legacy-runtime/oracle/doctor.py
R100	oracle/download_processor.py	archive/legacy-runtime/oracle/download_processor.py
R100	oracle/duplicates.py	archive/legacy-runtime/oracle/duplicates.py
R100	oracle/embedders/__init__.py	archive/legacy-runtime/oracle/embedders/__init__.py
R100	oracle/embedders/clap_embedder.py	archive/legacy-runtime/oracle/embedders/clap_embedder.py
R100	oracle/enrichers/__init__.py	archive/legacy-runtime/oracle/enrichers/__init__.py
R100	oracle/enrichers/acoustid.py	archive/legacy-runtime/oracle/enrichers/acoustid.py
R100	oracle/enrichers/biographer.py	archive/legacy-runtime/oracle/enrichers/biographer.py
R100	oracle/enrichers/cache.py	archive/legacy-runtime/oracle/enrichers/cache.py
R100	oracle/enrichers/credit_mapper.py	archive/legacy-runtime/oracle/enrichers/credit_mapper.py
R100	oracle/enrichers/discogs.py	archive/legacy-runtime/oracle/enrichers/discogs.py
R100	oracle/enrichers/essentia.py	archive/legacy-runtime/oracle/enrichers/essentia.py
R100	oracle/enrichers/genius.py	archive/legacy-runtime/oracle/enrichers/genius.py
R100	oracle/enrichers/lastfm.py	archive/legacy-runtime/oracle/enrichers/lastfm.py
R100	oracle/enrichers/mb_identity.py	archive/legacy-runtime/oracle/enrichers/mb_identity.py
R100	oracle/enrichers/musicbrainz.py	archive/legacy-runtime/oracle/enrichers/musicbrainz.py
R100	oracle/enrichers/musicnn.py	archive/legacy-runtime/oracle/enrichers/musicnn.py
R100	oracle/enrichers/unified.py	archive/legacy-runtime/oracle/enrichers/unified.py
R100	oracle/explain.py	archive/legacy-runtime/oracle/explain.py
R100	oracle/explainability.py	archive/legacy-runtime/oracle/explainability.py
R100	oracle/fast_batch.py	archive/legacy-runtime/oracle/fast_batch.py
R100	oracle/graph_builder.py	archive/legacy-runtime/oracle/graph_builder.py
R100	oracle/horizon/__init__.py	archive/legacy-runtime/oracle/horizon/__init__.py
R100	oracle/horizon/prowlarr_releases.py	archive/legacy-runtime/oracle/horizon/prowlarr_releases.py
R100	oracle/horizon/prowlarr_setup.py	archive/legacy-runtime/oracle/horizon/prowlarr_setup.py
R100	oracle/hunter.py	archive/legacy-runtime/oracle/hunter.py
R100	oracle/importers/__init__.py	archive/legacy-runtime/oracle/importers/__init__.py
R100	oracle/indexer.py	archive/legacy-runtime/oracle/indexer.py
R100	oracle/ingest_confidence.py	archive/legacy-runtime/oracle/ingest_confidence.py
R100	oracle/ingest_watcher.py	archive/legacy-runtime/oracle/ingest_watcher.py
R100	oracle/integrations/__init__.py	archive/legacy-runtime/oracle/integrations/__init__.py
R100	oracle/integrations/beefweb_bridge.py	archive/legacy-runtime/oracle/integrations/beefweb_bridge.py
R100	oracle/integrations/beets_import.py	archive/legacy-runtime/oracle/integrations/beets_import.py
R100	oracle/integrations/lastfm_history.py	archive/legacy-runtime/oracle/integrations/lastfm_history.py
R100	oracle/integrations/listenbrainz.py	archive/legacy-runtime/oracle/integrations/listenbrainz.py
R100	oracle/llm.py	archive/legacy-runtime/oracle/llm.py
R100	oracle/llm_config.py	archive/legacy-runtime/oracle/llm_config.py
R100	oracle/lore.py	archive/legacy-runtime/oracle/lore.py
R100	oracle/lyra_protocol.py	archive/legacy-runtime/oracle/lyra_protocol.py
R100	oracle/mood_interpreter.py	archive/legacy-runtime/oracle/mood_interpreter.py
R100	oracle/name_cleaner.py	archive/legacy-runtime/oracle/name_cleaner.py
R100	oracle/normalizer.py	archive/legacy-runtime/oracle/normalizer.py
R100	oracle/ops.py	archive/legacy-runtime/oracle/ops.py
R100	oracle/organizer.py	archive/legacy-runtime/oracle/organizer.py
R100	oracle/perf.py	archive/legacy-runtime/oracle/perf.py
R100	oracle/pipeline.py	archive/legacy-runtime/oracle/pipeline.py
R100	oracle/player/__init__.py	archive/legacy-runtime/oracle/player/__init__.py
R100	oracle/player/audio_engine.py	archive/legacy-runtime/oracle/player/audio_engine.py
R100	oracle/player/events.py	archive/legacy-runtime/oracle/player/events.py
R100	oracle/player/repository.py	archive/legacy-runtime/oracle/player/repository.py
R100	oracle/player/service.py	archive/legacy-runtime/oracle/player/service.py
R100	oracle/playlust.py	archive/legacy-runtime/oracle/playlust.py
R100	oracle/provider_contract.py	archive/legacy-runtime/oracle/provider_contract.py
R100	oracle/provider_health.py	archive/legacy-runtime/oracle/provider_health.py
R100	oracle/radio.py	archive/legacy-runtime/oracle/radio.py
R100	oracle/recommendation_broker.py	archive/legacy-runtime/oracle/recommendation_broker.py
R100	oracle/repair.py	archive/legacy-runtime/oracle/repair.py
R100	oracle/runtime_services.py	archive/legacy-runtime/oracle/runtime_services.py
R100	oracle/runtime_state.py	archive/legacy-runtime/oracle/runtime_state.py
R100	oracle/scanner.py	archive/legacy-runtime/oracle/scanner.py
R100	oracle/scorer.py	archive/legacy-runtime/oracle/scorer.py
R100	oracle/scout.py	archive/legacy-runtime/oracle/scout.py
R100	oracle/search.py	archive/legacy-runtime/oracle/search.py
R100	oracle/status.py	archive/legacy-runtime/oracle/status.py
R100	oracle/taste.py	archive/legacy-runtime/oracle/taste.py
R100	oracle/taste_backfill.py	archive/legacy-runtime/oracle/taste_backfill.py
R100	oracle/types.py	archive/legacy-runtime/oracle/types.py
R100	oracle/validation.py	archive/legacy-runtime/oracle/validation.py
R100	oracle/vibe_descriptors.py	archive/legacy-runtime/oracle/vibe_descriptors.py
R100	oracle/vibes.py	archive/legacy-runtime/oracle/vibes.py
R100	oracle/worker.py	archive/legacy-runtime/oracle/worker.py
R100	scripts/analyze_playlist_export.py	archive/legacy-runtime/scripts/analyze_playlist_export.py
R100	scripts/check_errors.py	archive/legacy-runtime/scripts/check_errors.py
R100	scripts/check_health.py	archive/legacy-runtime/scripts/check_health.py
R100	scripts/cleanup_library.py	archive/legacy-runtime/scripts/cleanup_library.py
R100	scripts/diagnose_quality.py	archive/legacy-runtime/scripts/diagnose_quality.py
R100	scripts/diagnose_search.py	archive/legacy-runtime/scripts/diagnose_search.py
R100	scripts/diagnose_tiers.py	archive/legacy-runtime/scripts/diagnose_tiers.py
R100	scripts/enrich_genres.py	archive/legacy-runtime/scripts/enrich_genres.py
R100	scripts/fast_dedupe.py	archive/legacy-runtime/scripts/fast_dedupe.py
R100	scripts/fix_fstrings.py	archive/legacy-runtime/scripts/fix_fstrings.py
R100	scripts/fix_zeroed_tracks.py	archive/legacy-runtime/scripts/fix_zeroed_tracks.py
R100	scripts/flush_tracks_db.py	archive/legacy-runtime/scripts/flush_tracks_db.py
R100	scripts/library_clean.py	archive/legacy-runtime/scripts/library_clean.py
R100	scripts/list_artists.py	archive/legacy-runtime/scripts/list_artists.py
R100	scripts/queue_recovery_tracks.py	archive/legacy-runtime/scripts/queue_recovery_tracks.py
R100	scripts/runtime_tool_entrypoints/spotdl_runtime.py	archive/legacy-runtime/scripts/spotdl_runtime.py
R100	scripts/runtime_tool_entrypoints/streamrip_runtime.py	archive/legacy-runtime/scripts/streamrip_runtime.py
R100	scripts/xray_tags.py	archive/legacy-runtime/scripts/xray_tags.py
R100	tests/test_acquire_batch.py	archive/legacy-runtime/tests-python/test_acquire_batch.py
R100	tests/test_acquisition_guard_path.py	archive/legacy-runtime/tests-python/test_acquisition_guard_path.py
R100	tests/test_agent_engine_alias.py	archive/legacy-runtime/tests-python/test_agent_engine_alias.py
R100	tests/test_api_cors.py	archive/legacy-runtime/tests-python/test_api_cors.py
R100	tests/test_api_prewarm.py	archive/legacy-runtime/tests-python/test_api_prewarm.py
R100	tests/test_audio_engine_miniaudio.py	archive/legacy-runtime/tests-python/test_audio_engine_miniaudio.py
R100	tests/test_clap_embedder_audio_loading.py	archive/legacy-runtime/tests-python/test_clap_embedder_audio_loading.py
R100	tests/test_clap_embedder_runtime.py	archive/legacy-runtime/tests-python/test_clap_embedder_runtime.py
R100	tests/test_companion_pulse.py	archive/legacy-runtime/tests-python/test_companion_pulse.py
R100	tests/test_config_data_root.py	archive/legacy-runtime/tests-python/test_config_data_root.py
R100	tests/test_config_schema_contract.py	archive/legacy-runtime/tests-python/test_config_schema_contract.py
R100	tests/test_data_root_migration.py	archive/legacy-runtime/tests-python/test_data_root_migration.py
R100	tests/test_doctor.py	archive/legacy-runtime/tests-python/test_doctor.py
R100	tests/test_duplicates.py	archive/legacy-runtime/tests-python/test_duplicates.py
R100	tests/test_explainability.py	archive/legacy-runtime/tests-python/test_explainability.py
R100	tests/test_genius_provider.py	archive/legacy-runtime/tests-python/test_genius_provider.py
R100	tests/test_guard_junk_patterns.py	archive/legacy-runtime/tests-python/test_guard_junk_patterns.py
R100	tests/test_import_integrity.py	archive/legacy-runtime/tests-python/test_import_integrity.py
R100	tests/test_ingest_confidence.py	archive/legacy-runtime/tests-python/test_ingest_confidence.py
R100	tests/test_ingest_watcher_queue_resolution.py	archive/legacy-runtime/tests-python/test_ingest_watcher_queue_resolution.py
R100	tests/test_lastfm_provider.py	archive/legacy-runtime/tests-python/test_lastfm_provider.py
R100	tests/test_listenbrainz_parser.py	archive/legacy-runtime/tests-python/test_listenbrainz_parser.py
R100	tests/test_llm_config.py	archive/legacy-runtime/tests-python/test_llm_config.py
R100	tests/test_lyra_api_contract.py	archive/legacy-runtime/tests-python/test_lyra_api_contract.py
R100	tests/test_mb_identity.py	archive/legacy-runtime/tests-python/test_mb_identity.py
R100	tests/test_musicbrainz_provider.py	archive/legacy-runtime/tests-python/test_musicbrainz_provider.py
R100	tests/test_musicnn_provider.py	archive/legacy-runtime/tests-python/test_musicnn_provider.py
R100	tests/test_oracle_actions_contract.py	archive/legacy-runtime/tests-python/test_oracle_actions_contract.py
R100	tests/test_pipeline_wrapper.py	archive/legacy-runtime/tests-python/test_pipeline_wrapper.py
R100	tests/test_player_api_contract.py	archive/legacy-runtime/tests-python/test_player_api_contract.py
R100	tests/test_player_service.py	archive/legacy-runtime/tests-python/test_player_service.py
R100	tests/test_playlists_contract.py	archive/legacy-runtime/tests-python/test_playlists_contract.py
R100	tests/test_playlust_cache_schema.py	archive/legacy-runtime/tests-python/test_playlust_cache_schema.py
R100	tests/test_provider_contract.py	archive/legacy-runtime/tests-python/test_provider_contract.py
R100	tests/test_radio_semantic_fallback.py	archive/legacy-runtime/tests-python/test_radio_semantic_fallback.py
R100	tests/test_recommendation_broker_contract.py	archive/legacy-runtime/tests-python/test_recommendation_broker_contract.py
R100	tests/test_remix_search.py	archive/legacy-runtime/tests-python/test_remix_search.py
R100	tests/test_revelations.py	archive/legacy-runtime/tests-python/test_revelations.py
R100	tests/test_runtime_data_root_api.py	archive/legacy-runtime/tests-python/test_runtime_data_root_api.py
R100	tests/test_runtime_services_policy.py	archive/legacy-runtime/tests-python/test_runtime_services_policy.py
R100	tests/test_runtime_state.py	archive/legacy-runtime/tests-python/test_runtime_state.py
R100	tests/test_scheduler_lock.py	archive/legacy-runtime/tests-python/test_scheduler_lock.py
R100	tests/test_schema_idempotence.py	archive/legacy-runtime/tests-python/test_schema_idempotence.py
R100	tests/test_scorer_dimensions.py	archive/legacy-runtime/tests-python/test_scorer_dimensions.py
R100	tests/test_scout_weather.py	archive/legacy-runtime/tests-python/test_scout_weather.py
R100	tests/test_search_fallback.py	archive/legacy-runtime/tests-python/test_search_fallback.py
R100	tests/test_search_rewrite.py	archive/legacy-runtime/tests-python/test_search_rewrite.py
R100	tests/test_smart_pipeline_queue.py	archive/legacy-runtime/tests-python/test_smart_pipeline_queue.py
R100	tests/test_spotify_import_endpoint.py	archive/legacy-runtime/tests-python/test_spotify_import_endpoint.py
R100	tests/test_streamrip.py	archive/legacy-runtime/tests-python/test_streamrip.py
R100	tests/test_vibe_bridge.py	archive/legacy-runtime/tests-python/test_vibe_bridge.py
R100	tests/test_waterfall_guard.py	archive/legacy-runtime/tests-python/test_waterfall_guard.py
```

## Archive Files Added Directly (No Prior Path)
```text
A	archive/README.md
A	archive/legacy-archive/_archive/downloader.py
```

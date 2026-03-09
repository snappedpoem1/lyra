use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use rusqlite::{params, Connection, OptionalExtension};
use serde_json::{json, Value};
use tracing::{info, warn};

use crate::commands::{
    AdjacencySignal, BridgePath, BridgeStep, ComposedPlaylistDraft, ComposedPlaylistTrack,
    ComposerAction, ComposerProviderStatus, ComposerResponse, ConfidenceVoice, DetailDepth,
    DiscoveryDirection, DiscoveryRoute, FallbackVoice, GeneratedPlaylist, LyraFraming,
    LyraReadSurface, PlaylistIntent, PlaylistIntentState, PlaylistPhase, PlaylistTrackWithReason,
    ResponsePosture, RouteComparison, RouteVariantSummary, SettingsPayload, SteerPayload,
    TasteMemorySnapshot, TasteProfile, TrackReasonPayload, TrackRecord,
};
use crate::errors::{LyraError, LyraResult};
use crate::llm_client::{LlmClient, LlmEndpointConfig};
use crate::oracle;
use crate::playlists;
use crate::taste_memory;

const DIMENSIONS: [&str; 10] = [
    "energy",
    "valence",
    "tension",
    "density",
    "warmth",
    "movement",
    "space",
    "rawness",
    "complexity",
    "nostalgia",
];

type Dims = [f64; 10];

#[derive(Clone)]
struct RouteFlavorSpec {
    flavor: &'static str,
    label: &'static str,
    continuity_weight: f64,
    contrast_weight: f64,
    novelty_weight: f64,
    scene_weight: f64,
    risk_weight: f64,
}

fn bridge_route_specs() -> [RouteFlavorSpec; 3] {
    [
        RouteFlavorSpec {
            flavor: "direct_bridge",
            label: "Direct bridge",
            continuity_weight: 0.82,
            contrast_weight: 0.22,
            novelty_weight: 0.34,
            scene_weight: 0.74,
            risk_weight: 0.18,
        },
        RouteFlavorSpec {
            flavor: "scenic",
            label: "Scenic route",
            continuity_weight: 0.62,
            contrast_weight: 0.36,
            novelty_weight: 0.56,
            scene_weight: 0.8,
            risk_weight: 0.42,
        },
        RouteFlavorSpec {
            flavor: "contrast",
            label: "Contrast route",
            continuity_weight: 0.42,
            contrast_weight: 0.84,
            novelty_weight: 0.66,
            scene_weight: 0.44,
            risk_weight: 0.72,
        },
    ]
}

fn discovery_route_specs() -> [RouteFlavorSpec; 3] {
    [
        RouteFlavorSpec {
            flavor: "safe",
            label: "Safe",
            continuity_weight: 0.88,
            contrast_weight: 0.14,
            novelty_weight: 0.22,
            scene_weight: 0.84,
            risk_weight: 0.12,
        },
        RouteFlavorSpec {
            flavor: "interesting",
            label: "Interesting",
            continuity_weight: 0.62,
            contrast_weight: 0.42,
            novelty_weight: 0.6,
            scene_weight: 0.58,
            risk_weight: 0.46,
        },
        RouteFlavorSpec {
            flavor: "dangerous",
            label: "Dangerous",
            continuity_weight: 0.34,
            contrast_weight: 0.82,
            novelty_weight: 0.78,
            scene_weight: 0.28,
            risk_weight: 0.84,
        },
    ]
}

#[derive(Clone)]
struct RoleBehavior {
    role: String,
    explanation_depth: String,
    silent_inference_ok: bool,
    offer_alternatives: bool,
    prefer_revision: bool,
    protect_vibe: bool,
    tempt_sideways: bool,
}

struct ComposeRuntime<'a> {
    provider_status: &'a ComposerProviderStatus,
    provider_configs: &'a [ProviderConfig],
    behavior: &'a RoleBehavior,
    taste: &'a TasteProfile,
    taste_memory: &'a TasteMemorySnapshot,
    spotify_pressure: &'a SpotifyPressure,
    graph_context: &'a HashMap<String, GraphAffinity>,
    candidates: &'a [CandidateTrack],
}

struct NarrativeRequest<'a> {
    prompt: &'a str,
    action_label: &'a str,
    intent: &'a PlaylistIntent,
    behavior: &'a RoleBehavior,
    variants: &'a [RouteVariantSummary],
    tracks: &'a [ComposedPlaylistTrack],
}

#[derive(Clone)]
struct CandidateTrack {
    track: TrackRecord,
    dims: Dims,
    play_count: i64,
    artist_lower: String,
    title_lower: String,
    scene_family: String,
}

#[derive(Clone, Debug, Default)]
struct GraphAffinity {
    score: f64,
    connection_type: String,
    source_entity: String,
}

#[derive(Clone, Debug, Default)]
struct SpotifyPressure {
    available: bool,
    anchor_artist_keys: HashSet<String>,
    missing_world_artist_keys: HashSet<String>,
    recoverable_missing_count: i64,
    novelty_boost: f64,
    canon_resistance: f64,
    scene_exit_bias: f64,
    cue_lines: Vec<String>,
}

#[derive(Clone, Copy)]
struct ArcTemplateSpec {
    template_id: &'static str,
    labels: [&'static str; 4],
    energy: [f64; 4],
    valence: [f64; 4],
    tension: [f64; 4],
    warmth: [f64; 4],
    space: [f64; 4],
}

#[derive(Clone, Copy, Default)]
struct PromptPhaseShape {
    energy: f64,
    valence: f64,
    tension: f64,
    warmth: f64,
    space: f64,
    novelty: f64,
}

struct SequenceContext<'a> {
    taste: &'a TasteProfile,
    behavior: &'a RoleBehavior,
    taste_memory: &'a TasteMemorySnapshot,
    spotify_pressure: &'a SpotifyPressure,
    graph_context: &'a HashMap<String, GraphAffinity>,
    route_spec: Option<&'a RouteFlavorSpec>,
}

#[derive(Clone)]
struct ProviderConfig {
    provider_key: String,
    config: Value,
}

trait LlmProvider {
    fn provider_key(&self) -> &'static str;
    fn provider_kind(&self) -> &'static str;
    fn is_available(&self, config: &ProviderConfig) -> bool;
    fn parse_intent(
        &self,
        config: &ProviderConfig,
        provider_configs: &[ProviderConfig],
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent>;
    fn narrate(
        &self,
        config: &ProviderConfig,
        provider_configs: &[ProviderConfig],
        system_prompt: &str,
        user_prompt: &str,
    ) -> Option<String>;
}

struct OllamaProvider;

struct OpenAiCompatibleProvider {
    provider_key: &'static str,
}

fn config_string<'a>(config: &'a Value, keys: &[&str]) -> Option<&'a str> {
    keys.iter()
        .find_map(|key| config.get(*key).and_then(Value::as_str))
        .filter(|value| !value.trim().is_empty())
}

impl LlmProvider for OllamaProvider {
    fn provider_key(&self) -> &'static str {
        "ollama"
    }

    fn provider_kind(&self) -> &'static str {
        "local"
    }

    fn is_available(&self, config: &ProviderConfig) -> bool {
        let model = config_string(&config.config, &["model", "ollama_model"]).unwrap_or("");
        !model.trim().is_empty()
    }

    fn parse_intent(
        &self,
        config: &ProviderConfig,
        _provider_configs: &[ProviderConfig],
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent> {
        let base_url = config_string(&config.config, &["base_url", "ollama_base_url"])
            .unwrap_or("http://127.0.0.1:11434");
        let model = config_string(&config.config, &["model", "ollama_model"])?;
        let response = ureq::post(&format!("{}/api/chat", base_url.trim_end_matches('/')))
            .send_json(json!({
                "model": model,
                "stream": false,
                "format": "json",
                "messages": [
                    {
                        "role": "system",
                        "content": intent_prompt()
                    },
                    {
                        "role": "user",
                        "content": intent_user_prompt(prompt, fallback)
                    }
                ]
            }))
            .ok()?;
        let payload: Value = response.into_json().ok()?;
        let content = payload
            .get("message")
            .and_then(|value| value.get("content"))
            .and_then(Value::as_str)?;
        parse_intent_response(content, fallback)
    }

    fn narrate(
        &self,
        config: &ProviderConfig,
        _provider_configs: &[ProviderConfig],
        system_prompt: &str,
        user_prompt: &str,
    ) -> Option<String> {
        let base_url = config_string(&config.config, &["base_url", "ollama_base_url"])
            .unwrap_or("http://127.0.0.1:11434");
        let model = config_string(&config.config, &["model", "ollama_model"])?;
        let response = ureq::post(&format!("{}/api/chat", base_url.trim_end_matches('/')))
            .send_json(json!({
                "model": model,
                "stream": false,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            }))
            .ok()?;
        let payload: Value = response.into_json().ok()?;
        payload
            .get("message")
            .and_then(|value| value.get("content"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
    }
}

impl LlmProvider for OpenAiCompatibleProvider {
    fn provider_key(&self) -> &'static str {
        self.provider_key
    }

    fn provider_kind(&self) -> &'static str {
        "cloud"
    }

    fn is_available(&self, config: &ProviderConfig) -> bool {
        let model = config_string(
            &config.config,
            &[
                "model",
                "cloud_model",
                "openai_model",
                "groq_model",
                "openrouter_model",
            ],
        )
        .unwrap_or("");
        let api_key = config_string(
            &config.config,
            &[
                "api_key",
                "token",
                "openai_api_key",
                "groq_api_key",
                "openrouter_api_key",
            ],
        )
        .unwrap_or("");
        !model.trim().is_empty() && !api_key.trim().is_empty()
    }

    fn parse_intent(
        &self,
        config: &ProviderConfig,
        provider_configs: &[ProviderConfig],
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent> {
        let response = openai_compatible_completion(
            config,
            provider_configs,
            json!([
                {
                    "role": "system",
                    "content": intent_prompt()
                },
                {
                    "role": "user",
                    "content": intent_user_prompt(prompt, fallback)
                }
            ]),
        )?;
        parse_intent_response(&response, fallback)
    }

    fn narrate(
        &self,
        config: &ProviderConfig,
        provider_configs: &[ProviderConfig],
        system_prompt: &str,
        user_prompt: &str,
    ) -> Option<String> {
        openai_compatible_completion(
            config,
            provider_configs,
            json!([
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]),
        )
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    }
}

pub fn compose_composer_response(
    conn: &Connection,
    settings: &SettingsPayload,
    prompt: &str,
    track_count: usize,
    steer: Option<&SteerPayload>,
) -> LyraResult<ComposerResponse> {
    let trimmed_prompt = prompt.trim();
    if trimmed_prompt.is_empty() {
        return Err(LyraError::Message("Prompt cannot be empty".to_string()));
    }
    info!(
        "lyra-compose: prompt='{}' track_count={}",
        trimmed_prompt, track_count
    );

    let requested_provider = normalize_provider_preference(&settings.composer_provider_preference);
    let provider_configs = load_llm_provider_configs(conn)?;
    let taste_memory = taste_memory::load_snapshot(conn).unwrap_or_default();
    let heuristic_intent = heuristic_intent(conn, trimmed_prompt, settings, &taste_memory);
    let (provider_status, parsed_intent) = select_and_parse_intent(
        trimmed_prompt,
        &heuristic_intent,
        requested_provider.as_str(),
        &provider_configs,
    );
    let steered_intent = apply_steer(&parsed_intent, steer);
    let action = detect_composer_action(trimmed_prompt, &steered_intent);
    info!(
        "lyra-compose: action={} provider={} mode={} role={}",
        format!("{:?}", action).to_ascii_lowercase(),
        provider_status.selected_provider,
        provider_status.mode,
        steered_intent.prompt_role
    );
    let behavior = role_behavior(&steered_intent, &action);
    let taste = load_taste_profile(conn);
    let spotify_pressure = load_spotify_pressure(conn, &steered_intent);
    let graph_context = build_graph_context(conn, &steered_intent);
    let candidates = load_candidates(conn)?;
    let runtime = ComposeRuntime {
        provider_status: &provider_status,
        provider_configs: &provider_configs,
        behavior: &behavior,
        taste: &taste,
        taste_memory: &taste_memory,
        spotify_pressure: &spotify_pressure,
        graph_context: &graph_context,
        candidates: &candidates,
    };
    let response = match action {
        ComposerAction::Bridge => compose_bridge_response(
            trimmed_prompt,
            track_count.max(5),
            &steered_intent,
            &runtime,
        ),
        ComposerAction::Discovery => compose_discovery_response(
            trimmed_prompt,
            track_count.max(9),
            &steered_intent,
            &runtime,
        ),
        ComposerAction::Explain => compose_explanation_response(
            trimmed_prompt,
            &steered_intent,
            runtime.provider_status,
            runtime.behavior,
        ),
        ComposerAction::Steer | ComposerAction::Playlist => compose_draft_response(
            trimmed_prompt,
            track_count.max(4),
            &steered_intent,
            &runtime,
        ),
    };
    Ok(response)
}

pub fn compose_playlist_draft(
    conn: &Connection,
    settings: &SettingsPayload,
    prompt: &str,
    track_count: usize,
) -> LyraResult<ComposedPlaylistDraft> {
    let response = compose_composer_response(conn, settings, prompt, track_count, None)?;
    response.draft.ok_or_else(|| {
        LyraError::Message("Prompt did not resolve to a playlist draft.".to_string())
    })
}

pub fn save_composed_playlist(
    conn: &Connection,
    name: &str,
    draft: &ComposedPlaylistDraft,
) -> LyraResult<i64> {
    let playlist_id = playlists::create_playlist(conn, name)?;
    for item in &draft.tracks {
        playlists::add_track_to_playlist(conn, playlist_id, item.track.id)?;
        conn.execute(
            "INSERT OR REPLACE INTO playlist_track_reasons (playlist_id, track_id, reason, reason_json, phase_key, phase_label, position)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                playlist_id,
                item.track.id,
                item.reason.summary,
                serde_json::to_string(&item.reason)?,
                item.phase_key,
                item.phase_label,
                item.position as i64,
            ],
        )?;
    }
    Ok(playlist_id)
}

pub fn draft_to_generated(draft: &ComposedPlaylistDraft) -> GeneratedPlaylist {
    GeneratedPlaylist {
        name: draft.name.clone(),
        intent: draft.prompt.clone(),
        narrative: draft.narrative.clone(),
        tracks: draft
            .tracks
            .iter()
            .map(|item| PlaylistTrackWithReason {
                track: item.track.clone(),
                reason: item.reason.summary.clone(),
                position: item.position,
            })
            .collect(),
    }
}

fn compose_draft_response(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> ComposerResponse {
    let phases = build_phase_plan(
        intent,
        track_count,
        runtime.behavior,
        runtime.spotify_pressure,
    );
    let tracks = sequence_tracks(
        runtime.candidates,
        &phases,
        intent,
        track_count,
        SequenceContext {
            taste: runtime.taste,
            behavior: runtime.behavior,
            taste_memory: runtime.taste_memory,
            spotify_pressure: runtime.spotify_pressure,
            graph_context: runtime.graph_context,
            route_spec: None,
        },
    );
    let phase_route_comparison = route_comparison_for_phases(&phases);
    let narrative = select_narrative(
        &NarrativeRequest {
            prompt,
            action_label: "playlist",
            intent,
            behavior: runtime.behavior,
            variants: &phase_route_comparison.variants,
            tracks: &tracks,
        },
        runtime.provider_status,
        runtime.provider_configs,
    )
    .or_else(|| Some(template_narrative(intent, &phases, runtime.behavior)));
    let alternatives_considered = alternatives_for_action(intent, &ComposerAction::Playlist);
    let uncertainty = uncertainty_notes(intent, runtime.provider_status, runtime.behavior);
    let framing = build_lyra_framing(
        prompt,
        intent,
        &detect_composer_action(prompt, intent),
        runtime.provider_status,
        runtime.behavior,
        runtime.taste_memory,
        runtime.spotify_pressure,
        Some(phase_route_comparison),
    );

    ComposerResponse {
        action: detect_composer_action(prompt, intent),
        prompt: prompt.to_string(),
        intent: intent.clone(),
        provider_status: runtime.provider_status.clone(),
        framing,
        draft: Some(ComposedPlaylistDraft {
            name: format!("{} Journey", title_case(prompt)),
            prompt: prompt.to_string(),
            intent: intent.clone(),
            provider_status: runtime.provider_status.clone(),
            phases,
            narrative,
            tracks,
        }),
        bridge: None,
        discovery: None,
        explanation: None,
        active_role: runtime.behavior.role.clone(),
        uncertainty,
        alternatives_considered,
        taste_memory: runtime.taste_memory.clone(),
    }
}

fn compose_bridge_response(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> ComposerResponse {
    let specs = bridge_route_specs();
    let selected_flavor = choose_bridge_flavor(prompt, runtime.taste_memory);
    let mut chosen_spec = &specs[0];
    let mut chosen_tracks = Vec::new();
    let mut variants = Vec::new();
    for spec in &specs {
        let flavored_intent = intent_for_route_flavor(intent, spec);
        let phases = build_bridge_phase_plan(
            &flavored_intent,
            track_count,
            runtime.behavior,
            runtime.spotify_pressure,
        );
        let tracks = sequence_tracks(
            runtime.candidates,
            &phases,
            &flavored_intent,
            track_count,
            SequenceContext {
                taste: runtime.taste,
                behavior: runtime.behavior,
                taste_memory: runtime.taste_memory,
                spotify_pressure: runtime.spotify_pressure,
                graph_context: runtime.graph_context,
                route_spec: Some(spec),
            },
        );
        variants.push(route_variant_summary(
            spec,
            &flavored_intent,
            runtime.spotify_pressure,
        ));
        if spec.flavor == selected_flavor {
            chosen_spec = spec;
            chosen_tracks = tracks;
        }
    }
    if chosen_tracks.is_empty() {
        let phases = build_bridge_phase_plan(
            intent,
            track_count,
            runtime.behavior,
            runtime.spotify_pressure,
        );
        chosen_tracks = sequence_tracks(
            runtime.candidates,
            &phases,
            intent,
            track_count,
            SequenceContext {
                taste: runtime.taste,
                behavior: runtime.behavior,
                taste_memory: runtime.taste_memory,
                spotify_pressure: runtime.spotify_pressure,
                graph_context: runtime.graph_context,
                route_spec: None,
            },
        );
    }
    let (source_label, destination_label) = bridge_labels(prompt, intent);
    let narrative = select_narrative(
        &NarrativeRequest {
            prompt,
            action_label: "bridge",
            intent,
            behavior: runtime.behavior,
            variants: &variants,
            tracks: &chosen_tracks,
        },
        runtime.provider_status,
        runtime.provider_configs,
    )
    .or_else(|| {
        Some(template_bridge_narrative(
            intent,
            &source_label,
            &destination_label,
        ))
    });
    let steps = chosen_tracks
        .iter()
        .enumerate()
        .map(|(idx, item)| {
            let candidate = runtime
                .candidates
                .iter()
                .find(|candidate| candidate.track.id == item.track.id);
            let candidate_dims = candidate
                .map(|candidate| candidate.dims)
                .unwrap_or([0.5; 10]);
            let previous_dims = if idx == 0 {
                None
            } else {
                chosen_tracks.get(idx - 1).and_then(|previous| {
                    runtime
                        .candidates
                        .iter()
                        .find(|candidate| candidate.track.id == previous.track.id)
                        .map(|candidate| candidate.dims)
                })
            };
            let fallback_candidate = CandidateTrack {
                track: item.track.clone(),
                dims: candidate_dims,
                play_count: candidate
                    .map(|candidate| candidate.play_count)
                    .unwrap_or_default(),
                artist_lower: item.track.artist.to_ascii_lowercase(),
                title_lower: item.track.title.to_ascii_lowercase(),
                scene_family: scene_family_for_genre(item.track.genre.as_deref().unwrap_or("")),
            };
            let (preserves, changes) =
                preserve_change_notes(&fallback_candidate, intent, chosen_spec);
            BridgeStep {
                track: item.track.clone(),
                fit_score: item.fit_score,
                role: bridge_step_role(idx, chosen_tracks.len()),
                why: format!(
                    "{} {}",
                    item.reason.why_this_track, item.reason.transition_note
                ),
                distance_from_source: bridge_distance(idx, chosen_tracks.len(), false),
                distance_from_destination: bridge_distance(idx, chosen_tracks.len(), true),
                preserves,
                changes,
                adjacency_type: if chosen_spec.flavor == "contrast" {
                    "shared tension".to_string()
                } else if chosen_spec.flavor == "scenic" {
                    "scene adjacency".to_string()
                } else {
                    "emotional continuity".to_string()
                },
                adjacency_signals: adjacency_signals_for_transition(
                    previous_dims,
                    candidate_dims,
                    intent,
                    chosen_spec,
                ),
                leads_to_next: if idx + 1 < chosen_tracks.len() {
                    "It leaves one live wire for the next step to pick up.".to_string()
                } else {
                    "It resolves the bridge without pretending the source disappeared.".to_string()
                },
            }
        })
        .collect::<Vec<_>>();
    let bridge = BridgePath {
        source_label,
        destination_label,
        route_flavor: chosen_spec.flavor.to_string(),
        steps,
        narrative,
        confidence: intent.confidence,
        alternate_directions: alternatives_for_action(intent, &ComposerAction::Bridge),
        variants: variants.clone(),
    };
    let framing = build_lyra_framing(
        prompt,
        intent,
        &ComposerAction::Bridge,
        runtime.provider_status,
        runtime.behavior,
        runtime.taste_memory,
        runtime.spotify_pressure,
        Some(route_comparison_for_bridge(&bridge)),
    );

    ComposerResponse {
        action: ComposerAction::Bridge,
        prompt: prompt.to_string(),
        intent: intent.clone(),
        provider_status: runtime.provider_status.clone(),
        framing,
        draft: None,
        bridge: Some(bridge),
        discovery: None,
        explanation: None,
        active_role: runtime.behavior.role.clone(),
        uncertainty: uncertainty_notes(intent, runtime.provider_status, runtime.behavior),
        alternatives_considered: alternatives_for_action(intent, &ComposerAction::Bridge),
        taste_memory: runtime.taste_memory.clone(),
    }
}

fn compose_discovery_response(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> ComposerResponse {
    let scene_exit = is_scene_exit_prompt(prompt);
    let primary_flavor = choose_discovery_flavor(
        prompt,
        intent,
        runtime.taste_memory,
        runtime.spotify_pressure,
    )
    .to_string();
    let seed_label = intent
        .explicit_entities
        .first()
        .cloned()
        .unwrap_or_else(|| title_case(prompt));
    let directions = discovery_directions(prompt, track_count, intent, runtime);
    let variants = discovery_route_specs()
        .iter()
        .map(|spec| route_variant_summary(spec, intent, runtime.spotify_pressure))
        .collect::<Vec<_>>();
    let route = DiscoveryRoute {
        seed_label,
        primary_flavor: primary_flavor.clone(),
        scene_exit,
        directions,
        narrative: select_narrative(
            &NarrativeRequest {
                prompt,
                action_label: "discovery",
                intent,
                behavior: runtime.behavior,
                variants: &variants,
                tracks: &[],
            },
            runtime.provider_status,
            runtime.provider_configs,
        )
        .or_else(|| Some(template_discovery_narrative(intent))),
        confidence: intent.confidence,
        variants: variants.clone(),
    };
    let framing = build_lyra_framing(
        prompt,
        intent,
        &ComposerAction::Discovery,
        runtime.provider_status,
        runtime.behavior,
        runtime.taste_memory,
        runtime.spotify_pressure,
        Some(route_comparison_for_discovery(&route)),
    );

    ComposerResponse {
        action: ComposerAction::Discovery,
        prompt: prompt.to_string(),
        intent: intent.clone(),
        provider_status: runtime.provider_status.clone(),
        framing,
        draft: None,
        bridge: None,
        discovery: Some(route),
        explanation: None,
        active_role: runtime.behavior.role.clone(),
        uncertainty: uncertainty_notes(intent, runtime.provider_status, runtime.behavior),
        alternatives_considered: alternatives_for_action(intent, &ComposerAction::Discovery),
        taste_memory: runtime.taste_memory.clone(),
    }
}

fn compose_explanation_response(
    prompt: &str,
    intent: &PlaylistIntent,
    provider_status: &ComposerProviderStatus,
    behavior: &RoleBehavior,
) -> ComposerResponse {
    ComposerResponse {
        action: ComposerAction::Explain,
        prompt: prompt.to_string(),
        intent: intent.clone(),
        provider_status: provider_status.clone(),
        framing: build_lyra_framing(
            prompt,
            intent,
            &ComposerAction::Explain,
            provider_status,
            behavior,
            &TasteMemorySnapshot::default(),
            &SpotifyPressure::default(),
            None,
        ),
        draft: None,
        bridge: None,
        discovery: None,
        explanation: Some(template_explanation(intent, provider_status, behavior)),
        active_role: behavior.role.clone(),
        uncertainty: uncertainty_notes(intent, provider_status, behavior),
        alternatives_considered: alternatives_for_action(intent, &ComposerAction::Explain),
        taste_memory: TasteMemorySnapshot::default(),
    }
}

fn role_behavior(intent: &PlaylistIntent, action: &ComposerAction) -> RoleBehavior {
    let role = intent.prompt_role.clone();
    match role.as_str() {
        "oracle" => RoleBehavior {
            role,
            explanation_depth: "deep".to_string(),
            silent_inference_ok: false,
            offer_alternatives: true,
            prefer_revision: matches!(action, ComposerAction::Playlist | ComposerAction::Steer),
            protect_vibe: true,
            tempt_sideways: false,
        },
        "copilot" => RoleBehavior {
            role,
            explanation_depth: "balanced".to_string(),
            silent_inference_ok: true,
            offer_alternatives: true,
            prefer_revision: true,
            protect_vibe: true,
            tempt_sideways: true,
        },
        "coach" => RoleBehavior {
            role,
            explanation_depth: "balanced".to_string(),
            silent_inference_ok: false,
            offer_alternatives: true,
            prefer_revision: true,
            protect_vibe: true,
            tempt_sideways: true,
        },
        _ => RoleBehavior {
            role,
            explanation_depth: "light".to_string(),
            silent_inference_ok: true,
            offer_alternatives: matches!(
                action,
                ComposerAction::Bridge | ComposerAction::Discovery
            ),
            prefer_revision: false,
            protect_vibe: matches!(action, ComposerAction::Bridge | ComposerAction::Steer),
            tempt_sideways: matches!(action, ComposerAction::Discovery | ComposerAction::Bridge),
        },
    }
}

fn load_llm_provider_configs(conn: &Connection) -> LyraResult<Vec<ProviderConfig>> {
    let mut stmt = conn.prepare(
        "SELECT provider_key, config_json
         FROM provider_configs
         WHERE enabled = 1
           AND provider_key IN ('ollama', 'openai', 'openrouter', 'groq')",
    )?;
    let rows = stmt.query_map([], |row| {
        let provider_key: String = row.get(0)?;
        let config_json: String = row.get(1)?;
        let config = serde_json::from_str(&config_json).unwrap_or_else(|_| json!({}));
        Ok(ProviderConfig {
            provider_key,
            config,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

fn select_and_parse_intent(
    prompt: &str,
    heuristic: &PlaylistIntent,
    requested_provider: &str,
    provider_configs: &[ProviderConfig],
) -> (ComposerProviderStatus, PlaylistIntent) {
    let providers: Vec<Box<dyn LlmProvider>> = vec![
        Box::new(OllamaProvider),
        Box::new(OpenAiCompatibleProvider {
            provider_key: "openrouter",
        }),
        Box::new(OpenAiCompatibleProvider {
            provider_key: "groq",
        }),
        Box::new(OpenAiCompatibleProvider {
            provider_key: "openai",
        }),
    ];

    if requested_provider == "disabled" {
        return (
            ComposerProviderStatus {
                requested_provider: "disabled".to_string(),
                selected_provider: "heuristic".to_string(),
                provider_kind: "deterministic".to_string(),
                mode: "heuristic-only".to_string(),
                fallback_reason: Some("Composer LLM disabled in settings.".to_string()),
            },
            heuristic.clone(),
        );
    }

    let order = provider_order(requested_provider);
    for provider_key in order {
        let Some(config) = provider_configs
            .iter()
            .find(|config| config.provider_key == provider_key)
        else {
            continue;
        };
        let Some(provider) = providers
            .iter()
            .find(|provider| provider.provider_key() == provider_key)
        else {
            continue;
        };
        if !provider.is_available(config) {
            continue;
        }
        if let Some(parsed) = provider.parse_intent(config, provider_configs, prompt, heuristic) {
            let sanitized = sanitize_provider_intent(prompt, heuristic, parsed);
            info!(
                "lyra-compose: provider-parse success provider={} confidence={:.2}",
                provider.provider_key(),
                sanitized.confidence
            );
            return (
                ComposerProviderStatus {
                    requested_provider: requested_provider.to_string(),
                    selected_provider: provider.provider_key().to_string(),
                    provider_kind: provider.provider_kind().to_string(),
                    mode: if sanitized.confidence > heuristic.confidence {
                        "provider-assisted".to_string()
                    } else {
                        "provider-assisted-with-heuristic-merge".to_string()
                    },
                    fallback_reason: None,
                },
                sanitized,
            );
        }
    }

    warn!("lyra-compose: no provider parse available; using heuristic fallback");
    (
        ComposerProviderStatus {
            requested_provider: requested_provider.to_string(),
            selected_provider: "heuristic".to_string(),
            provider_kind: "deterministic".to_string(),
            mode: "heuristic-fallback".to_string(),
            fallback_reason: Some(
                "No configured LLM provider was available for this prompt.".to_string(),
            ),
        },
        heuristic.clone(),
    )
}

fn select_narrative(
    request: &NarrativeRequest<'_>,
    provider_status: &ComposerProviderStatus,
    provider_configs: &[ProviderConfig],
) -> Option<String> {
    if provider_status.provider_kind == "deterministic" {
        return None;
    }
    let provider_key = provider_status.selected_provider.clone();
    let config = provider_configs
        .iter()
        .find(|config| config.provider_key == provider_key)?;
    let system_prompt =
        provider_narrative_system_prompt(request.action_label, request.behavior, provider_status);
    let user_prompt = provider_narrative_user_prompt(
        request.prompt,
        request.intent,
        request.variants,
        request.tracks,
    );
    let raw = match provider_key.as_str() {
        "ollama" => OllamaProvider.narrate(config, provider_configs, &system_prompt, &user_prompt),
        "openai" => OpenAiCompatibleProvider {
            provider_key: "openai",
        }
        .narrate(config, provider_configs, &system_prompt, &user_prompt),
        "openrouter" => OpenAiCompatibleProvider {
            provider_key: "openrouter",
        }
        .narrate(config, provider_configs, &system_prompt, &user_prompt),
        "groq" => OpenAiCompatibleProvider {
            provider_key: "groq",
        }
        .narrate(config, provider_configs, &system_prompt, &user_prompt),
        _ => None,
    }?;
    sanitize_provider_narrative(&raw, request.action_label, provider_status)
}

fn provider_narrative_system_prompt(
    action_label: &str,
    behavior: &RoleBehavior,
    provider_status: &ComposerProviderStatus,
) -> String {
    format!(
        "You are Lyra inside Cassette. Obey the Lyra contract exactly. Stay in {action_label} mode and {} role behavior. Use 2 concise sentences maximum. Name what the route preserves, what it changes, and how confident Lyra should sound. No generic assistant filler, no apology, no fake poetry, no invented tracks, no pretending provider certainty. Mention heuristic limits if the evidence is partial. Provider mode is {} / {}.",
        behavior.role,
        provider_status.provider_kind,
        provider_status.mode
    )
}

fn provider_narrative_user_prompt(
    prompt: &str,
    intent: &PlaylistIntent,
    variants: &[RouteVariantSummary],
    tracks: &[ComposedPlaylistTrack],
) -> String {
    let variant_text = variants
        .iter()
        .map(|variant| {
            format!(
                "{}: {} | preserves {} | changes {}",
                variant.label,
                variant.logic,
                variant.preserves.join(", "),
                variant.changes.join(", ")
            )
        })
        .collect::<Vec<_>>()
        .join(" || ");
    let track_text = tracks
        .iter()
        .take(6)
        .map(|track| format!("{} - {}", track.track.artist, track.track.title))
        .collect::<Vec<_>>()
        .join(" | ");
    format!(
        "Prompt: {prompt}\nEmotional arc: {}\nTexture cues: {}\nRoute variants: {variant_text}\nRepresentative tracks: {track_text}\nWrite Lyra-facing narration that obeys the contract.",
        intent.emotional_arc.join(", "),
        intent.texture_descriptors.join(", "),
    )
}

fn sanitize_provider_narrative(
    raw: &str,
    action_label: &str,
    provider_status: &ComposerProviderStatus,
) -> Option<String> {
    let cleaned = raw
        .replace("Certainly,", "")
        .replace("Here are", "")
        .replace("I can help", "")
        .trim()
        .to_string();
    if cleaned.is_empty()
        || cleaned.to_ascii_lowercase().contains("as an ai")
        || cleaned.to_ascii_lowercase().contains("i'm sorry")
    {
        return None;
    }
    let mut sentences = cleaned
        .split_terminator('.')
        .map(str::trim)
        .filter(|sentence| !sentence.is_empty())
        .take(2)
        .map(|sentence| format!("{sentence}."))
        .collect::<Vec<_>>();
    if sentences.is_empty() {
        return None;
    }
    if provider_status.provider_kind != "deterministic"
        && !sentences.iter().any(|sentence| {
            sentence.contains("preserves")
                || sentence.contains("changes")
                || sentence.contains("risk")
                || sentence.contains("safe")
                || sentence.contains("interesting")
                || sentence.contains("dangerous")
        })
    {
        sentences.push(format!(
            "Lyra is keeping this {action_label} legible by naming what the route preserves and what it changes."
        ));
    }
    Some(sentences.join(" "))
}

fn provider_order(requested_provider: &str) -> Vec<&str> {
    let mut order = match requested_provider {
        "auto" => vec!["ollama", "openrouter", "groq", "openai"],
        "ollama" => vec!["ollama", "openrouter", "groq", "openai"],
        "openrouter" => vec!["openrouter", "groq", "openai", "ollama"],
        "groq" => vec!["groq", "openrouter", "openai", "ollama"],
        "openai" => vec!["openai", "openrouter", "groq", "ollama"],
        other => vec![other, "ollama", "openrouter", "groq", "openai"],
    };
    order.dedup();
    order
}

fn heuristic_intent(
    conn: &Connection,
    prompt: &str,
    settings: &SettingsPayload,
    taste_memory: &TasteMemorySnapshot,
) -> PlaylistIntent {
    let lower = prompt.to_ascii_lowercase();
    let source_energy = detect_source_energy(&lower);
    let destination_energy = detect_destination_energy(&lower, &source_energy);
    let transition_style = detect_transition_style(&lower);
    let emotional_arc = detect_emotional_arc(&lower);
    let texture_descriptors = detect_texture_descriptors(&lower);
    let explicit_entities = detect_named_entities(conn, prompt);
    let familiarity_vs_novelty = detect_familiarity(&lower);
    let discovery_aggressiveness = detect_discovery_aggressiveness(&lower);
    let user_steer = detect_user_steer(&lower);
    let exclusions = detect_exclusions(prompt);
    let sequencing_notes = detect_sequencing_notes(&lower);
    let confidence_notes = confidence_notes_for_prompt(&lower, &explicit_entities);
    let prompt_role = detect_prompt_role(&lower);

    PlaylistIntent {
        prompt: prompt.to_string(),
        prompt_role,
        source_energy: source_energy.clone(),
        destination_energy: destination_energy.clone(),
        opening_state: PlaylistIntentState {
            energy: source_energy,
            descriptors: detect_opening_descriptors(&lower),
        },
        landing_state: PlaylistIntentState {
            energy: destination_energy,
            descriptors: detect_landing_descriptors(&lower),
        },
        transition_style,
        emotional_arc,
        texture_descriptors,
        explicit_entities,
        familiarity_vs_novelty,
        discovery_aggressiveness,
        user_steer: merge_taste_memory(
            &user_steer,
            &settings.composer_taste_memory,
            &taste_memory.session_posture.active_signals,
        ),
        exclusions,
        explanation_depth: settings.composer_explanation_depth.clone(),
        sequencing_notes,
        confidence_notes,
        confidence: heuristic_confidence(prompt),
    }
}

fn build_phase_plan(
    intent: &PlaylistIntent,
    track_count: usize,
    behavior: &RoleBehavior,
    spotify_pressure: &SpotifyPressure,
) -> Vec<PlaylistPhase> {
    let start_energy = energy_value(&intent.source_energy);
    let end_energy = energy_value(&intent.destination_energy);
    let gradual =
        intent.transition_style.contains("gradual") || intent.transition_style.contains("glide");
    let template = select_arc_template(intent, behavior);
    let prompt_phase_shape = prompt_phase_shape(intent);
    let arc = [
        ("ignite", "Ignition"),
        ("open", "Opening run"),
        ("bridge", "Bridge"),
        ("land", "Landing"),
    ];
    let role_valence_bias = match behavior.role.as_str() {
        "coach" => 0.06,
        "oracle" => -0.04,
        _ => 0.0,
    };
    arc.iter()
        .enumerate()
        .map(|(idx, (key, label))| {
            let progress = if track_count <= 1 {
                1.0
            } else {
                idx as f64 / (arc.len().saturating_sub(1) as f64)
            };
            let eased = if gradual {
                progress * progress * (3.0 - 2.0 * progress)
            } else {
                progress
            };
            let energy = lerp(
                lerp(start_energy, end_energy, eased),
                template_value(template.energy, idx),
                0.44,
            );
            let valence = lerp(
                if intent
                    .emotional_arc
                    .iter()
                    .any(|value| value.contains("ache"))
                {
                    lerp(0.38 + role_valence_bias, 0.56 + role_valence_bias, eased)
                } else {
                    lerp(0.48 + role_valence_bias, 0.64 + role_valence_bias, eased)
                },
                template_value(template.valence, idx),
                0.38,
            );
            let tension = lerp(
                if idx < 2 {
                    lerp(0.78, 0.5, eased)
                } else {
                    lerp(0.5, 0.32, eased)
                },
                template_value(template.tension, idx),
                0.46,
            );
            let warmth = lerp(
                if intent
                    .texture_descriptors
                    .iter()
                    .any(|value| value.contains("lofi"))
                {
                    lerp(0.34, 0.78, eased)
                } else {
                    lerp(0.38, 0.62, eased)
                },
                template_value(template.warmth, idx),
                0.34,
            );
            let space = lerp(
                if idx >= 2 {
                    lerp(0.42, 0.82, eased)
                } else {
                    lerp(0.28, 0.58, eased)
                },
                template_value(template.space, idx),
                0.38,
            );
            let prompt_pressure = prompt_phase_shape[idx];
            PlaylistPhase {
                key: (*key).to_string(),
                label: format!("{} {}", *label, title_case(template.labels[idx])),
                summary: phase_summary(intent, template.template_id, idx, prompt_pressure),
                target_energy: (energy + prompt_pressure.energy).clamp(0.0, 1.0),
                target_valence: (valence + prompt_pressure.valence).clamp(0.0, 1.0),
                target_tension: (tension + prompt_pressure.tension).clamp(0.0, 1.0),
                target_warmth: (warmth + prompt_pressure.warmth).clamp(0.0, 1.0),
                target_space: (space + prompt_pressure.space).clamp(0.0, 1.0),
                novelty_bias: (novelty_bias(intent, idx, spotify_pressure)
                    + prompt_pressure.novelty)
                    .clamp(0.0, 1.0),
            }
        })
        .collect()
}

fn load_candidates(conn: &Connection) -> LyraResult<Vec<CandidateTrack>> {
    let mut stmt = conn.prepare(
        "SELECT t.id,
                t.title,
                COALESCE(ar.name, ''),
                COALESCE(al.title, ''),
                t.path,
                COALESCE(t.duration_seconds, 0),
                t.genre,
                t.year,
                t.bpm,
                t.key_signature,
                t.liked_at,
                COALESCE(ts.energy, 0.5),
                COALESCE(ts.valence, 0.5),
                COALESCE(ts.tension, 0.5),
                COALESCE(ts.density, 0.5),
                COALESCE(ts.warmth, 0.5),
                COALESCE(ts.movement, 0.5),
                COALESCE(ts.space, 0.5),
                COALESCE(ts.rawness, 0.5),
                COALESCE(ts.complexity, 0.5),
                COALESCE(ts.nostalgia, 0.5),
                COALESCE((
                    SELECT COUNT(*)
                    FROM playback_history ph
                    WHERE ph.track_id = t.id
                ), 0)
         FROM tracks t
         JOIN track_scores ts ON ts.track_id = t.id
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE COALESCE(t.quarantined, 0) = 0
         ORDER BY t.id DESC
         LIMIT 6000",
    )?;

    let rows = stmt.query_map([], |row| {
        let liked_at: Option<String> = row.get(10)?;
        let track = TrackRecord {
            id: row.get(0)?,
            title: row.get(1)?,
            artist: row.get(2)?,
            album: row.get(3)?,
            path: row.get(4)?,
            duration_seconds: row.get(5)?,
            genre: row.get(6)?,
            year: row.get(7)?,
            bpm: row.get(8)?,
            key_signature: row.get(9)?,
            liked: liked_at.is_some(),
            liked_at,
        };
        Ok(CandidateTrack {
            artist_lower: track.artist.to_ascii_lowercase(),
            title_lower: track.title.to_ascii_lowercase(),
            scene_family: scene_family_for_genre(track.genre.as_deref().unwrap_or("")),
            track,
            dims: [
                row.get(11)?,
                row.get(12)?,
                row.get(13)?,
                row.get(14)?,
                row.get(15)?,
                row.get(16)?,
                row.get(17)?,
                row.get(18)?,
                row.get(19)?,
                row.get(20)?,
            ],
            play_count: row.get(21)?,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

fn scene_family_for_genre(genre: &str) -> String {
    let lower = genre.to_ascii_lowercase();
    if has_any(&lower, &["punk", "hardcore", "grunge", "garage", "emo"]) {
        "punk".to_string()
    } else if has_any(
        &lower,
        &[
            "edm",
            "electronic",
            "house",
            "techno",
            "trance",
            "breakcore",
            "drum and bass",
            "synth",
        ],
    ) {
        "electronic".to_string()
    } else if has_any(
        &lower,
        &["ambient", "lofi", "shoegaze", "slowcore", "dream"],
    ) {
        "haze".to_string()
    } else if has_any(
        &lower,
        &["darkwave", "ebm", "witch house", "post-punk", "goth"],
    ) {
        "nocturnal".to_string()
    } else if has_any(
        &lower,
        &["folk", "singer-songwriter", "chamber", "acoustic"],
    ) {
        "intimate".to_string()
    } else if has_any(&lower, &["hip hop", "rap", "trip-hop"]) {
        "hiphop".to_string()
    } else if has_any(&lower, &["jazz", "soul", "r&b", "funk"]) {
        "groove".to_string()
    } else if has_any(&lower, &["metal", "industrial"]) {
        "heavy".to_string()
    } else if has_any(&lower, &["pop", "art-pop", "indie"]) {
        "indie-pop".to_string()
    } else {
        "mixed".to_string()
    }
}

fn prompt_scene_families(prompt: &str, texture_descriptors: &[String]) -> Vec<String> {
    let lower = prompt.to_ascii_lowercase();
    let mut families = Vec::new();
    for family in texture_descriptors
        .iter()
        .map(|value| scene_family_for_genre(value))
        .filter(|value| value != "mixed")
    {
        families.push(family);
    }
    for (needle, values) in [
        ("aggressive", vec!["punk", "heavy", "electronic"]),
        ("euphoric", vec!["electronic", "indie-pop"]),
        ("melancholic", vec!["haze", "intimate"]),
        ("energetic", vec!["electronic", "heavy"]),
        ("dark", vec!["nocturnal", "heavy"]),
        ("rebellious", vec!["punk", "heavy"]),
        ("introspective", vec!["intimate", "haze"]),
        ("late-night", vec!["nocturnal", "electronic"]),
        ("lofi", vec!["haze"]),
        ("shoegaze", vec!["haze"]),
        ("edm", vec!["electronic"]),
        ("punk", vec!["punk"]),
        ("jazz", vec!["groove"]),
        ("hip hop", vec!["hiphop"]),
    ] {
        if lower.contains(needle) {
            families.extend(values.into_iter().map(str::to_string));
        }
    }
    families.sort();
    families.dedup();
    if families.is_empty() {
        families.push("mixed".to_string());
    }
    families
}

fn adjacent_scene_families(source: &str) -> Vec<String> {
    match source {
        "punk" => vec!["nocturnal", "indie-pop", "heavy"],
        "electronic" => vec!["haze", "nocturnal", "groove"],
        "haze" => vec!["intimate", "electronic", "nocturnal"],
        "nocturnal" => vec!["electronic", "haze", "punk"],
        "intimate" => vec!["haze", "indie-pop", "groove"],
        "hiphop" => vec!["groove", "electronic", "intimate"],
        "groove" => vec!["hiphop", "indie-pop", "electronic"],
        "heavy" => vec!["punk", "electronic", "nocturnal"],
        "indie-pop" => vec!["intimate", "electronic", "haze"],
        _ => vec!["electronic", "haze", "intimate"],
    }
    .into_iter()
    .map(str::to_string)
    .collect()
}

fn contrast_scene_families(source: &str) -> Vec<String> {
    match source {
        "punk" => vec!["intimate", "groove", "haze"],
        "electronic" => vec!["punk", "intimate", "heavy"],
        "haze" => vec!["heavy", "groove", "punk"],
        "nocturnal" => vec!["groove", "intimate", "indie-pop"],
        "intimate" => vec!["heavy", "punk", "electronic"],
        "hiphop" => vec!["haze", "heavy", "punk"],
        "groove" => vec!["heavy", "haze", "nocturnal"],
        "heavy" => vec!["intimate", "haze", "groove"],
        "indie-pop" => vec!["heavy", "punk", "nocturnal"],
        _ => vec!["heavy", "punk", "groove"],
    }
    .into_iter()
    .map(str::to_string)
    .collect()
}

fn target_scene_families(intent: &PlaylistIntent, spec: &RouteFlavorSpec) -> Vec<String> {
    let sources = prompt_scene_families(&intent.prompt, &intent.texture_descriptors);
    let source = sources
        .first()
        .cloned()
        .unwrap_or_else(|| "mixed".to_string());
    match spec.flavor {
        "safe" | "direct_bridge" => {
            let mut families = vec![source.clone()];
            families.extend(adjacent_scene_families(&source).into_iter().take(1));
            families
        }
        "interesting" | "scenic" => adjacent_scene_families(&source),
        "dangerous" | "contrast" => contrast_scene_families(&source),
        _ => vec![source],
    }
}

fn sequence_tracks(
    candidates: &[CandidateTrack],
    phases: &[PlaylistPhase],
    intent: &PlaylistIntent,
    track_count: usize,
    context: SequenceContext<'_>,
) -> Vec<ComposedPlaylistTrack> {
    let phase_count = phases.len().max(1);
    let per_phase = ((track_count as f64 / phase_count as f64).ceil() as usize).max(1);
    let entity_needles: Vec<String> = intent
        .explicit_entities
        .iter()
        .map(|value| value.to_ascii_lowercase())
        .collect();
    let novelty_target = novelty_target(&intent.familiarity_vs_novelty);
    let mut used = HashSet::new();
    let mut ordered = Vec::new();
    let mut previous_dims: Option<Dims> = None;

    for phase in phases {
        let mut scored: Vec<(f64, &CandidateTrack)> = candidates
            .iter()
            .filter(|candidate| !used.contains(&candidate.track.id))
            .map(|candidate| {
                let fit = phase_fit(candidate, phase);
                let taste_fit = taste_fit(candidate, context.taste);
                let novelty_fit = 1.0 - (novelty_score(candidate) - novelty_target).abs();
                let entity_bonus = entity_bonus(candidate, &entity_needles);
                let transition_fit = previous_dims
                    .map(|prev| transition_fit(prev, candidate.dims, &intent.transition_style))
                    .unwrap_or(0.64);
                let vibe_guard_fit = vibe_guard_fit(candidate, intent, context.behavior);
                let sideways_fit = sideways_fit(candidate, intent, context.behavior);
                let graph_fit =
                    graph_affinity_fit(candidate, context.graph_context, context.route_spec);
                let route_fit = context
                    .route_spec
                    .map(|spec| {
                        route_shape_fit(
                            candidate,
                            previous_dims,
                            intent,
                            spec,
                            context.spotify_pressure,
                        )
                    })
                    .unwrap_or(0.58);
                let route_memory_fit =
                    route_memory_pressure(context.route_spec, context.taste_memory);
                let deep_cut_fit = deep_cut_pressure(
                    candidate,
                    intent,
                    context.route_spec,
                    context.spotify_pressure,
                );
                let (fit_weight, taste_weight, novelty_weight, transition_weight, entity_weight) =
                    score_weights(&context.behavior.role, &intent.prompt_role);
                let score = fit * fit_weight
                    + taste_fit * taste_weight
                    + novelty_fit * novelty_weight
                    + transition_fit * transition_weight
                    + entity_bonus * entity_weight
                    + vibe_guard_fit * 0.08
                    + sideways_fit * 0.06
                    + graph_fit * 0.1
                    + route_fit * 0.16
                    + route_memory_fit * 0.08
                    + deep_cut_fit * 0.08
                    + context.spotify_pressure.canon_resistance * 0.04;
                (score, candidate)
            })
            .filter(|(score, _)| *score >= route_score_floor(context.route_spec))
            .collect();
        scored.sort_by(|left, right| {
            right
                .0
                .partial_cmp(&left.0)
                .unwrap_or(Ordering::Equal)
                .then_with(|| left.1.play_count.cmp(&right.1.play_count))
        });

        for (score, candidate) in scored.into_iter().take(per_phase) {
            let summary = reason_summary(candidate, phase, score, context.behavior, context.taste);
            let why_this_track = format!(
                "{} anchors {} by matching {} energy with {} texture while Lyra works in {} mode{}.",
                candidate.track.title,
                phase.label,
                intent_phrase(&phase.label),
                descriptor_phrase(candidate, intent),
                context.behavior.role,
                graph_reason_suffix(candidate, context.graph_context)
            );
            let transition_note = previous_dims
                .map(|prev| transition_sentence(prev, candidate.dims, &intent.transition_style))
                .unwrap_or_else(|| {
                    "Opens the arc without forcing the landing too early.".to_string()
                });
            let reason = TrackReasonPayload {
                summary,
                phase: phase.label.clone(),
                why_this_track,
                transition_note,
                evidence: evidence_for_candidate(
                    candidate,
                    phase,
                    context.taste,
                    context.graph_context,
                    context.spotify_pressure,
                ),
                explicit_from_prompt: explicit_hits(candidate, &entity_needles),
                inferred_by_lyra: inferred_notes(
                    candidate,
                    phase,
                    intent,
                    context.behavior,
                    context.graph_context,
                    context.spotify_pressure,
                ),
                confidence: score.clamp(0.0, 1.0),
            };
            ordered.push(ComposedPlaylistTrack {
                track: candidate.track.clone(),
                phase_key: phase.key.clone(),
                phase_label: phase.label.clone(),
                fit_score: score,
                reason,
                position: ordered.len(),
            });
            used.insert(candidate.track.id);
            previous_dims = Some(candidate.dims);
        }
    }

    ordered.truncate(track_count);
    optimize_sequence_order(ordered, candidates, intent)
}

fn load_taste_profile(conn: &Connection) -> TasteProfile {
    crate::taste::get_taste_profile(conn).unwrap_or_default()
}

fn normalize_provider_preference(value: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "" => "auto".to_string(),
        "none" | "off" => "disabled".to_string(),
        other => other.to_string(),
    }
}

fn legacy_spotify_db_path() -> PathBuf {
    std::env::var("LYRA_DB_PATH")
        .ok()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("lyra_registry.db"))
}

fn with_attached_spotify_legacy<T, F>(conn: &Connection, callback: F) -> Option<T>
where
    F: FnOnce(&Connection, &Path) -> rusqlite::Result<T>,
{
    let legacy_path = legacy_spotify_db_path();
    if !legacy_path.exists() {
        return None;
    }
    conn.execute(
        "ATTACH DATABASE ?1 AS spotify_ctx",
        params![legacy_path.display().to_string()],
    )
    .ok()?;
    let result = callback(conn, &legacy_path).ok();
    let _ = conn.execute("DETACH DATABASE spotify_ctx", []);
    result
}

fn load_spotify_pressure(conn: &Connection, intent: &PlaylistIntent) -> SpotifyPressure {
    let lower_prompt = intent.prompt.to_ascii_lowercase();
    let scene_exit = is_scene_exit_prompt(&intent.prompt);
    let lower_entities = intent
        .explicit_entities
        .iter()
        .map(|value| value.to_ascii_lowercase())
        .collect::<Vec<_>>();

    with_attached_spotify_legacy(conn, |db, _legacy_path| {
        let history_exists = db
            .query_row(
                "SELECT 1 FROM spotify_ctx.sqlite_master WHERE type = 'table' AND name = 'spotify_history'",
                [],
                |_| Ok(1_i64),
            )
            .optional()?
            .is_some();
        let library_exists = db
            .query_row(
                "SELECT 1 FROM spotify_ctx.sqlite_master WHERE type = 'table' AND name = 'spotify_library'",
                [],
                |_| Ok(1_i64),
            )
            .optional()?
            .is_some();
        if !history_exists && !library_exists {
            return Ok(SpotifyPressure::default());
        }

        let recoverable_missing_count = if library_exists {
            db.query_row(
                "SELECT COUNT(*)
                 FROM spotify_ctx.spotify_library sl
                 WHERE NOT EXISTS (
                    SELECT 1
                    FROM tracks t
                    LEFT JOIN artists ar ON ar.id = t.artist_id
                    WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                      AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                 )
                 AND NOT EXISTS (
                    SELECT 1
                    FROM acquisition_queue aq
                    WHERE lower(trim(COALESCE(aq.artist, ''))) = lower(trim(sl.artist))
                      AND lower(trim(COALESCE(aq.title, ''))) = lower(trim(sl.title))
                      AND aq.status NOT IN ('completed', 'cancelled')
                 )",
                [],
                |row| row.get(0),
            )?
        } else {
            0
        };

        let mut anchor_artist_keys = HashSet::new();
        let mut missing_world_artist_keys = HashSet::new();
        let mut cue_lines = Vec::new();

        for entity in &lower_entities {
            let play_count = if history_exists {
                db.query_row(
                    "SELECT COUNT(*)
                     FROM spotify_ctx.spotify_history
                     WHERE lower(trim(COALESCE(artist, ''))) = lower(trim(?1))",
                    params![entity],
                    |row| row.get::<_, i64>(0),
                )?
            } else {
                0
            };
            let missing_count = if library_exists {
                db.query_row(
                    "SELECT COUNT(*)
                     FROM spotify_ctx.spotify_library sl
                     WHERE lower(trim(sl.artist)) = lower(trim(?1))
                       AND NOT EXISTS (
                          SELECT 1
                          FROM tracks t
                          LEFT JOIN artists ar ON ar.id = t.artist_id
                          WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                            AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                       )",
                    params![entity],
                    |row| row.get::<_, i64>(0),
                )?
            } else {
                0
            };
            if play_count > 0 || missing_count > 0 {
                anchor_artist_keys.insert(entity.clone());
                if missing_count > 0 {
                    missing_world_artist_keys.insert(entity.clone());
                    cue_lines.push(format!(
                        "Spotify history says {} mattered before the local library finished bringing that world home.",
                        title_case(entity)
                    ));
                }
            }
        }

        if cue_lines.is_empty() && history_exists && library_exists {
            let mut stmt = db.prepare(
                "WITH artist_plays AS (
                    SELECT
                        trim(artist) AS artist,
                        COUNT(*) AS play_count
                    FROM spotify_ctx.spotify_history
                    WHERE artist IS NOT NULL AND trim(artist) != ''
                    GROUP BY lower(trim(artist))
                )
                SELECT ap.artist,
                       ap.play_count,
                       (
                         SELECT COUNT(*)
                         FROM spotify_ctx.spotify_library sl
                         WHERE lower(trim(sl.artist)) = lower(trim(ap.artist))
                           AND NOT EXISTS (
                             SELECT 1
                             FROM tracks t
                             LEFT JOIN artists ar ON ar.id = t.artist_id
                             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(sl.artist))
                               AND lower(trim(COALESCE(t.title, ''))) = lower(trim(sl.title))
                           )
                       ) AS missing_count
                FROM artist_plays ap
                ORDER BY missing_count DESC, ap.play_count DESC
                LIMIT 2",
            )?;
            let rows = stmt.query_map([], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                ))
            })?;
            for (artist, play_count, missing_count) in rows.filter_map(Result::ok) {
                if missing_count > 0 {
                    missing_world_artist_keys.insert(artist.to_ascii_lowercase());
                    cue_lines.push(format!(
                        "{} still has {} locally missing tracks despite {} Spotify plays.",
                        artist, missing_count, play_count
                    ));
                }
            }
        }

        let novelty_boost = if !missing_world_artist_keys.is_empty() {
            0.16
        } else if !anchor_artist_keys.is_empty() {
            0.08
        } else if recoverable_missing_count > 24 {
            0.06
        } else {
            0.0
        };
        let canon_resistance = if !missing_world_artist_keys.is_empty()
            && has_any(
                &lower_prompt,
                &[
                    "less obvious",
                    "canon",
                    "different world",
                    "adjacent",
                    "rewarding risk",
                    "scene exit",
                ],
            ) {
            0.18
        } else if !missing_world_artist_keys.is_empty() {
            0.1
        } else {
            0.0
        };
        let scene_exit_bias = if scene_exit && !missing_world_artist_keys.is_empty() {
            0.18
        } else if scene_exit && recoverable_missing_count > 0 {
            0.1
        } else {
            0.0
        };

        Ok(SpotifyPressure {
            available: history_exists || library_exists,
            anchor_artist_keys,
            missing_world_artist_keys,
            recoverable_missing_count,
            novelty_boost,
            canon_resistance,
            scene_exit_bias,
            cue_lines,
        })
    })
    .unwrap_or_default()
}

fn apply_steer(intent: &PlaylistIntent, steer: Option<&SteerPayload>) -> PlaylistIntent {
    let Some(steer) = steer else {
        return intent.clone();
    };
    let mut next = intent.clone();
    if let Some(novelty_bias) = steer.novelty_bias {
        next.familiarity_vs_novelty = if novelty_bias >= 0.72 {
            "novel leaning".to_string()
        } else if novelty_bias <= 0.32 {
            "familiar leaning".to_string()
        } else {
            "balanced".to_string()
        };
    }
    if let Some(explanation_depth) = &steer.explanation_depth {
        next.explanation_depth = explanation_depth.clone();
    }
    if let Some(contrast) = steer.contrast_sharpness {
        next.transition_style = if contrast >= 0.68 {
            "contrast cut".to_string()
        } else if contrast <= 0.32 {
            "gradual cooling".to_string()
        } else {
            next.transition_style.clone()
        };
    }
    if let Some(warmth_bias) = steer.warmth_bias {
        if warmth_bias >= 0.68 {
            next.texture_descriptors.push("warm-night".to_string());
        } else if warmth_bias <= 0.32 {
            next.texture_descriptors.push("bright-air".to_string());
        }
    }
    if let Some(energy_bias) = steer.energy_bias {
        next.destination_energy = if energy_bias >= 0.68 {
            "high".to_string()
        } else if energy_bias <= 0.32 {
            "low".to_string()
        } else {
            next.destination_energy.clone()
        };
    }
    if let Some(adventurousness) = steer.adventurousness {
        next.discovery_aggressiveness = if adventurousness >= 0.72 {
            "assertive".to_string()
        } else if adventurousness <= 0.32 {
            "gentle".to_string()
        } else {
            "medium".to_string()
        };
    }
    next.texture_descriptors.sort();
    next.texture_descriptors.dedup();
    next
}

fn merge_taste_memory(
    user_steer: &[String],
    memory: &[String],
    session_signals: &[String],
) -> Vec<String> {
    let mut merged = user_steer.to_vec();
    merged.extend(memory.iter().cloned());
    merged.extend(session_signals.iter().cloned());
    merged.sort();
    merged.dedup();
    merged
}

fn detect_composer_action(prompt: &str, intent: &PlaylistIntent) -> ComposerAction {
    let lower = prompt.to_ascii_lowercase();
    if has_any(
        &lower,
        &[
            "bridge from",
            "show me a path",
            "path from",
            "what should come after this",
        ],
    ) {
        ComposerAction::Bridge
    } else if has_any(
        &lower,
        &[
            "three ways",
            "leave this scene",
            "three exits",
            "one safe, one interesting, one dangerous",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "stay in the ache, lose the gloss",
            "get me out of this canon",
            "scene exit",
            "rewarding risk",
        ],
    ) {
        ComposerAction::Discovery
    } else if has_any(
        &lower,
        &[
            "adjacent",
            "less obvious",
            "three ways",
            "leave this scene",
            "discover",
            "something adjacent",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "stay in the ache, lose the gloss",
            "canon",
            "rewarding risk",
        ],
    ) {
        if has_any(
            &lower,
            &[
                "make this",
                "without losing",
                "keep the",
                "stay in this mood",
            ],
        ) {
            ComposerAction::Steer
        } else {
            ComposerAction::Discovery
        }
    } else if has_any(&lower, &["why is this", "explain", "why this track"]) {
        ComposerAction::Explain
    } else if intent.prompt_role == "copilot" {
        ComposerAction::Steer
    } else {
        ComposerAction::Playlist
    }
}

fn detect_named_entities(conn: &Connection, prompt: &str) -> Vec<String> {
    let prompt_lower = prompt.to_ascii_lowercase();
    let mut entities = Vec::new();
    if let Ok(mut stmt) = conn.prepare(
        "SELECT name FROM artists
         WHERE instr(?1, lower(name)) > 0
         ORDER BY length(name) DESC
         LIMIT 6",
    ) {
        if let Ok(rows) = stmt.query_map(params![prompt_lower], |row| row.get::<_, String>(0)) {
            entities.extend(rows.filter_map(Result::ok));
        }
    }
    entities.sort();
    entities.dedup();
    entities
}

fn detect_prompt_role(lower: &str) -> String {
    if lower.contains("why") || lower.contains("explain") {
        "oracle".to_string()
    } else if has_any(lower, &["make this", "keep the", "stay in this mood"]) {
        "copilot".to_string()
    } else if has_any(
        lower,
        &[
            "adjacent",
            "discover",
            "bridge",
            "path from",
            "come after this",
            "what should come after this",
            "three ways",
            "three exits",
            "one safe, one interesting, one dangerous",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "stay in the ache, lose the gloss",
            "get me out of this canon",
            "rewarding risk",
        ],
    ) {
        "recommender".to_string()
    } else {
        "coach".to_string()
    }
}

fn detect_source_energy(lower: &str) -> String {
    if has_any(
        lower,
        &[
            "fire",
            "storm",
            "sprint",
            "high-energy",
            "blast",
            "frenzy",
            "edm",
        ],
    ) {
        "high".to_string()
    } else if has_any(lower, &["calm", "soft", "still", "lofi", "chill", "gentle"]) {
        "low".to_string()
    } else {
        "medium".to_string()
    }
}

fn detect_destination_energy(lower: &str, source: &str) -> String {
    if has_any(
        lower,
        &[
            "into chill",
            "lofi",
            "undercurrent",
            "forgives",
            "nocturnal",
            "calm",
        ],
    ) {
        "low".to_string()
    } else if has_any(lower, &["erupts", "ends loud", "climax", "blast"]) {
        "high".to_string()
    } else {
        source.to_string()
    }
}

fn detect_transition_style(lower: &str) -> String {
    if has_any(
        lower,
        &[
            "three exits",
            "leave this scene",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "stay in the ache, lose the gloss",
            "get me out of this canon",
        ],
    ) {
        "scene exit".to_string()
    } else if has_any(
        lower,
        &[
            "trickling",
            "gradual",
            "glide",
            "undercurrent",
            "slowly",
            "eventually",
        ],
    ) {
        "gradual cooling".to_string()
    } else if has_any(
        lower,
        &["sharper contrast", "hard pivot", "leave this scene"],
    ) {
        "contrast cut".to_string()
    } else if has_any(lower, &["bridge", "adjacent", "path"]) {
        "adjacent bridge".to_string()
    } else if has_any(lower, &["sprint", "storm", "crash"]) {
        "charged push".to_string()
    } else {
        "guided drift".to_string()
    }
}

fn detect_emotional_arc(lower: &str) -> Vec<String> {
    let mut values = Vec::new();
    if has_any(lower, &["ache", "sad", "melancholy", "forgives"]) {
        values.push("ache".to_string());
    }
    if has_any(lower, &["confession", "human", "forgives", "resolve"]) {
        values.push("release".to_string());
    }
    if has_any(
        lower,
        &["regret", "late-night", "melancholy", "bedroom static"],
    ) {
        values.push("afterglow".to_string());
    }
    if has_any(lower, &["storm", "fire", "sprint"]) {
        values.push("surge".to_string());
    }
    if values.is_empty() {
        values.push("curiosity".to_string());
    }
    values
}

fn detect_texture_descriptors(lower: &str) -> Vec<String> {
    let mapping = [
        ("lofi", "lofi"),
        ("cover", "cover-memory"),
        ("static", "static-hiss"),
        ("goth", "gothic"),
        ("neon", "neon-synthetic"),
        ("edm", "bright-synthetic"),
        ("bedroom", "bedroom-close"),
        ("mall", "public-space"),
        ("nocturnal", "night-drive"),
        ("chill", "cooling"),
        ("shimmer", "digital-shimmer"),
        ("analog", "analog-warmth"),
        ("confession", "confessional"),
        ("booth", "booth-intimate"),
        ("mall goth", "mall-goth"),
        ("electronic melancholy", "electronic-melancholy"),
    ];
    let mut values = Vec::new();
    for (needle, label) in mapping {
        if lower.contains(needle) {
            values.push(label.to_string());
        }
    }
    if values.is_empty() {
        values.push("mixed-library".to_string());
    }
    values
}

fn detect_familiarity(lower: &str) -> String {
    if has_any(
        lower,
        &[
            "less obvious",
            "adjacent but less obvious",
            "adventurous",
            "deeper cut",
            "different world",
            "out of this canon",
        ],
    ) {
        "novel leaning".to_string()
    } else if has_any(lower, &["more obvious", "familiar", "recognizable"]) {
        "familiar leaning".to_string()
    } else {
        "balanced".to_string()
    }
}

fn detect_discovery_aggressiveness(lower: &str) -> String {
    if has_any(
        lower,
        &[
            "three ways",
            "leave this scene",
            "path from",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "rewarding risk",
        ],
    ) {
        "exploratory".to_string()
    } else if has_any(
        lower,
        &["less obvious", "adjacent", "bridge", "adventurous"],
    ) {
        "assertive".to_string()
    } else if has_any(lower, &["keep", "gently", "familiar"]) {
        "gentle".to_string()
    } else {
        "assertive".to_string()
    }
}

fn detect_user_steer(lower: &str) -> Vec<String> {
    let mut values = Vec::new();
    for needle in [
        "keep",
        "make this",
        "less obvious",
        "more obvious",
        "bridge",
        "why",
        "explain",
        "more nocturnal",
        "brighter",
        "heavier",
        "softer",
        "more adventurous",
        "more familiar",
        "smoother transition",
        "sharper contrast",
    ] {
        if lower.contains(needle) {
            values.push(needle.to_string());
        }
    }
    values
}

fn detect_exclusions(prompt: &str) -> Vec<String> {
    prompt
        .split(&[',', ';'][..])
        .filter_map(|segment| {
            let trimmed = segment.trim();
            if trimmed.to_ascii_lowercase().starts_with("avoid ")
                || trimmed.to_ascii_lowercase().starts_with("no ")
                || trimmed.to_ascii_lowercase().starts_with("without ")
            {
                Some(trimmed.to_string())
            } else {
                None
            }
        })
        .collect()
}

fn detect_sequencing_notes(lower: &str) -> Vec<String> {
    let mut values = Vec::new();
    if has_any(lower, &["trickling", "gradual", "not abruptly"]) {
        values.push("Avoid a genre cliff between phases.".to_string());
    }
    if lower.contains("middle third") {
        values.push("The middle phase should break obvious picks.".to_string());
    }
    if lower.contains("keep the ache") {
        values.push("Preserve emotional sting while softening the surface.".to_string());
    }
    if has_any(lower, &["leave this scene", "path from", "bridge from"]) {
        values.push(
            "Make the pivot legible with intermediate adjacency, not a blind jump.".to_string(),
        );
    }
    if values.is_empty() {
        values.push("Maintain a readable arc instead of random jumps.".to_string());
    }
    values
}

fn detect_opening_descriptors(lower: &str) -> Vec<String> {
    let mut values = Vec::new();
    if has_any(lower, &["fire", "storm", "sprint"]) {
        values.push("charged".to_string());
    }
    if lower.contains("edm") {
        values.push("synthetic".to_string());
    }
    if values.is_empty() {
        values.push("searching".to_string());
    }
    values
}

fn detect_landing_descriptors(lower: &str) -> Vec<String> {
    let mut values = Vec::new();
    if has_any(lower, &["lofi", "chill", "calm"]) {
        values.push("cool".to_string());
    }
    if has_any(lower, &["forgives", "ache", "bedroom"]) {
        values.push("tender".to_string());
    }
    if lower.contains("cover") {
        values.push("reinterpretive".to_string());
    }
    if values.is_empty() {
        values.push("resolved".to_string());
    }
    values
}

fn confidence_notes_for_prompt(lower: &str, entities: &[String]) -> Vec<String> {
    let mut values = Vec::new();
    if entities.is_empty() {
        values.push("No explicit artist or track entities were detected; Lyra is leaning on inferred vibe language.".to_string());
    }
    if !lower.contains("into") && !lower.contains("to") {
        values.push(
            "Destination energy is inferred because the prompt does not state an explicit landing."
                .to_string(),
        );
    }
    if has_any(
        lower,
        &["bridge", "adjacent", "less obvious", "leave this scene"],
    ) {
        values.push("This prompt implies a route choice, so Lyra may offer alternate directions instead of one supposedly final answer.".to_string());
    }
    values
}

fn heuristic_confidence(prompt: &str) -> f64 {
    let words = prompt.split_whitespace().count() as f64;
    (0.46 + (words.min(16.0) / 40.0)).clamp(0.46, 0.82)
}

fn build_graph_context(
    conn: &Connection,
    intent: &PlaylistIntent,
) -> HashMap<String, GraphAffinity> {
    let mut context: HashMap<String, GraphAffinity> = HashMap::new();
    for entity in intent.explicit_entities.iter().take(2) {
        for related in oracle::get_related_artists(entity, 8, conn) {
            let key = related.name.to_ascii_lowercase();
            let candidate = GraphAffinity {
                score: related.connection_strength as f64,
                connection_type: related.connection_type,
                source_entity: entity.clone(),
            };
            match context.get(&key) {
                Some(existing) if existing.score >= candidate.score => {}
                _ => {
                    context.insert(key, candidate);
                }
            }
        }
    }
    context
}

fn energy_value(label: &str) -> f64 {
    match label {
        "high" => 0.82,
        "low" => 0.28,
        _ => 0.54,
    }
}

fn prompt_phase_shape(intent: &PlaylistIntent) -> [PromptPhaseShape; 4] {
    let lower = intent.prompt.to_ascii_lowercase();
    let mut phases = [PromptPhaseShape::default(); 4];
    for (needle, shape) in [
        (
            "fire",
            PromptPhaseShape {
                energy: 0.12,
                tension: 0.1,
                novelty: 0.04,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "storm",
            PromptPhaseShape {
                energy: 0.14,
                tension: 0.12,
                novelty: 0.05,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "sprint",
            PromptPhaseShape {
                energy: 0.16,
                tension: 0.08,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "ache",
            PromptPhaseShape {
                valence: -0.1,
                warmth: 0.04,
                space: 0.05,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "forgives",
            PromptPhaseShape {
                valence: 0.08,
                warmth: 0.1,
                space: 0.06,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "melancholy",
            PromptPhaseShape {
                valence: -0.08,
                space: 0.1,
                warmth: 0.04,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "late-night",
            PromptPhaseShape {
                valence: -0.04,
                warmth: 0.05,
                space: 0.12,
                novelty: 0.05,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "nocturnal",
            PromptPhaseShape {
                valence: -0.03,
                warmth: 0.04,
                space: 0.1,
                novelty: 0.04,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "chill",
            PromptPhaseShape {
                energy: -0.1,
                tension: -0.08,
                warmth: 0.08,
                space: 0.08,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "lofi",
            PromptPhaseShape {
                energy: -0.08,
                warmth: 0.1,
                space: 0.06,
                novelty: 0.06,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "static",
            PromptPhaseShape {
                tension: 0.06,
                space: 0.04,
                novelty: 0.04,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "human",
            PromptPhaseShape {
                warmth: 0.06,
                space: 0.04,
                novelty: 0.03,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "clean",
            PromptPhaseShape {
                warmth: -0.04,
                space: -0.02,
                novelty: -0.04,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "rougher",
            PromptPhaseShape {
                tension: 0.05,
                warmth: 0.03,
                novelty: 0.08,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "warmer",
            PromptPhaseShape {
                warmth: 0.08,
                valence: 0.03,
                ..PromptPhaseShape::default()
            },
        ),
        (
            "dream",
            PromptPhaseShape {
                energy: -0.04,
                space: 0.12,
                novelty: 0.05,
                ..PromptPhaseShape::default()
            },
        ),
    ] {
        if lower.contains(needle) {
            apply_prompt_shape(&mut phases, shape);
        }
    }

    if has_any(
        &lower,
        &[
            "into",
            "eventually",
            "trickling into",
            "ends in",
            "undercurrent",
        ],
    ) {
        phases[0].energy += 0.04;
        phases[1].energy -= 0.02;
        phases[2].space += 0.06;
        phases[3].warmth += 0.06;
        phases[3].tension -= 0.08;
    }
    if has_any(
        &lower,
        &[
            "leave this scene",
            "different world",
            "exit",
            "out of this canon",
        ],
    ) {
        phases[1].novelty += 0.08;
        phases[2].novelty += 0.12;
        phases[2].space += 0.06;
        phases[3].space += 0.08;
    }
    phases
}

fn apply_prompt_shape(phases: &mut [PromptPhaseShape; 4], shape: PromptPhaseShape) {
    let weights = [0.95_f64, 0.72, 0.86, 0.58];
    for (index, phase) in phases.iter_mut().enumerate() {
        let weight = weights[index];
        phase.energy += shape.energy * weight;
        phase.valence += shape.valence * weight;
        phase.tension += shape.tension * weight;
        phase.warmth += shape.warmth * weight;
        phase.space += shape.space * weight;
        phase.novelty += shape.novelty * weight;
    }
}

fn select_arc_template(intent: &PlaylistIntent, behavior: &RoleBehavior) -> ArcTemplateSpec {
    let lower_prompt = intent.prompt.to_ascii_lowercase();
    if intent
        .texture_descriptors
        .iter()
        .any(|value| value.contains("night"))
        || lower_prompt.contains("late-night")
        || lower_prompt.contains("night drive")
    {
        ArcTemplateSpec {
            template_id: "night_drive",
            labels: ["depart", "cruise", "coast", "arrive"],
            energy: [0.36, 0.52, 0.46, 0.28],
            valence: [0.34, 0.4, 0.44, 0.48],
            tension: [0.52, 0.58, 0.44, 0.3],
            warmth: [0.42, 0.48, 0.56, 0.62],
            space: [0.58, 0.66, 0.74, 0.82],
        }
    } else if intent
        .emotional_arc
        .iter()
        .any(|value| value.contains("ache"))
        || lower_prompt.contains("forgives")
    {
        ArcTemplateSpec {
            template_id: "heartbreak",
            labels: ["anger", "crash", "bottom", "light"],
            energy: [0.62, 0.48, 0.22, 0.36],
            valence: [0.24, 0.18, 0.22, 0.48],
            tension: [0.74, 0.62, 0.34, 0.18],
            warmth: [0.38, 0.42, 0.5, 0.64],
            space: [0.34, 0.42, 0.78, 0.7],
        }
    } else if behavior.role == "coach"
        || lower_prompt.contains("fire")
        || lower_prompt.contains("storm")
    {
        ArcTemplateSpec {
            template_id: "catharsis",
            labels: ["tension", "climb", "aftermath", "peace"],
            energy: [0.76, 0.86, 0.5, 0.28],
            valence: [0.38, 0.42, 0.46, 0.58],
            tension: [0.62, 0.84, 0.42, 0.18],
            warmth: [0.3, 0.34, 0.46, 0.6],
            space: [0.28, 0.34, 0.58, 0.74],
        }
    } else {
        ArcTemplateSpec {
            template_id: "slow_burn",
            labels: ["intro", "build", "sustain", "resolve"],
            energy: [0.3, 0.48, 0.62, 0.4],
            valence: [0.42, 0.5, 0.6, 0.64],
            tension: [0.34, 0.46, 0.52, 0.28],
            warmth: [0.42, 0.52, 0.66, 0.72],
            space: [0.44, 0.52, 0.58, 0.7],
        }
    }
}

fn template_value(values: [f64; 4], index: usize) -> f64 {
    values[index.min(values.len() - 1)]
}

fn phase_summary(
    intent: &PlaylistIntent,
    template_id: &str,
    idx: usize,
    prompt_pressure: PromptPhaseShape,
) -> String {
    let pressure_line = if prompt_pressure.novelty >= 0.08 {
        Some(
            "The prompt pressure here is asking for a real detour, not just cleaner similarity."
                .to_string(),
        )
    } else if prompt_pressure.space >= 0.08 {
        Some("The prompt is pushing this phase toward more air and afterimage.".to_string())
    } else if prompt_pressure.warmth >= 0.08 {
        Some("The prompt is asking this phase to get warmer and more human.".to_string())
    } else {
        None
    };
    match (template_id, idx) {
        ("heartbreak", 0) => pressure_line.unwrap_or_else(|| {
            "Open with the sting still near the surface instead of dodging it.".to_string()
        }),
        ("heartbreak", 2) => pressure_line.unwrap_or_else(|| {
            "Let the floor drop out so the route earns its recovery.".to_string()
        }),
        ("night_drive", 1) => pressure_line.unwrap_or_else(|| {
            "Keep the motion hypnotic while the scene widens around it.".to_string()
        }),
        ("catharsis", 0) => pressure_line.unwrap_or_else(|| {
            "Start with pressure already in the room so the arc feels authored, not polite."
                .to_string()
        }),
        ("catharsis", 2) => pressure_line.unwrap_or_else(|| {
            "Use the aftermath to keep the damage audible while the surface cools.".to_string()
        }),
        ("slow_burn", 1) => pressure_line.unwrap_or_else(|| {
            "Let the build show itself before you spend the reveal.".to_string()
        }),
        _ => match idx {
            0 => format!(
                "Open with {} energy and {} texture.",
                intent.source_energy,
                intent.opening_state.descriptors.join(", ")
            ),
            1 => format!(
                "Keep motion alive while {} starts to show.",
                intent.texture_descriptors.join(", ")
            ),
            2 => format!(
                "Bridge toward {} without dropping the emotional thread.",
                intent.destination_energy
            ),
            _ => format!(
                "Land in {} with {} descriptors still audible.",
                intent.destination_energy,
                intent.landing_state.descriptors.join(", ")
            ),
        },
    }
}

fn novelty_bias(intent: &PlaylistIntent, idx: usize, spotify_pressure: &SpotifyPressure) -> f64 {
    let base = match intent.familiarity_vs_novelty.as_str() {
        "novel leaning" if (1..=2).contains(&idx) => 0.84,
        "familiar landing" if idx == 3 => 0.34,
        _ => 0.56,
    };
    let spotify_boost = if (1..=2).contains(&idx) {
        spotify_pressure.novelty_boost
    } else if idx == 3 {
        spotify_pressure.novelty_boost * 0.4
    } else {
        0.0
    };
    (base + spotify_boost).clamp(0.0, 1.0)
}

fn graph_affinity_fit(
    candidate: &CandidateTrack,
    graph_context: &HashMap<String, GraphAffinity>,
    route_spec: Option<&RouteFlavorSpec>,
) -> f64 {
    let Some(graph) = graph_context.get(&candidate.artist_lower) else {
        return 0.36;
    };
    match route_spec.map(|spec| spec.flavor) {
        Some("safe") | Some("direct_bridge") => (0.54 + graph.score * 0.46).clamp(0.0, 1.0),
        Some("interesting") | Some("scenic") => (0.42 + graph.score * 0.38).clamp(0.0, 1.0),
        Some("dangerous") | Some("contrast") => (0.24 + graph.score * 0.24).clamp(0.0, 1.0),
        _ => (0.42 + graph.score * 0.42).clamp(0.0, 1.0),
    }
}

fn graph_reason_suffix(
    candidate: &CandidateTrack,
    graph_context: &HashMap<String, GraphAffinity>,
) -> String {
    graph_context
        .get(&candidate.artist_lower)
        .map(|graph| {
            format!(
                ", with {} graph pull from {}",
                graph.connection_type.replace('_', " "),
                graph.source_entity
            )
        })
        .unwrap_or_default()
}

fn taste_fit(candidate: &CandidateTrack, taste: &TasteProfile) -> f64 {
    if taste.dimensions.is_empty() {
        return 0.52;
    }
    let mut total = 0.0;
    let mut count = 0.0;
    for (idx, dimension) in DIMENSIONS.iter().enumerate() {
        if let Some(value) = taste.dimensions.get(*dimension) {
            total += 1.0 - (candidate.dims[idx] - *value).abs();
            count += 1.0;
        }
    }
    if count == 0.0 {
        0.52
    } else {
        (total / count).clamp(0.0, 1.0)
    }
}

fn novelty_score(candidate: &CandidateTrack) -> f64 {
    if candidate.track.liked {
        0.28
    } else if candidate.play_count == 0 {
        0.92
    } else {
        (1.0 / (1.0 + candidate.play_count as f64 / 6.0)).clamp(0.12, 0.88)
    }
}

fn novelty_target(label: &str) -> f64 {
    match label {
        "novel leaning" => 0.78,
        "familiar leaning" => 0.24,
        "familiar landing" => 0.34,
        _ => 0.56,
    }
}

fn phase_fit(candidate: &CandidateTrack, phase: &PlaylistPhase) -> f64 {
    let target = [
        phase.target_energy,
        phase.target_valence,
        phase.target_tension,
        0.5,
        phase.target_warmth,
        0.5,
        phase.target_space,
        0.5,
        0.5,
        0.5,
    ];
    let distance = candidate
        .dims
        .iter()
        .zip(target.iter())
        .map(|(left, right)| (left - right).abs())
        .sum::<f64>();
    (1.0 - distance / 10.0).clamp(0.0, 1.0)
}

fn transition_fit(previous: Dims, next: Dims, style: &str) -> f64 {
    let distance = previous
        .iter()
        .zip(next.iter())
        .map(|(left, right)| (left - right).abs())
        .sum::<f64>()
        / 10.0;
    if style.contains("gradual") {
        (1.0 - distance).clamp(0.0, 1.0)
    } else if style.contains("contrast") {
        (0.48 + distance / 1.6).clamp(0.0, 1.0)
    } else if style.contains("charged") {
        (0.55 + distance / 2.0).clamp(0.0, 1.0)
    } else {
        (0.82 - (distance - 0.32).abs()).clamp(0.0, 1.0)
    }
}

fn transition_smoothness(
    previous: &CandidateTrack,
    next: &CandidateTrack,
    intent: &PlaylistIntent,
) -> f64 {
    let dimensional_flow = transition_fit(previous.dims, next.dims, &intent.transition_style);
    let bpm_fit = match (previous.track.bpm, next.track.bpm) {
        (Some(left), Some(right)) => (1.0 - ((left - right).abs() / 36.0)).clamp(0.0, 1.0),
        _ => 0.58,
    };
    let genre_fit = match (&previous.track.genre, &next.track.genre) {
        (Some(left), Some(right)) if !left.trim().is_empty() && !right.trim().is_empty() => {
            if left.eq_ignore_ascii_case(right) {
                1.0
            } else if left.split(&['/', ',', ';'][..]).any(|segment| {
                right
                    .to_ascii_lowercase()
                    .contains(segment.trim().to_ascii_lowercase().as_str())
            }) {
                0.72
            } else {
                0.38
            }
        }
        _ => 0.56,
    };
    let era_fit = match (&previous.track.year, &next.track.year) {
        (Some(left), Some(right)) => match (left.parse::<i32>(), right.parse::<i32>()) {
            (Ok(left_year), Ok(right_year)) => {
                (1.0 - ((left_year - right_year).abs() as f64 / 24.0)).clamp(0.0, 1.0)
            }
            _ => 0.56,
        },
        _ => 0.56,
    };
    (dimensional_flow * 0.54 + bpm_fit * 0.2 + genre_fit * 0.16 + era_fit * 0.1).clamp(0.0, 1.0)
}

fn optimize_sequence_order(
    ordered: Vec<ComposedPlaylistTrack>,
    candidates: &[CandidateTrack],
    intent: &PlaylistIntent,
) -> Vec<ComposedPlaylistTrack> {
    if ordered.len() < 3 {
        return ordered
            .into_iter()
            .enumerate()
            .map(|(position, mut track)| {
                track.position = position;
                track
            })
            .collect();
    }

    let mut optimized = ordered;
    for _ in 0..2 {
        let mut changed = false;
        let mut index = 1usize;
        while index + 1 < optimized.len() {
            if optimized[index].phase_key != optimized[index + 1].phase_key {
                index += 1;
                continue;
            }
            let baseline = local_transition_window(&optimized, candidates, intent, index);
            let mut trial = optimized.clone();
            trial.swap(index, index + 1);
            let swapped = local_transition_window(&trial, candidates, intent, index);
            if swapped > baseline + 0.02 {
                optimized = trial;
                changed = true;
                index += 2;
            } else {
                index += 1;
            }
        }
        if !changed {
            break;
        }
    }

    optimized
        .into_iter()
        .enumerate()
        .map(|(position, mut track)| {
            track.position = position;
            track
        })
        .collect()
}

fn local_transition_window(
    ordered: &[ComposedPlaylistTrack],
    candidates: &[CandidateTrack],
    intent: &PlaylistIntent,
    index: usize,
) -> f64 {
    let start = index.saturating_sub(1);
    let end = (index + 2).min(ordered.len().saturating_sub(1));
    let mut total = 0.0;
    let mut count = 0.0;
    for pair_index in start + 1..=end {
        let Some(previous) = candidate_for_track(candidates, ordered[pair_index - 1].track.id)
        else {
            continue;
        };
        let Some(next) = candidate_for_track(candidates, ordered[pair_index].track.id) else {
            continue;
        };
        total += transition_smoothness(previous, next, intent);
        count += 1.0;
    }
    if count == 0.0 {
        0.0
    } else {
        total / count
    }
}

fn candidate_for_track(candidates: &[CandidateTrack], track_id: i64) -> Option<&CandidateTrack> {
    candidates
        .iter()
        .find(|candidate| candidate.track.id == track_id)
}

fn top_aligned_dimensions(
    candidate: &CandidateTrack,
    taste: &TasteProfile,
    limit: usize,
) -> Vec<String> {
    let mut aligned = DIMENSIONS
        .iter()
        .enumerate()
        .filter_map(|(index, dimension)| {
            taste
                .dimensions
                .get(*dimension)
                .map(|value| (1.0 - (candidate.dims[index] - *value).abs(), *dimension))
        })
        .collect::<Vec<_>>();
    aligned.sort_by(|left, right| right.0.partial_cmp(&left.0).unwrap_or(Ordering::Equal));
    aligned
        .into_iter()
        .take(limit)
        .filter(|(score, _)| *score >= 0.66)
        .map(|(_, dimension)| dimension_label(dimension))
        .collect()
}

fn dominant_dimensions(candidate: &CandidateTrack, limit: usize) -> Vec<String> {
    let mut weighted = DIMENSIONS
        .iter()
        .enumerate()
        .map(|(index, dimension)| {
            (
                (candidate.dims[index] - 0.5).abs(),
                *dimension,
                candidate.dims[index],
            )
        })
        .collect::<Vec<_>>();
    weighted.sort_by(|left, right| right.0.partial_cmp(&left.0).unwrap_or(Ordering::Equal));
    weighted
        .into_iter()
        .take(limit)
        .filter(|(distance, _, _)| *distance >= 0.14)
        .map(|(_, dimension, value)| {
            if value >= 0.5 {
                format!("high {}", dimension_label(dimension))
            } else {
                format!("low {}", dimension_label(dimension))
            }
        })
        .collect()
}

fn dimension_label(dimension: &str) -> String {
    match dimension {
        "energy" => "energy".to_string(),
        "valence" => "light".to_string(),
        "tension" => "tension".to_string(),
        "density" => "density".to_string(),
        "warmth" => "warmth".to_string(),
        "movement" => "pulse".to_string(),
        "space" => "space".to_string(),
        "rawness" => "roughness".to_string(),
        "complexity" => "complexity".to_string(),
        "nostalgia" => "afterimage".to_string(),
        other => other.to_string(),
    }
}

fn entity_bonus(candidate: &CandidateTrack, entities: &[String]) -> f64 {
    if entities.is_empty() {
        return 0.4;
    }
    if entities.iter().any(|entity| {
        candidate.artist_lower.contains(entity) || candidate.title_lower.contains(entity)
    }) {
        1.0
    } else {
        0.18
    }
}

fn vibe_guard_fit(
    candidate: &CandidateTrack,
    intent: &PlaylistIntent,
    behavior: &RoleBehavior,
) -> f64 {
    if !behavior.protect_vibe {
        return 0.5;
    }
    let mut score: f64 = 0.5;
    if intent.emotional_arc.iter().any(|value| value == "ache") {
        score += (1.0 - (candidate.dims[1] - 0.34).abs()).clamp(0.0, 1.0) * 0.2;
        score += (1.0 - (candidate.dims[4] - 0.52).abs()).clamp(0.0, 1.0) * 0.15;
    }
    if has_any(
        &intent.prompt.to_ascii_lowercase(),
        &["keep", "without losing", "stay in this mood"],
    ) {
        score += (1.0 - (candidate.dims[9] - 0.56).abs()).clamp(0.0, 1.0) * 0.15;
    }
    score.clamp(0.0, 1.0)
}

fn sideways_fit(
    candidate: &CandidateTrack,
    intent: &PlaylistIntent,
    behavior: &RoleBehavior,
) -> f64 {
    if !behavior.tempt_sideways {
        return 0.4;
    }
    let novelty = novelty_score(candidate);
    let texture_shift = candidate.dims[7];
    let appetite = if intent.familiarity_vs_novelty == "novel leaning" {
        0.72
    } else {
        0.52
    };
    (1.0 - (novelty - appetite).abs() + texture_shift * 0.2).clamp(0.0, 1.0)
}

fn deep_cut_pressure(
    candidate: &CandidateTrack,
    intent: &PlaylistIntent,
    route_spec: Option<&RouteFlavorSpec>,
    spotify_pressure: &SpotifyPressure,
) -> f64 {
    let novelty = novelty_score(candidate);
    let inverse_familiarity = (1.0 - (candidate.play_count as f64 / 12.0).min(1.0)).clamp(0.0, 1.0);
    let roughness = candidate.dims[7];
    let warmth = candidate.dims[4];
    let lower = intent.prompt.to_ascii_lowercase();
    let prompt_wants_detour = has_any(
        &lower,
        &[
            "less obvious",
            "not the canon",
            "out of this canon",
            "different world",
            "rewarding risk",
            "deeper cut",
            "rougher",
            "more human",
        ],
    );
    let route_appetite = match route_spec.map(|spec| spec.flavor) {
        Some("safe") | Some("direct_bridge") => 0.28,
        Some("interesting") | Some("scenic") => 0.58,
        Some("dangerous") | Some("contrast") => 0.84,
        _ if prompt_wants_detour || spotify_pressure.canon_resistance >= 0.12 => 0.72,
        _ => 0.46,
    } + spotify_pressure.novelty_boost * 0.6;
    let texture_bonus = if has_any(
        &lower,
        &["rougher", "more human", "less polished", "lose the gloss"],
    ) {
        (roughness * 0.7 + warmth * 0.3).clamp(0.0, 1.0)
    } else {
        roughness
    };
    let spotify_artist_bonus = if spotify_pressure
        .missing_world_artist_keys
        .contains(&candidate.artist_lower)
        || spotify_pressure
            .anchor_artist_keys
            .contains(&candidate.artist_lower)
    {
        0.1
    } else {
        0.0
    };
    ((1.0 - ((novelty * 0.7 + inverse_familiarity * 0.3) - route_appetite.clamp(0.0, 1.0)).abs()
        + texture_bonus * 0.18)
        + spotify_artist_bonus)
        .clamp(0.0, 1.0)
}

fn reason_summary(
    candidate: &CandidateTrack,
    phase: &PlaylistPhase,
    fit_score: f64,
    _behavior: &RoleBehavior,
    taste: &TasteProfile,
) -> String {
    let placement = if fit_score >= 0.82 {
        "locks into"
    } else if fit_score >= 0.68 {
        "belongs in"
    } else {
        "still earns"
    };
    let texture_line = if candidate.dims[7] >= 0.58 {
        "rougher surface"
    } else if candidate.dims[4] >= 0.62 {
        "warmer edge"
    } else if candidate.dims[6] >= 0.62 {
        "more open air"
    } else {
        "cleaner frame"
    };
    let aligned = top_aligned_dimensions(candidate, taste, 2);
    let dimensional_hook = dominant_dimensions(candidate, 1)
        .into_iter()
        .next()
        .unwrap_or_else(|| texture_line.to_string());
    if !aligned.is_empty() {
        format!(
            "{} {} {} with a {:.0}% fit, keeps the {}, and lines up with your {} bias.",
            candidate.track.title,
            placement,
            phase.label,
            fit_score * 100.0,
            dimensional_hook,
            aligned.join(" + ")
        )
    } else {
        format!(
            "{} {} {} with a {:.0}% fit and keeps the {} Lyra is leaning on.",
            candidate.track.title,
            placement,
            phase.label,
            fit_score * 100.0,
            dimensional_hook
        )
    }
}

fn descriptor_phrase(candidate: &CandidateTrack, intent: &PlaylistIntent) -> String {
    if candidate.track.genre.as_deref().unwrap_or("").is_empty() {
        intent.texture_descriptors.join(", ")
    } else {
        format!(
            "{} and {}",
            candidate.track.genre.clone().unwrap_or_default(),
            intent.texture_descriptors.join(", ")
        )
    }
}

fn intent_phrase(phase_label: &str) -> &'static str {
    match phase_label {
        "Ignition" => "opening",
        "Opening run" => "forward motion",
        "Bridge" => "turn",
        _ => "landing",
    }
}

fn transition_sentence(previous: Dims, next: Dims, style: &str) -> String {
    let change = next[0] - previous[0];
    let pulse_change = (next[5] - previous[5]).abs();
    let roughness_change = (next[7] - previous[7]).abs();
    if style.contains("gradual") {
        if roughness_change >= 0.18 {
            "The handoff softens the temperature while letting more grain through.".to_string()
        } else {
            format!(
                "Transitions with a {:.0}% energy {} so the arc cools instead of snapping.",
                change.abs() * 100.0,
                if change < 0.0 { "drop" } else { "lift" }
            )
        }
    } else if style.contains("contrast") {
        if pulse_change <= 0.14 {
            "This is the sharper pivot: the surface changes fast, but the pulse survives it."
                .to_string()
        } else {
            "This step risks more by changing the surface and the push at the same time."
                .to_string()
        }
    } else {
        "Keeps the move readable by changing one pressure point before the next one.".to_string()
    }
}

fn evidence_for_candidate(
    candidate: &CandidateTrack,
    phase: &PlaylistPhase,
    taste: &TasteProfile,
    graph_context: &HashMap<String, GraphAffinity>,
    spotify_pressure: &SpotifyPressure,
) -> Vec<String> {
    let mut evidence = vec![
        format!(
            "Phase target energy {:.2}; track energy {:.2}.",
            phase.target_energy, candidate.dims[0]
        ),
        format!(
            "Phase target warmth {:.2}; track warmth {:.2}.",
            phase.target_warmth, candidate.dims[4]
        ),
        format!(
            "Track play count in local history: {}.",
            candidate.play_count
        ),
    ];
    let dominant = dominant_dimensions(candidate, 2);
    if !dominant.is_empty() {
        evidence.push(format!(
            "Most distinctive local dimensions: {}.",
            dominant.join(" and ")
        ));
    }
    if let Some(bpm) = candidate.track.bpm {
        evidence.push(format!("Tempo signal sits near {:.0} BPM.", bpm));
    }
    if let Some(genre) = candidate
        .track
        .genre
        .as_deref()
        .filter(|genre| !genre.trim().is_empty())
    {
        evidence.push(format!("Genre tag contributes scene color: {}.", genre));
    }
    if let Some(graph) = graph_context.get(&candidate.artist_lower) {
        evidence.push(format!(
            "Artist graph evidence: {} is connected to {} via {} ({:.0}% strength).",
            candidate.track.artist,
            graph.source_entity,
            graph.connection_type.replace('_', " "),
            graph.score * 100.0
        ));
    }
    let novelty = novelty_score(candidate);
    if novelty >= 0.78 {
        evidence.push(format!(
            "Local obscurity pressure is high here ({:.0}% novelty with {} prior plays).",
            novelty * 100.0,
            candidate.play_count
        ));
    } else if novelty <= 0.34 {
        evidence.push(format!(
            "This sits closer to the familiar lane ({:.0}% novelty with {} prior plays).",
            novelty * 100.0,
            candidate.play_count
        ));
    }
    if !taste.dimensions.is_empty() {
        let aligned = top_aligned_dimensions(candidate, taste, 2);
        evidence.push(format!(
            "Taste confidence {:.0}% contributed to reranking.",
            taste.confidence * 100.0
        ));
        if !aligned.is_empty() {
            evidence.push(format!(
                "Closest taste alignment lands on {}.",
                aligned.join(" + ")
            ));
        }
    }
    if spotify_pressure.available && !spotify_pressure.cue_lines.is_empty() {
        evidence.push(format!(
            "Spotify pressure contributed context here: {}",
            spotify_pressure.cue_lines[0]
        ));
    }
    evidence
}

fn explicit_hits(candidate: &CandidateTrack, entities: &[String]) -> Vec<String> {
    entities
        .iter()
        .filter(|entity| {
            candidate.artist_lower.contains(entity.as_str())
                || candidate.title_lower.contains(entity.as_str())
        })
        .cloned()
        .collect()
}

fn inferred_notes(
    candidate: &CandidateTrack,
    phase: &PlaylistPhase,
    intent: &PlaylistIntent,
    behavior: &RoleBehavior,
    graph_context: &HashMap<String, GraphAffinity>,
    spotify_pressure: &SpotifyPressure,
) -> Vec<String> {
    let mut notes = vec![format!("Assigned to {} from local score fit.", phase.label)];
    if !intent.texture_descriptors.is_empty() {
        notes.push(format!(
            "Texture interpretation leaned on {}.",
            intent.texture_descriptors.join(", ")
        ));
    }
    if !behavior.silent_inference_ok {
        notes.push(
            "Lyra is surfacing inference explicitly because this role should not hide uncertainty."
                .to_string(),
        );
    }
    if candidate.play_count == 0 {
        notes.push("Boosted as a fresh library path with no prior playback history.".to_string());
    } else if candidate.play_count <= 2 && !candidate.track.liked {
        notes.push(
            "Still reads like a deep-cut lane in local history rather than a library staple."
                .to_string(),
        );
    } else if candidate.play_count >= 8 {
        notes.push("Lyra reads this as a more familiar anchor, so it is being used on purpose rather than by accident.".to_string());
    }
    if let Some(graph) = graph_context.get(&candidate.artist_lower) {
        notes.push(format!(
            "Graph adjacency helped: {} keeps a live link to {} through {} evidence.",
            candidate.track.artist,
            graph.source_entity,
            graph.connection_type.replace('_', " ")
        ));
    }
    if is_scene_exit_prompt(&intent.prompt) {
        notes.push(format!(
            "Scene-exit logic kept the {} family legible while changing the room around it.",
            candidate.scene_family
        ));
    }
    if spotify_pressure
        .missing_world_artist_keys
        .contains(&candidate.artist_lower)
    {
        notes.push(
            "Spotify history says this world still matters, so Lyra is allowing that older pressure to stay alive while the owned library catches up."
                .to_string(),
        );
    } else if spotify_pressure.available && spotify_pressure.recoverable_missing_count > 0 {
        notes.push(
            "Spotify-derived missing-world pressure is nudging Lyra away from a purely local-canon answer."
                .to_string(),
        );
    }
    notes
}

fn title_case(value: &str) -> String {
    value
        .split_whitespace()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn score_weights(role: &str, prompt_role: &str) -> (f64, f64, f64, f64, f64) {
    match (role, prompt_role) {
        ("oracle", _) => (0.34, 0.14, 0.14, 0.24, 0.14),
        ("coach", _) => (0.34, 0.22, 0.18, 0.14, 0.12),
        ("copilot", _) => (0.38, 0.16, 0.18, 0.14, 0.14),
        _ => (0.42, 0.18, 0.14, 0.16, 0.10),
    }
}

fn build_bridge_phase_plan(
    intent: &PlaylistIntent,
    track_count: usize,
    behavior: &RoleBehavior,
    spotify_pressure: &SpotifyPressure,
) -> Vec<PlaylistPhase> {
    let mut phases = build_phase_plan(intent, track_count.max(5), behavior, spotify_pressure);
    let labels = [
        ("source", "Departure"),
        ("slip", "Slip"),
        ("hinge", "Hinge"),
        ("glow", "Arrival shadow"),
        ("arrive", "Arrival"),
    ];
    phases.truncate(labels.len());
    for (idx, phase) in phases.iter_mut().enumerate() {
        phase.key = labels[idx].0.to_string();
        phase.label = labels[idx].1.to_string();
        phase.summary = match idx {
            0 => "Start close enough to the source scene to keep the DNA audible.".to_string(),
            1 => "Loosen the obvious markers without losing pulse or ache.".to_string(),
            2 => "Use a hinge track that makes the next emotional language believable.".to_string(),
            3 => "Let the destination mood appear before the genre label fully flips.".to_string(),
            _ => "Arrive at the new scene with the route still legible in hindsight.".to_string(),
        };
    }
    phases
}

fn bridge_labels(prompt: &str, intent: &PlaylistIntent) -> (String, String) {
    let lower = prompt.to_ascii_lowercase();
    let entities = &intent.explicit_entities;
    if entities.len() >= 2 {
        return (entities[0].clone(), entities[1].clone());
    }
    if let Some(rest) = lower.split("bridge from ").nth(1) {
        if let Some((left, right)) = rest.split_once(" into ") {
            return (title_case(left.trim()), title_case(right.trim()));
        }
        if let Some((left, right)) = rest.split_once(" to ") {
            return (title_case(left.trim()), title_case(right.trim()));
        }
    }
    (
        entities
            .first()
            .cloned()
            .unwrap_or_else(|| intent.opening_state.descriptors.join(" ")),
        if !intent.landing_state.descriptors.is_empty() {
            intent.landing_state.descriptors.join(" ")
        } else {
            intent.destination_energy.clone()
        },
    )
}

fn bridge_step_role(index: usize, len: usize) -> String {
    match index {
        0 => "anchor".to_string(),
        i if i + 1 >= len => "arrival".to_string(),
        i if i == len / 2 => "hinge".to_string(),
        _ => "handoff".to_string(),
    }
}

fn bridge_distance(index: usize, len: usize, reverse: bool) -> f64 {
    if len <= 1 {
        return 0.0;
    }
    let progress = index as f64 / (len.saturating_sub(1) as f64);
    if reverse {
        1.0 - progress
    } else {
        progress
    }
}

fn intent_for_route_flavor(intent: &PlaylistIntent, spec: &RouteFlavorSpec) -> PlaylistIntent {
    let mut flavored = intent.clone();
    match spec.flavor {
        "direct_bridge" | "safe" => {
            flavored.familiarity_vs_novelty = "familiar leaning".to_string();
            flavored.discovery_aggressiveness = "gentle".to_string();
            flavored.transition_style = "adjacent bridge".to_string();
        }
        "scenic" | "interesting" => {
            flavored.familiarity_vs_novelty = "novel leaning".to_string();
            flavored.discovery_aggressiveness = "assertive".to_string();
            flavored.transition_style = "guided drift".to_string();
        }
        "contrast" | "dangerous" => {
            flavored.familiarity_vs_novelty = "novel leaning".to_string();
            flavored.discovery_aggressiveness = "exploratory".to_string();
            flavored.transition_style = "contrast cut".to_string();
        }
        _ => {}
    }
    flavored
}

fn choose_bridge_flavor(prompt: &str, taste_memory: &TasteMemorySnapshot) -> &'static str {
    let lower = prompt.to_ascii_lowercase();
    if lower.contains("scenic") {
        "scenic"
    } else if lower.contains("contrast")
        || lower.contains("rewarding risk")
        || route_memory_pressure(Some(&bridge_route_specs()[2]), taste_memory) >= 0.12
    {
        "contrast"
    } else if route_memory_pressure(Some(&bridge_route_specs()[1]), taste_memory) >= 0.08 {
        "scenic"
    } else {
        "direct_bridge"
    }
}

fn choose_discovery_flavor(
    prompt: &str,
    intent: &PlaylistIntent,
    taste_memory: &TasteMemorySnapshot,
    spotify_pressure: &SpotifyPressure,
) -> &'static str {
    let lower = prompt.to_ascii_lowercase();
    if lower.contains("safe") {
        return "safe";
    }
    if lower.contains("dangerous") || lower.contains("rewarding risk") {
        return "dangerous";
    }
    if lower.contains("interesting")
        || lower.contains("less obvious")
        || lower.contains("adjacent but not the canon")
    {
        return "interesting";
    }
    if is_scene_exit_prompt(prompt) {
        if lower.contains("canon") || lower.contains("different world") {
            return if spotify_pressure.scene_exit_bias >= 0.16
                && !intent.explicit_entities.is_empty()
            {
                "dangerous"
            } else {
                "interesting"
            };
        }
        if lower.contains("leave this genre") {
            return "dangerous";
        }
    }
    let dangerous_pressure = route_memory_pressure(Some(&discovery_route_specs()[2]), taste_memory);
    let interesting_pressure =
        route_memory_pressure(Some(&discovery_route_specs()[1]), taste_memory);
    if spotify_pressure.scene_exit_bias >= 0.16
        && is_scene_exit_prompt(prompt)
        && !intent.explicit_entities.is_empty()
        && intent.discovery_aggressiveness != "gentle"
    {
        "dangerous"
    } else if spotify_pressure.canon_resistance >= 0.14
        && intent.familiarity_vs_novelty != "familiar leaning"
    {
        "interesting"
    } else if dangerous_pressure >= 0.14 && intent.discovery_aggressiveness == "exploratory" {
        "dangerous"
    } else if interesting_pressure >= 0.08 || intent.familiarity_vs_novelty == "novel leaning" {
        "interesting"
    } else {
        "safe"
    }
}

fn route_memory_pressure(
    route_spec: Option<&RouteFlavorSpec>,
    taste_memory: &TasteMemorySnapshot,
) -> f64 {
    let Some(spec) = route_spec else {
        return 0.0;
    };
    let mut pressure = 0.0;
    for route in taste_memory.route_preferences.iter().take(6) {
        let matches_lane = match (spec.flavor, route.route_kind.as_str()) {
            ("direct_bridge", "safe") | ("safe", "safe") => true,
            ("scenic", "interesting") | ("interesting", "interesting") => true,
            ("contrast", "dangerous") | ("dangerous", "dangerous") => true,
            (left, right) if left == right => true,
            _ => false,
        };
        if !matches_lane {
            continue;
        }
        pressure += match route.outcome.as_str() {
            "accepted" => 0.24 * route.confidence,
            "rejected" => -0.22 * route.confidence,
            _ => 0.08 * route.confidence,
        };
    }
    pressure.clamp(-0.32, 0.32)
}

fn is_scene_exit_prompt(prompt: &str) -> bool {
    let lower = prompt.to_ascii_lowercase();
    has_any(
        &lower,
        &[
            "three exits",
            "three ways to leave",
            "leave this scene",
            "same pulse, different world",
            "leave this genre, keep this wound",
            "stay in the ache, lose the gloss",
            "get me out of this canon",
            "scene exit",
        ],
    )
}

fn adjacency_signals_for_transition(
    previous: Option<Dims>,
    current: Dims,
    intent: &PlaylistIntent,
    spec: &RouteFlavorSpec,
) -> Vec<AdjacencySignal> {
    let previous = previous.unwrap_or(current);
    let emotional_delta =
        1.0 - ((current[1] - previous[1]).abs() + (current[2] - previous[2]).abs()) / 2.0;
    let texture_delta =
        1.0 - ((current[3] - previous[3]).abs() + (current[6] - previous[6]).abs()) / 2.0;
    let rhythm_delta = 1.0 - (current[5] - previous[5]).abs();
    let roughness_delta = 1.0 - (current[7] - previous[7]).abs();
    let melodic_familiarity = 1.0 - (current[9] - previous[9]).abs();
    let vocal_distance =
        1.0 - ((current[6] - previous[6]).abs() * 0.55 + (current[4] - previous[4]).abs() * 0.45);
    let scene_delta = 1.0
        - ((current[3] - previous[3]).abs() * 0.3
            + (current[8] - previous[8]).abs() * 0.4
            + (current[4] - previous[4]).abs() * 0.3);
    let lineage_delta =
        1.0 - ((current[9] - previous[9]).abs() * 0.6 + (current[8] - previous[8]).abs() * 0.4);
    let risk_value =
        ((current[8] - previous[8]).abs() * 0.5 + spec.risk_weight * 0.5).clamp(0.0, 1.0);
    vec![
        AdjacencySignal {
            dimension: "emotional continuity".to_string(),
            relation: if emotional_delta >= 0.58 {
                "preserve".to_string()
            } else if spec.contrast_weight >= 0.7 {
                "contrast".to_string()
            } else {
                "shift".to_string()
            },
            score: emotional_delta.clamp(0.0, 1.0),
            note: if intent.emotional_arc.iter().any(|value| value.contains("ache")) {
                "This keeps the wound in frame even if the surface changes.".to_string()
            } else {
                "The emotional temperature stays legible across the handoff.".to_string()
            },
        },
        AdjacencySignal {
            dimension: "texture continuity".to_string(),
            relation: if texture_delta >= 0.6 {
                "preserve".to_string()
            } else {
                "surface shift".to_string()
            },
            score: texture_delta.clamp(0.0, 1.0),
            note: "Texture is being managed separately from mood so the route does not flatten into similarity.".to_string(),
        },
        AdjacencySignal {
            dimension: "rhythmic continuity".to_string(),
            relation: if rhythm_delta >= 0.6 {
                "keep pulse".to_string()
            } else {
                "drop pulse".to_string()
            },
            score: rhythm_delta.clamp(0.0, 1.0),
            note: "This is where Lyra decides whether the pulse survives the jump.".to_string(),
        },
        AdjacencySignal {
            dimension: "production roughness".to_string(),
            relation: if roughness_delta >= 0.62 {
                "same polish lane".to_string()
            } else {
                "polish shift".to_string()
            },
            score: roughness_delta.clamp(0.0, 1.0),
            note: "Lyra is tracking gloss versus human pressure, not just genre tags.".to_string(),
        },
        AdjacencySignal {
            dimension: "melodic familiarity".to_string(),
            relation: if melodic_familiarity >= 0.66 {
                "afterimage holds".to_string()
            } else {
                "melody shifts".to_string()
            },
            score: melodic_familiarity.clamp(0.0, 1.0),
            note: "This estimates whether the route still carries the melodic afterimage, even when the wrapper changes.".to_string(),
        },
        AdjacencySignal {
            dimension: "vocal intimacy".to_string(),
            relation: if vocal_distance >= 0.62 {
                "same distance".to_string()
            } else {
                "camera moves".to_string()
            },
            score: vocal_distance.clamp(0.0, 1.0),
            note: "Lyra is using warmth and space as a proxy for whether the voice feels whispered close or pushed out into the room.".to_string(),
        },
        AdjacencySignal {
            dimension: "scene adjacency".to_string(),
            relation: if scene_delta >= 0.62 {
                "same neighborhood".to_string()
            } else if spec.contrast_weight >= 0.7 {
                "side-door exit".to_string()
            } else {
                "scene drift".to_string()
            },
            score: scene_delta.clamp(0.0, 1.0),
            note: "Scene is inferred from density, complexity, and warmth so the route can move sideways without pretending genre tags are enough.".to_string(),
        },
        AdjacencySignal {
            dimension: "era / lineage".to_string(),
            relation: if lineage_delta >= 0.64 {
                "shared lineage".to_string()
            } else {
                "lineage break".to_string()
            },
            score: lineage_delta.clamp(0.0, 1.0),
            note: "Lineage is estimated from nostalgia and complexity as a proxy for whether the step feels inherited or newly arrived.".to_string(),
        },
        AdjacencySignal {
            dimension: "risk / reward".to_string(),
            relation: if spec.risk_weight >= 0.7 {
                "rewarding risk".to_string()
            } else if spec.risk_weight <= 0.2 {
                "safe hold".to_string()
            } else {
                "measured risk".to_string()
            },
            score: risk_value,
            note: "Risk is grounded in what changes between steps, not in decorative language.".to_string(),
        },
    ]
}

fn preserve_change_notes(
    candidate: &CandidateTrack,
    intent: &PlaylistIntent,
    spec: &RouteFlavorSpec,
) -> (Vec<String>, Vec<String>) {
    let mut preserves = Vec::new();
    let mut changes = Vec::new();
    if intent
        .emotional_arc
        .iter()
        .any(|value| value.contains("ache"))
    {
        preserves.push("keeps the ache".to_string());
    }
    if intent.prompt.to_ascii_lowercase().contains("pulse") || candidate.dims[5] >= 0.48 {
        preserves.push("keeps the pulse alive".to_string());
    }
    if candidate.dims[7] >= 0.54 {
        changes.push("drops gloss for rougher grain".to_string());
    } else {
        changes.push("keeps the surface relatively clean".to_string());
    }
    if spec.flavor == "contrast" || spec.flavor == "dangerous" {
        changes.push("changes tension faster than texture".to_string());
    } else if spec.flavor == "scenic" || spec.flavor == "interesting" {
        changes.push("moves scenes before it changes emotional temperature".to_string());
    } else {
        preserves.push("holds the emotional temperature steady".to_string());
    }
    preserves.sort();
    preserves.dedup();
    changes.sort();
    changes.dedup();
    (preserves, changes)
}

fn route_variant_summary(
    spec: &RouteFlavorSpec,
    intent: &PlaylistIntent,
    spotify_pressure: &SpotifyPressure,
) -> RouteVariantSummary {
    let prompt_lower = intent.prompt.to_ascii_lowercase();
    let scene_exit = is_scene_exit_prompt(&intent.prompt);
    let (logic, preserves, changes, risk_note, reward_note) = match spec.flavor {
        "safe" | "direct_bridge" => (
            format!(
                "This is the safest path because it preserves emotional temperature and scene adjacency before it spends novelty ({:.0}% continuity, {:.0}% scene).",
                spec.continuity_weight * 100.0,
                spec.scene_weight * 100.0
            ),
            vec!["emotional continuity".to_string(), "familiar landmarks".to_string()],
            vec!["surface polish only".to_string()],
            "Low risk: the bridge may feel a little too polite if you want rupture.".to_string(),
            "Reward is legibility: the route holds together on first listen.".to_string(),
        ),
        "dangerous" | "contrast" => (
            format!(
                "This is the riskier path because it shares tension or pulse more than texture ({:.0}% contrast, {:.0}% novelty).",
                spec.contrast_weight * 100.0,
                spec.novelty_weight * 100.0
            ),
            vec!["live-wire tension".to_string()],
            vec!["texture family".to_string(), "scene assumptions".to_string()],
            "Higher risk: it can read as a jump if the hinge misses.".to_string(),
            "Reward is afterimage: less related on paper, closer to the feeling you are chasing.".to_string(),
        ),
        _ => (
            format!(
                "This is the interesting path because it exits the obvious lane without giving up the emotional thread ({:.0}% novelty, {:.0}% continuity).",
                spec.novelty_weight * 100.0,
                spec.continuity_weight * 100.0
            ),
            vec!["ache or pulse".to_string()],
            vec!["obviousness".to_string(), "surface gloss".to_string()],
            "Measured risk: novelty rises once trust is established.".to_string(),
            "Reward is a more tastemaker-like route instead of a nearest-neighbor answer.".to_string(),
        ),
    };
    let mut preserves = preserves;
    if intent
        .emotional_arc
        .iter()
        .any(|value| value.contains("ache"))
    {
        preserves.push("ache".to_string());
    }
    if prompt_lower.contains("pulse") {
        preserves.push("pulse".to_string());
    }
    let logic = if scene_exit && matches!(spec.flavor, "safe" | "interesting" | "dangerous") {
        let target_worlds = target_scene_families(intent, spec).join(", ");
        match spec.flavor {
            "safe" => format!("{logic} It exits the scene by changing polish first and leaving the emotional weather mostly intact. Target world: {target_worlds}."),
            "dangerous" => format!("{logic} It leaves the scene on purpose by breaking texture family while holding one deeper wire alive. Target world: {target_worlds}."),
            _ => format!("{logic} It leaves the canon lane without dropping the wound, pulse, or afterimage that made the scene worth leaving carefully. Target world: {target_worlds}."),
        }
    } else if spotify_pressure.available && spotify_pressure.recoverable_missing_count > 0 {
        format!(
            "{logic} Spotify history says part of this world mattered before the owned library fully caught up, so Lyra is biasing toward a truer missing-world route instead of a local-canon loop."
        )
    } else {
        logic
    };
    let risk_note = if scene_exit && spec.flavor == "safe" {
        "Low risk: you may leave the room but still feel too close to the same canon furniture."
            .to_string()
    } else {
        risk_note
    };
    let reward_note = if scene_exit && spec.flavor == "interesting" {
        "Reward is a real exit: same pressure, different world.".to_string()
    } else {
        reward_note
    };
    RouteVariantSummary {
        flavor: spec.flavor.to_string(),
        label: spec.label.to_string(),
        logic,
        preserves,
        changes,
        risk_note,
        reward_note,
    }
}

fn route_score_floor(route_spec: Option<&RouteFlavorSpec>) -> f64 {
    match route_spec.map(|spec| spec.flavor) {
        Some("safe") | Some("direct_bridge") => 0.38,
        Some("interesting") | Some("scenic") => 0.34,
        Some("dangerous") | Some("contrast") => 0.28,
        _ => 0.32,
    }
}

fn route_shape_fit(
    candidate: &CandidateTrack,
    previous_dims: Option<Dims>,
    intent: &PlaylistIntent,
    spec: &RouteFlavorSpec,
    spotify_pressure: &SpotifyPressure,
) -> f64 {
    let familiarity = if candidate.track.liked {
        0.92
    } else if candidate.play_count > 1 {
        0.66
    } else {
        0.24
    };
    let novelty = novelty_score(candidate);
    let roughness = candidate.dims[7];
    let scene_color =
        ((candidate.dims[8] + candidate.dims[9] + candidate.dims[4]) / 3.0).clamp(0.0, 1.0);
    let continuity = previous_dims
        .map(|previous| transition_fit(previous, candidate.dims, &intent.transition_style))
        .unwrap_or(0.58);
    let contrast = previous_dims
        .map(|previous| {
            ((candidate.dims[0] - previous[0]).abs()
                + (candidate.dims[1] - previous[1]).abs()
                + (candidate.dims[3] - previous[3]).abs()
                + (candidate.dims[7] - previous[7]).abs())
                / 4.0
        })
        .unwrap_or(0.3)
        .clamp(0.0, 1.0);
    let live_wire = previous_dims
        .map(|previous| {
            let pulse_hold = 1.0 - (candidate.dims[5] - previous[5]).abs();
            let ache_hold = 1.0 - (candidate.dims[2] - previous[2]).abs();
            ((pulse_hold + ache_hold) / 2.0).clamp(0.0, 1.0)
        })
        .unwrap_or(0.56);
    let target_scenes = target_scene_families(intent, spec);
    let scene_target_fit = if target_scenes
        .iter()
        .any(|family| family == &candidate.scene_family)
    {
        1.0
    } else if is_scene_exit_prompt(&intent.prompt)
        && target_scenes
            .iter()
            .flat_map(|family| adjacent_scene_families(family))
            .any(|family| family == candidate.scene_family)
    {
        0.72
    } else {
        0.22
    };

    let spotify_world_bonus = if spotify_pressure
        .missing_world_artist_keys
        .contains(&candidate.artist_lower)
        || spotify_pressure
            .anchor_artist_keys
            .contains(&candidate.artist_lower)
    {
        0.12
    } else {
        0.0
    };

    match spec.flavor {
        "safe" | "direct_bridge" => (continuity * 0.42
            + familiarity * 0.3
            + (1.0 - novelty) * 0.16
            + live_wire * 0.12
            + scene_target_fit * 0.08
            + spotify_world_bonus * 0.08)
            .clamp(0.0, 1.0),
        "interesting" | "scenic" => {
            let curiosity =
                (novelty * 0.34 + roughness * 0.22 + scene_color * 0.14).clamp(0.0, 1.0);
            (continuity * 0.2
                + live_wire * 0.18
                + curiosity * 0.48
                + scene_target_fit * 0.14
                + spotify_world_bonus * 0.12
                + spotify_pressure.scene_exit_bias * 0.08)
                .clamp(0.0, 1.0)
        }
        "dangerous" | "contrast" => (contrast * 0.32
            + novelty * 0.24
            + live_wire * 0.24
            + (1.0 - familiarity) * 0.1
            + roughness * 0.1
            + scene_target_fit * 0.08
            + spotify_world_bonus * 0.1
            + spotify_pressure.canon_resistance * 0.06)
            .clamp(0.0, 1.0),
        _ => 0.58,
    }
}

fn discovery_directions(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> Vec<DiscoveryDirection> {
    discovery_route_specs()
        .iter()
        .map(|spec| {
            let direction_intent = intent_for_route_flavor(intent, spec);
            let phases = build_phase_plan(
                &direction_intent,
                (track_count / 3).max(3),
                runtime.behavior,
                runtime.spotify_pressure,
            );
            let tracks = sequence_tracks(
                runtime.candidates,
                &phases,
                &direction_intent,
                (track_count / 3).max(3),
                SequenceContext {
                    taste: runtime.taste,
                    behavior: runtime.behavior,
                    taste_memory: runtime.taste_memory,
                    spotify_pressure: runtime.spotify_pressure,
                    graph_context: runtime.graph_context,
                    route_spec: Some(spec),
                },
            );
            let variant = route_variant_summary(spec, &direction_intent, runtime.spotify_pressure);
            let why = select_narrative(
                &NarrativeRequest {
                    prompt,
                    action_label: "discovery",
                    intent: &direction_intent,
                    behavior: runtime.behavior,
                    variants: std::slice::from_ref(&variant),
                    tracks: &tracks,
                },
                runtime.provider_status,
                runtime.provider_configs,
            )
            .unwrap_or_else(|| variant.logic.clone());
            DiscoveryDirection {
                flavor: spec.flavor.to_string(),
                label: spec.label.to_string(),
                description: variant.logic.clone(),
                tracks: tracks.clone(),
                why,
                preserves: variant.preserves.clone(),
                changes: variant.changes.clone(),
                adjacency_signals: tracks
                    .first()
                    .and_then(|track| {
                        runtime
                            .candidates
                            .iter()
                            .find(|candidate| candidate.track.id == track.track.id)
                    })
                    .map(|candidate| {
                        adjacency_signals_for_transition(
                            None,
                            candidate.dims,
                            &direction_intent,
                            spec,
                        )
                    })
                    .unwrap_or_default(),
                risk_note: variant.risk_note.clone(),
                reward_note: variant.reward_note.clone(),
            }
        })
        .collect()
}

fn build_lyra_framing(
    prompt: &str,
    intent: &PlaylistIntent,
    action: &ComposerAction,
    provider_status: &ComposerProviderStatus,
    behavior: &RoleBehavior,
    taste_memory: &TasteMemorySnapshot,
    spotify_pressure: &SpotifyPressure,
    route_comparison: Option<RouteComparison>,
) -> LyraFraming {
    let posture = posture_for(action, &behavior.role);
    let detail_depth = detail_depth_for(behavior, action, intent);
    let confidence = confidence_voice(intent, provider_status, action);
    let fallback = fallback_voice(provider_status);
    let challenge = challenge_line(prompt, intent, action, behavior);
    let memory = taste_memory_hint(intent, taste_memory);
    let lyra_read = lyra_read_surface(prompt, intent, action, taste_memory, spotify_pressure);

    LyraFraming {
        posture,
        detail_depth,
        lead: lead_line(intent, action, behavior),
        rationale: rationale_line(intent, action, behavior, spotify_pressure),
        presence_note: presence_note(intent, action, behavior),
        challenge,
        vibe_guard: vibe_guard_line(intent, action, behavior),
        confidence,
        fallback,
        route_comparison,
        lyra_read,
        sideways_temptations: sideways_temptations(intent, action, behavior),
        memory_hint: memory,
        next_nudges: next_nudges(intent, action),
    }
}

fn posture_for(action: &ComposerAction, role: &str) -> ResponsePosture {
    match (action, role) {
        (ComposerAction::Explain, _) | (_, "oracle") => ResponsePosture::Revelatory,
        (ComposerAction::Steer, _) | (_, "copilot") => ResponsePosture::Collaborative,
        (_, "coach") => ResponsePosture::Refining,
        _ => ResponsePosture::Suggestive,
    }
}

fn detail_depth_for(
    behavior: &RoleBehavior,
    action: &ComposerAction,
    intent: &PlaylistIntent,
) -> DetailDepth {
    match (
        behavior.explanation_depth.as_str(),
        action,
        intent.explanation_depth.as_str(),
    ) {
        ("deep", _, _) | (_, ComposerAction::Explain, _) | (_, ComposerAction::Bridge, "deep") => {
            DetailDepth::Deep
        }
        ("light", _, _) => DetailDepth::Short,
        _ => DetailDepth::Medium,
    }
}

fn confidence_voice(
    intent: &PlaylistIntent,
    provider_status: &ComposerProviderStatus,
    action: &ComposerAction,
) -> ConfidenceVoice {
    let level = if intent.confidence >= 0.8 {
        "high"
    } else if intent.confidence >= 0.58 {
        "medium"
    } else {
        "low"
    };
    let phrasing = match (level, action, provider_status.provider_kind.as_str()) {
        ("high", ComposerAction::Bridge, _) => {
            "The route feels convincing enough to push forward without over-hedging.".to_string()
        }
        ("high", _, _) => "Lyra has a strong read on the move here.".to_string(),
        ("medium", _, "deterministic") => {
            "The shape is believable, but the language parse is still heuristic rather than semantic certainty.".to_string()
        }
        ("medium", _, _) => "There is a clear direction here, but Lyra is leaving room for adjacent revisions.".to_string(),
        ("low", ComposerAction::Discovery, _) => {
            "There are several plausible exits from this prompt, so Lyra is keeping the answer plural.".to_string()
        }
        ("low", _, _) => "The prompt points in a real direction, but not sharply enough to fake certainty.".to_string(),
        _ => "Lyra has a partial read and is keeping the route steerable.".to_string(),
    };

    ConfidenceVoice {
        level: level.to_string(),
        phrasing,
        should_offer_alternatives: level != "high"
            || matches!(action, ComposerAction::Bridge | ComposerAction::Discovery),
    }
}

fn presence_note(
    intent: &PlaylistIntent,
    action: &ComposerAction,
    behavior: &RoleBehavior,
) -> Option<String> {
    if behavior.role == "copilot" || behavior.role == "coach" {
        Some(match action {
            ComposerAction::Steer => {
                "Lyra is staying loyal to the arc you already built and only pushing where the route got too safe.".to_string()
            }
            _ => format!(
                "Lyra is reading the hidden shape of the sentence, not just the nouns: {} stays central.",
                intent.emotional_arc.join(", ")
            ),
        })
    } else {
        None
    }
}

fn vibe_guard_line(
    intent: &PlaylistIntent,
    action: &ComposerAction,
    behavior: &RoleBehavior,
) -> Option<String> {
    if !behavior.protect_vibe {
        return None;
    }
    Some(match action {
        ComposerAction::Steer => "Lyra is protecting the emotional spine before it spends novelty on side moves.".to_string(),
        ComposerAction::Bridge => "Lyra is guarding the pulse and ache so the bridge bends instead of snapping.".to_string(),
        ComposerAction::Discovery => "Even the stranger exits keep one live wire from the original mood.".to_string(),
        _ => format!(
            "Lyra is protecting {} so the route does not solve the prompt by breaking its core feeling.",
            intent.emotional_arc.join(", ")
        ),
    })
}

fn sideways_temptations(
    intent: &PlaylistIntent,
    action: &ComposerAction,
    behavior: &RoleBehavior,
) -> Vec<String> {
    if !behavior.tempt_sideways {
        return Vec::new();
    }
    match action {
        ComposerAction::Discovery => vec![
            "Slip sideways into rougher texture before changing the emotional language.".to_string(),
            "Keep the same ache, but trade gloss for grain.".to_string(),
        ],
        ComposerAction::Bridge => vec![
            "Take the more interesting road through confessional warmth instead of the cleanest handoff.".to_string(),
        ],
        ComposerAction::Playlist | ComposerAction::Steer if intent.familiarity_vs_novelty != "familiar leaning" => vec![
            "There is a slightly stranger route here if you want Lyra to trade polish for nerve.".to_string(),
        ],
        _ => Vec::new(),
    }
}

fn taste_memory_hint(
    intent: &PlaylistIntent,
    taste_memory: &TasteMemorySnapshot,
) -> Option<String> {
    if let Some(line) = taste_memory.summary_lines.first() {
        Some(line.clone())
    } else if !intent.user_steer.is_empty() {
        Some(format!(
            "Recent steer language is clustering around {}.",
            intent.user_steer.join(", ")
        ))
    } else {
        None
    }
}

fn intelligence_recency_note(timestamp: &str) -> String {
    let parsed = chrono::DateTime::parse_from_rfc3339(timestamp)
        .map(|value| value.with_timezone(&chrono::Utc))
        .ok();
    match parsed.map(|value| chrono::Utc::now() - value) {
        Some(delta) if delta <= chrono::Duration::hours(4) => "in the last few hours".to_string(),
        Some(delta) if delta <= chrono::Duration::days(2) => "recently".to_string(),
        Some(_) => "a while ago".to_string(),
        None => "recently".to_string(),
    }
}

fn lyra_read_surface(
    prompt: &str,
    intent: &PlaylistIntent,
    action: &ComposerAction,
    taste_memory: &TasteMemorySnapshot,
    spotify_pressure: &SpotifyPressure,
) -> LyraReadSurface {
    let lower = prompt.to_ascii_lowercase();
    let mut cues = Vec::new();
    if let Some(preference) = taste_memory.remembered_preferences.first() {
        cues.push(format!(
            "Recent pressure leans {} on {}.",
            preference.preferred_pole, preference.axis_label
        ));
    }
    if let Some(route) = taste_memory.route_preferences.first() {
        cues.push(match route.outcome.as_str() {
            "accepted" => format!(
                "Recent route feedback favored the {} lane {}.",
                route.route_kind,
                intelligence_recency_note(&route.observed_at)
            ),
            "rejected" => format!(
                "Recent route feedback pushed away from the {} lane {}.",
                route.route_kind,
                intelligence_recency_note(&route.observed_at)
            ),
            _ => format!(
                "Route pressure has been drifting toward {} {}.",
                route.route_kind,
                intelligence_recency_note(&route.observed_at)
            ),
        });
    }
    if is_scene_exit_prompt(prompt) {
        cues.push("This reads like a scene exit: keep one live wire, leave the room.".to_string());
    }
    if let Some(cue) = spotify_pressure.cue_lines.first() {
        cues.push(cue.clone());
    }
    if lower.contains("clean") || lower.contains("polished") {
        cues.push(
            "This is less about sadness than about lowering gloss and increasing intimacy."
                .to_string(),
        );
    }
    cues.truncate(3);

    let summary = if is_scene_exit_prompt(prompt) {
        "Lyra sees an exit problem here: preserve the pressure, trade the world around it."
            .to_string()
    } else if lower.contains("ache") && lower.contains("pulse") {
        "Lyra reads the ask as keep the ache, keep the pulse, spend obviousness instead."
            .to_string()
    } else if lower.contains("clean") || lower.contains("polished") {
        "Lyra reads the target as rougher and more human, not simply darker.".to_string()
    } else if spotify_pressure.available && spotify_pressure.recoverable_missing_count > 0 {
        "Lyra reads a missing-world pressure here: part of the answer lives in what your Spotify history remembers but your owned library still undercovers."
            .to_string()
    } else if matches!(action, ComposerAction::Steer) {
        "Lyra reads this as revision pressure, not a new destination.".to_string()
    } else {
        format!(
            "Lyra reads the current pressure as {} moving toward {}.",
            intent.source_energy, intent.destination_energy
        )
    };

    let confidence_note = if taste_memory.remembered_preferences.is_empty()
        && taste_memory.route_preferences.is_empty()
    {
        "This read is mostly from the current prompt; memory pressure is still light.".to_string()
    } else {
        "This read blends the current prompt with recent pressure only. It stays provisional and overrideable.".to_string()
    };

    LyraReadSurface {
        summary,
        cues,
        confidence_note,
    }
}

fn fallback_voice(provider_status: &ComposerProviderStatus) -> FallbackVoice {
    if provider_status.provider_kind == "deterministic" {
        FallbackVoice {
            active: true,
            label: "Heuristic read".to_string(),
            message: "Lyra is being direct about fallback mode: the language read came from local heuristics, while retrieval and sequencing still stayed grounded in the library.".to_string(),
        }
    } else {
        FallbackVoice {
            active: false,
            label: "Provider-assisted read".to_string(),
            message: "A language provider helped interpret the prompt, but Lyra kept the actual selection logic local.".to_string(),
        }
    }
}

fn lead_line(intent: &PlaylistIntent, action: &ComposerAction, behavior: &RoleBehavior) -> String {
    match action {
        ComposerAction::Bridge => format!(
            "{} Lyra is threading {} into {} without dropping {}.",
            if intent.transition_style.contains("contrast") {
                "This wants a risk-managed hinge, not a blind jump."
            } else {
                "This wants a hinge, not a leap."
            },
            intent.opening_state.descriptors.join(", "),
            intent.landing_state.descriptors.join(", "),
            intent.emotional_arc.join(", ")
        ),
        ComposerAction::Discovery => {
            if intent.familiarity_vs_novelty == "novel leaning" {
                "There is more than one believable exit here, and the interesting one should not be hidden behind the safe lane.".to_string()
            } else {
                "There is more than one good way out of this scene, so Lyra is treating discovery as directions instead of one neat answer.".to_string()
            }
        }
        ComposerAction::Steer => {
            if intent.user_steer.iter().any(|value| value.contains("ache")) {
                "Lyra is treating this as a revision pass. The job is to keep the ache and change the surface around it.".to_string()
            } else {
                "Lyra is treating this as a revision pass, not a fresh command. The goal is to keep the spine and move the surface.".to_string()
            }
        }
        ComposerAction::Explain => "There is structure under this move. Lyra is naming the pressure points instead of waving at 'vibes'.".to_string(),
        ComposerAction::Playlist => match behavior.role.as_str() {
            "coach" => {
                if intent.prompt.to_ascii_lowercase().contains("pulse") {
                    "Lyra has a read on the mood, but it is also sharpening what needs to stay alive underneath it.".to_string()
                } else {
                    "Lyra has a read on the mood, but it is also sharpening what the prompt is really asking for.".to_string()
                }
            }
            _ => "Lyra is shaping this like a journey, not a bucket of matching tracks.".to_string(),
        },
    }
}

fn rationale_line(
    intent: &PlaylistIntent,
    action: &ComposerAction,
    behavior: &RoleBehavior,
    spotify_pressure: &SpotifyPressure,
) -> String {
    match action {
        ComposerAction::Bridge => format!(
            "The priority is legibility: keep {} audible early, let {} emerge late, and use the middle to make the turn feel earned.",
            intent.opening_state.descriptors.join(", "),
            intent.landing_state.descriptors.join(", ")
        ),
        ComposerAction::Discovery => {
            if is_scene_exit_prompt(&intent.prompt) {
                "Lyra is treating this as an exit problem, not a similarity problem: what stays constant, what changes on purpose, and how far the scene can move before the mood snaps.".to_string()
            } else if intent.prompt.to_ascii_lowercase().contains("canon") {
                "Lyra is separating the exits so the obvious canon lane stays visible but does not get to dominate the answer.".to_string()
            } else {
                "Lyra is separating familiar, adjacent, and scene-breaking exits so the user can choose what kind of risk feels right.".to_string()
            }
        }
        ComposerAction::Steer => format!(
            "Because this is {} mode, Lyra preserves the emotional thread while moving obviousness, contrast, and texture on purpose.",
            behavior.role
        ),
        ComposerAction::Explain => "The explanation stays concrete: bridge logic, emotional pressure, transition readability, and where uncertainty still lives.".to_string(),
        ComposerAction::Playlist => format!(
            "The sequence prioritizes {} over generic genre matching{}, so the arc can feel authored instead of auto-filled.",
            intent.emotional_arc.join(", "),
            if spotify_pressure.available && spotify_pressure.recoverable_missing_count > 0 {
                " and leans away from the parts of your world that Spotify says still go missing locally"
            } else {
                ""
            }
        ),
    }
}

fn challenge_line(
    prompt: &str,
    intent: &PlaylistIntent,
    action: &ComposerAction,
    behavior: &RoleBehavior,
) -> Option<String> {
    let lower = prompt.to_ascii_lowercase();
    if is_scene_exit_prompt(prompt) && lower.contains("canon") {
        Some("You asked for an exit, but part of the wording is still hugging canon. Lyra can give the polite version, or the truer one that actually leaves the room.".to_string())
    } else if is_scene_exit_prompt(prompt) && lower.contains("pulse") {
        Some("Lyra can preserve the pulse cleanly, but the more truthful exit may roughen the surface before the world changes.".to_string())
    } else if matches!(action, ComposerAction::Steer)
        && has_any(&lower, &["clean", "polished", "obvious", "safe"])
    {
        Some("If you want the truer route, Lyra should spend the easy landmarks before it spends the ache.".to_string())
    } else if matches!(action, ComposerAction::Steer) {
        Some("If you want this less obvious, Lyra will protect the ache first and sacrifice the easy landmarks second.".to_string())
    } else if matches!(action, ComposerAction::Discovery)
        && intent.familiarity_vs_novelty == "familiar leaning"
    {
        Some("The safe lane is here if you need it, but the more honest answer is probably the interesting one.".to_string())
    } else if behavior.role == "coach"
        && intent.explicit_entities.is_empty()
        && !has_any(&lower, &["into", "from", "after"])
    {
        Some("The prompt has mood, but not much destination. Lyra can move now, but a sharper landing would produce a stranger and better route.".to_string())
    } else if has_any(&lower, &["obvious", "canon"]) {
        Some("Lyra is intentionally resisting the safest canon picks here.".to_string())
    } else {
        None
    }
}

fn next_nudges(intent: &PlaylistIntent, action: &ComposerAction) -> Vec<String> {
    match action {
        ComposerAction::Bridge => vec![
            "Make the hinge darker.".to_string(),
            "Keep the same destination but roughen the middle.".to_string(),
            "Stay closer to the source scene.".to_string(),
        ],
        ComposerAction::Discovery => vec![
            "Push this less obvious.".to_string(),
            "Keep the pulse but go rougher.".to_string(),
            "Make one route warmer and one harsher.".to_string(),
        ],
        ComposerAction::Steer => vec![
            "Less obvious in the middle.".to_string(),
            "Darker and softer.".to_string(),
            "Rougher, less polished.".to_string(),
        ],
        ComposerAction::Explain => vec![
            "Compare this route against a sharper pivot.".to_string(),
            "Explain the hinge in more detail.".to_string(),
        ],
        ComposerAction::Playlist => {
            let mut nudges = vec![
                "Make it less obvious.".to_string(),
                "Push it more nocturnal.".to_string(),
            ];
            if intent.discovery_aggressiveness == "gentle" {
                nudges.push("Take a bigger risk in the middle.".to_string());
            } else {
                nudges.push("Keep more familiar landmarks.".to_string());
            }
            nudges
        }
    }
}

fn route_comparison_for_phases(phases: &[PlaylistPhase]) -> RouteComparison {
    let hinge = phases
        .get(phases.len().saturating_div(2))
        .map(|phase| phase.label.clone())
        .unwrap_or_else(|| "middle".to_string());
    RouteComparison {
        headline: "Arc logic".to_string(),
        summary: format!(
            "The route works because the early phases establish trust, then {} changes the pressure before the landing resolves it.",
            hinge
        ),
        variants: vec![
            RouteVariantSummary {
                flavor: "safe".to_string(),
                label: "Safe".to_string(),
                logic: "Stay close to the opening emotional temperature.".to_string(),
                preserves: vec!["core mood".to_string()],
                changes: vec!["surface detail".to_string()],
                risk_note: "Low risk, lower surprise.".to_string(),
                reward_note: "Cleanest route to a stable landing.".to_string(),
            },
            RouteVariantSummary {
                flavor: "interesting".to_string(),
                label: "Interesting".to_string(),
                logic: "Push the middle into a less obvious lane before resolving.".to_string(),
                preserves: vec!["ache or pulse".to_string()],
                changes: vec!["obviousness".to_string()],
                risk_note: "Measured risk in the middle third.".to_string(),
                reward_note: "Feels authored instead of autopiloted.".to_string(),
            },
            RouteVariantSummary {
                flavor: "dangerous".to_string(),
                label: "Dangerous".to_string(),
                logic: "Let the hinge announce itself instead of hiding the pivot.".to_string(),
                preserves: vec!["one live wire".to_string()],
                changes: vec!["texture family".to_string()],
                risk_note: "Higher chance of a visible jump.".to_string(),
                reward_note: "Best path when repetition is the real enemy.".to_string(),
            },
        ],
    }
}

fn route_comparison_for_bridge(bridge: &BridgePath) -> RouteComparison {
    let hinge = bridge
        .steps
        .iter()
        .find(|step| step.role == "hinge")
        .map(|step| format!("{} by {}", step.track.title, step.track.artist))
        .unwrap_or_else(|| "the midpoint hinge".to_string());
    RouteComparison {
        headline: "Why this bridge holds".to_string(),
        summary: format!(
            "Lyra is leaning on {} to keep the pulse from snapping while the destination mood comes into focus.",
            hinge
        ),
        variants: bridge.variants.clone(),
    }
}

fn route_comparison_for_discovery(route: &DiscoveryRoute) -> RouteComparison {
    RouteComparison {
        headline: if route.scene_exit {
            "How the exits differ".to_string()
        } else {
            "How the routes differ".to_string()
        },
        summary: if route.scene_exit {
            format!(
                "Lyra treated this as a scene exit. The {} lane currently reads truest, while the others stay visible so you can choose how much world-change the mood can survive.",
                route.primary_flavor
            )
        } else {
            format!(
                "Lyra separated the routes so one stays nearest the source, one slips sideways into adjacency, and one breaks scene while protecting the pulse. The {} lane currently reads truest.",
                route.primary_flavor
            )
        },
        variants: route.variants.clone(),
    }
}

fn uncertainty_notes(
    intent: &PlaylistIntent,
    provider_status: &ComposerProviderStatus,
    behavior: &RoleBehavior,
) -> Vec<String> {
    let mut notes = intent.confidence_notes.clone();
    if provider_status.provider_kind == "deterministic" {
        notes.push("Heuristic fallback shaped the language parse; Lyra kept retrieval and sequencing deterministic.".to_string());
    }
    if !behavior.silent_inference_ok {
        notes.push(
            "This role exposes interpretation seams instead of silently smoothing them over."
                .to_string(),
        );
    }
    if behavior.prefer_revision {
        notes.push(
            "Lyra is treating this as a revisable working route, not a final immutable answer."
                .to_string(),
        );
    }
    notes
}

fn alternatives_for_action(intent: &PlaylistIntent, action: &ComposerAction) -> Vec<String> {
    match action {
        ComposerAction::Bridge => vec![
            "Take a slower hinge through warmer, more confessional tracks.".to_string(),
            "Keep the same destination but pivot through sharper synthetic contrast.".to_string(),
            "Stay closer to the source scene and reduce the novelty jump.".to_string(),
        ],
        ComposerAction::Discovery => vec![
            "Push harder toward obscure adjacency.".to_string(),
            "Keep more familiar landmarks and soften the jump.".to_string(),
            "Preserve pulse while changing texture first.".to_string(),
        ],
        ComposerAction::Explain => vec![
            "Ask Lyra to defend the bridge instead of the destination.".to_string(),
            "Request deeper evidence instead of summary explanation.".to_string(),
        ],
        _ if intent.prompt_role == "copilot" || intent.prompt_role == "coach" => vec![
            "Revise the middle so it gets less obvious without collapsing the ache.".to_string(),
            "Keep the same shape but brighten the landing.".to_string(),
        ],
        _ => Vec::new(),
    }
}

fn template_narrative(
    intent: &PlaylistIntent,
    phases: &[PlaylistPhase],
    behavior: &RoleBehavior,
) -> String {
    format!(
        "Lyra is acting as a {} and reads this prompt as a move from {} toward {}. The sequence moves through {} and keeps {} in view without giving up {}. {}",
        behavior.role,
        intent.source_energy,
        intent.destination_energy,
        phases
            .iter()
            .map(|phase| phase.label.clone())
            .collect::<Vec<_>>()
            .join(", "),
        intent.texture_descriptors.join(", "),
        intent.emotional_arc.join(", "),
        if behavior.offer_alternatives {
            "This is a steerable draft, so Lyra keeps adjacent revisions available."
        } else {
            "Lyra is optimizing for a direct route."
        }
    )
}

fn template_bridge_narrative(
    intent: &PlaylistIntent,
    source_label: &str,
    destination_label: &str,
) -> String {
    format!(
        "Lyra treats this as a bridge problem, not a generic draft: start at {}, loosen the obvious markers, and arrive at {} through {} without losing {}.",
        source_label,
        destination_label,
        intent.texture_descriptors.join(", "),
        intent.emotional_arc.join(", ")
    )
}

fn template_discovery_narrative(intent: &PlaylistIntent) -> String {
    if is_scene_exit_prompt(&intent.prompt) {
        format!(
            "Lyra is treating this as a scene-exit problem. The routes keep {} alive while changing world, polish, and adjacency pressure on purpose.",
            intent.emotional_arc.join(", ")
        )
    } else {
        format!(
            "Lyra is offering multiple exits from the current scene so discovery stays steerable. The directions vary novelty pressure while keeping {} and {} legible.",
            intent.texture_descriptors.join(", "),
            intent.emotional_arc.join(", ")
        )
    }
}

fn template_explanation(
    intent: &PlaylistIntent,
    provider_status: &ComposerProviderStatus,
    behavior: &RoleBehavior,
) -> String {
    format!(
        "Lyra is in {} mode. It inferred a {} -> {} move with {} transition style, explanation depth {}, and provider mode {}. {}",
        behavior.role,
        intent.source_energy,
        intent.destination_energy,
        intent.transition_style,
        behavior.explanation_depth,
        provider_status.mode,
        if provider_status.provider_kind == "deterministic" {
            "Because no provider parsed the language, Lyra is exposing uncertainty instead of pretending semantic certainty."
        } else {
            "A language provider helped with interpretation, but local retrieval and sequencing remained authoritative."
        }
    )
}

fn has_any(value: &str, needles: &[&str]) -> bool {
    needles.iter().any(|needle| value.contains(needle))
}

fn lerp(start: f64, end: f64, amount: f64) -> f64 {
    start + (end - start) * amount
}

fn intent_prompt() -> &'static str {
    "You are Lyra inside Cassette. Your job is intent parsing for local-library route finding, not generic assistant chat. Obey these rules: never invent artists, tracks, or library state; never flatten scene exits or route comparisons into generic playlists; never output anything except JSON; keep confidence honest and low when language is ambiguous. Allowed enums: prompt_role = coach|copilot|recommender|oracle; source_energy and destination_energy = low|medium|high; familiarity_vs_novelty = familiar leaning|balanced|novel leaning; discovery_aggressiveness = gentle|assertive|exploratory; explanation_depth = light|balanced|deep. Use explicit_entities only when the prompt names entities that plausibly exist in the fallback parse. Return only JSON with keys: prompt_role, source_energy, destination_energy, transition_style, emotional_arc, texture_descriptors, explicit_entities, familiarity_vs_novelty, discovery_aggressiveness, user_steer, exclusions, explanation_depth, sequencing_notes, confidence_notes, confidence."
}

fn intent_user_prompt(prompt: &str, fallback: &PlaylistIntent) -> String {
    format!(
        "Prompt: {prompt}\nFallback interpretation: {}\nImprove the fallback only when the language clearly implies bridge, discovery, scene exit, steer/revision, or explanation behavior. If the wording is partial, keep the fallback structure and lower confidence instead of freelancing.\nReturn only JSON.",
        serde_json::to_string(fallback).unwrap_or_default()
    )
}

fn parse_intent_response(content: &str, fallback: &PlaylistIntent) -> Option<PlaylistIntent> {
    let json_text = extract_json_object(content)?;
    let payload: Value = serde_json::from_str(json_text).ok()?;
    let mut intent = fallback.clone();
    intent.prompt_role = payload
        .get("prompt_role")
        .and_then(Value::as_str)
        .unwrap_or(&intent.prompt_role)
        .to_string();
    intent.source_energy = payload
        .get("source_energy")
        .and_then(Value::as_str)
        .unwrap_or(&intent.source_energy)
        .to_string();
    intent.destination_energy = payload
        .get("destination_energy")
        .and_then(Value::as_str)
        .unwrap_or(&intent.destination_energy)
        .to_string();
    intent.transition_style = payload
        .get("transition_style")
        .and_then(Value::as_str)
        .unwrap_or(&intent.transition_style)
        .to_string();
    intent.emotional_arc = string_array(&payload, "emotional_arc", &intent.emotional_arc);
    intent.texture_descriptors =
        string_array(&payload, "texture_descriptors", &intent.texture_descriptors);
    intent.explicit_entities =
        string_array(&payload, "explicit_entities", &intent.explicit_entities);
    intent.familiarity_vs_novelty = payload
        .get("familiarity_vs_novelty")
        .and_then(Value::as_str)
        .unwrap_or(&intent.familiarity_vs_novelty)
        .to_string();
    intent.discovery_aggressiveness = payload
        .get("discovery_aggressiveness")
        .and_then(Value::as_str)
        .unwrap_or(&intent.discovery_aggressiveness)
        .to_string();
    intent.user_steer = string_array(&payload, "user_steer", &intent.user_steer);
    intent.exclusions = string_array(&payload, "exclusions", &intent.exclusions);
    intent.explanation_depth = payload
        .get("explanation_depth")
        .and_then(Value::as_str)
        .unwrap_or(&intent.explanation_depth)
        .to_string();
    intent.sequencing_notes = string_array(&payload, "sequencing_notes", &intent.sequencing_notes);
    intent.confidence_notes = string_array(&payload, "confidence_notes", &intent.confidence_notes);
    intent.confidence = payload
        .get("confidence")
        .and_then(Value::as_f64)
        .unwrap_or(intent.confidence)
        .clamp(0.0, 1.0);
    Some(sanitize_provider_intent(&fallback.prompt, fallback, intent))
}

fn sanitize_provider_intent(
    prompt: &str,
    fallback: &PlaylistIntent,
    mut parsed: PlaylistIntent,
) -> PlaylistIntent {
    parsed.prompt = fallback.prompt.clone();
    parsed.prompt_role = normalize_prompt_role(&parsed.prompt_role, &fallback.prompt_role);
    parsed.source_energy = normalize_energy(&parsed.source_energy, &fallback.source_energy);
    parsed.destination_energy =
        normalize_energy(&parsed.destination_energy, &fallback.destination_energy);
    parsed.familiarity_vs_novelty = normalize_novelty(
        &parsed.familiarity_vs_novelty,
        &fallback.familiarity_vs_novelty,
    );
    parsed.discovery_aggressiveness = normalize_discovery_aggressiveness(
        &parsed.discovery_aggressiveness,
        &fallback.discovery_aggressiveness,
    );
    parsed.explanation_depth =
        normalize_explanation_depth(&parsed.explanation_depth, &fallback.explanation_depth);
    parsed.transition_style =
        normalize_transition_style(prompt, &parsed.transition_style, &fallback.transition_style);
    parsed.explicit_entities.retain(|value| {
        fallback
            .explicit_entities
            .iter()
            .any(|entity| entity == value)
    });
    parsed.emotional_arc = normalized_array(parsed.emotional_arc, &fallback.emotional_arc, 5);
    parsed.texture_descriptors =
        normalized_array(parsed.texture_descriptors, &fallback.texture_descriptors, 6);
    parsed.user_steer = normalized_array(parsed.user_steer, &fallback.user_steer, 6);
    parsed.exclusions = normalized_array(parsed.exclusions, &fallback.exclusions, 5);
    parsed.sequencing_notes =
        normalized_array(parsed.sequencing_notes, &fallback.sequencing_notes, 6);
    parsed.confidence_notes =
        normalized_array(parsed.confidence_notes, &fallback.confidence_notes, 4);
    if is_scene_exit_prompt(prompt)
        && !parsed
            .sequencing_notes
            .iter()
            .any(|note| note.contains("exit"))
    {
        parsed.sequencing_notes.push(
            "Treat this as an exit route: preserve one live wire and change the room around it."
                .to_string(),
        );
    }
    parsed.confidence = if parsed.explicit_entities.len() > fallback.explicit_entities.len() {
        parsed.confidence.min(fallback.confidence)
    } else {
        parsed.confidence
    }
    .clamp(0.2, 0.88);
    parsed
}

fn normalize_prompt_role(value: &str, fallback: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "coach" | "copilot" | "recommender" | "oracle" => value.trim().to_ascii_lowercase(),
        _ => fallback.to_string(),
    }
}

fn normalize_energy(value: &str, fallback: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "low" | "medium" | "high" => value.trim().to_ascii_lowercase(),
        _ => fallback.to_string(),
    }
}

fn normalize_novelty(value: &str, fallback: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "familiar leaning" | "balanced" | "novel leaning" => value.trim().to_ascii_lowercase(),
        _ => fallback.to_string(),
    }
}

fn normalize_discovery_aggressiveness(value: &str, fallback: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "gentle" | "assertive" | "exploratory" => value.trim().to_ascii_lowercase(),
        _ => fallback.to_string(),
    }
}

fn normalize_explanation_depth(value: &str, fallback: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "light" | "balanced" | "deep" => value.trim().to_ascii_lowercase(),
        _ => fallback.to_string(),
    }
}

fn normalize_transition_style(prompt: &str, value: &str, fallback: &str) -> String {
    let normalized = value.trim().to_ascii_lowercase();
    if normalized.is_empty() {
        return fallback.to_string();
    }
    if is_scene_exit_prompt(prompt) && !normalized.contains("exit") {
        return "scene exit".to_string();
    }
    if has_any(
        &normalized,
        &[
            "gradual cooling",
            "contrast cut",
            "adjacent bridge",
            "guided drift",
            "scene exit",
        ],
    ) {
        normalized
    } else {
        fallback.to_string()
    }
}

fn normalized_array(mut values: Vec<String>, fallback: &[String], limit: usize) -> Vec<String> {
    values = values
        .into_iter()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .take(limit)
        .collect();
    if values.is_empty() {
        fallback.to_vec()
    } else {
        values.sort();
        values.dedup();
        values
    }
}

fn string_array(payload: &Value, key: &str, fallback: &[String]) -> Vec<String> {
    payload
        .get(key)
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|item| item.as_str().map(ToOwned::to_owned))
                .collect::<Vec<_>>()
        })
        .filter(|items| !items.is_empty())
        .unwrap_or_else(|| fallback.to_vec())
}

fn openai_compatible_completion(
    config: &ProviderConfig,
    provider_configs: &[ProviderConfig],
    messages: Value,
) -> Option<String> {
    let primary = endpoint_from_provider_config(config)?;
    let fallback = fallback_endpoint_from_provider_configs(config, provider_configs);
    let client = LlmClient::from_endpoints(primary, fallback);
    client.chat_completion_messages(&messages, None, 0.2)
}

fn endpoint_from_provider_config(config: &ProviderConfig) -> Option<LlmEndpointConfig> {
    let base_url = config_string(
        &config.config,
        &[
            "base_url",
            "openai_base_url",
            "openrouter_base_url",
            "groq_base_url",
        ],
    )
    .unwrap_or(match config.provider_key.as_str() {
        "openai" => "https://api.openai.com/v1",
        "openrouter" => "https://openrouter.ai/api/v1",
        "groq" => "https://api.groq.com/openai/v1",
        _ => return None,
    })
    .trim()
    .to_string();
    let model = config_string(
        &config.config,
        &[
            "model",
            "cloud_model",
            "openai_model",
            "groq_model",
            "openrouter_model",
        ],
    )?
    .trim()
    .to_string();
    let api_key = config_string(
        &config.config,
        &[
            "api_key",
            "token",
            "openai_api_key",
            "groq_api_key",
            "openrouter_api_key",
        ],
    )?
    .trim()
    .to_string();
    if base_url.is_empty() || model.is_empty() || api_key.is_empty() {
        return None;
    }
    Some(LlmEndpointConfig::new(
        config.provider_key.clone(),
        base_url,
        model,
        api_key,
    ))
}

fn fallback_endpoint_from_provider_configs(
    config: &ProviderConfig,
    provider_configs: &[ProviderConfig],
) -> Option<LlmEndpointConfig> {
    let fallback_key = match config.provider_key.as_str() {
        "groq" => "openrouter",
        "openrouter" => "groq",
        _ => return None,
    };
    let fallback_config = provider_configs
        .iter()
        .find(|candidate| candidate.provider_key == fallback_key)?;
    endpoint_from_provider_config(fallback_config)
}

fn extract_json_object(content: &str) -> Option<&str> {
    let start = content.find('{')?;
    let end = content.rfind('}')?;
    content.get(start..=end)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db;
    use std::sync::{Mutex, OnceLock};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn spotify_env_lock() -> &'static Mutex<()> {
        static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        LOCK.get_or_init(|| Mutex::new(()))
    }

    fn setup_memory_db() -> Connection {
        let conn = Connection::open_in_memory().expect("in-memory db");
        db::init_database(&conn).expect("db init");

        let artists = [
            "Brand New",
            "Midnight Circuit",
            "Glass Static",
            "Neon Chapel",
            "Warm Tape",
            "Lofi Haze",
            "Digital Ash",
            "Soft Signal",
            "Mall Ghost",
            "Analog Regret",
            "Fire Run",
            "Confession Booth",
        ];
        for artist in artists {
            conn.execute("INSERT INTO artists (name) VALUES (?1)", params![artist])
                .expect("artist");
        }
        let tracks = [
            (
                "Soco Static",
                "Brand New",
                0.46,
                0.34,
                0.62,
                0.52,
                0.44,
                0.40,
                0.32,
                0.38,
                0.56,
                0.68,
                "emo",
            ),
            (
                "Late Train Pulse",
                "Midnight Circuit",
                0.58,
                0.28,
                0.56,
                0.48,
                0.38,
                0.54,
                0.52,
                0.36,
                0.62,
                0.44,
                "electronic",
            ),
            (
                "Bedroom Static",
                "Glass Static",
                0.24,
                0.30,
                0.40,
                0.34,
                0.66,
                0.22,
                0.64,
                0.48,
                0.42,
                0.74,
                "lofi",
            ),
            (
                "Neon Confession",
                "Neon Chapel",
                0.72,
                0.48,
                0.58,
                0.70,
                0.36,
                0.78,
                0.42,
                0.28,
                0.52,
                0.34,
                "synthpop",
            ),
            (
                "Warm Analog Regret",
                "Warm Tape",
                0.36,
                0.32,
                0.44,
                0.42,
                0.82,
                0.30,
                0.58,
                0.34,
                0.46,
                0.86,
                "indie",
            ),
            (
                "Chill Undercurrent",
                "Lofi Haze",
                0.18,
                0.42,
                0.22,
                0.30,
                0.72,
                0.18,
                0.76,
                0.24,
                0.38,
                0.62,
                "lofi",
            ),
            (
                "Aggressive Shimmer",
                "Digital Ash",
                0.82,
                0.40,
                0.68,
                0.78,
                0.22,
                0.84,
                0.26,
                0.30,
                0.64,
                0.20,
                "edm",
            ),
            (
                "Eventually Forgives",
                "Soft Signal",
                0.22,
                0.54,
                0.26,
                0.32,
                0.78,
                0.20,
                0.72,
                0.22,
                0.34,
                0.80,
                "dream-pop",
            ),
            (
                "Mall Goth Sprint",
                "Mall Ghost",
                0.76,
                0.38,
                0.60,
                0.74,
                0.28,
                0.80,
                0.30,
                0.42,
                0.58,
                0.32,
                "post-punk",
            ),
            (
                "Analog Afterglow",
                "Analog Regret",
                0.34,
                0.36,
                0.32,
                0.40,
                0.84,
                0.26,
                0.66,
                0.20,
                0.40,
                0.90,
                "ambient",
            ),
            (
                "Fire Storm Trickle",
                "Fire Run",
                0.88,
                0.52,
                0.72,
                0.82,
                0.24,
                0.90,
                0.18,
                0.32,
                0.48,
                0.26,
                "edm",
            ),
            (
                "Confession Neon Booth",
                "Confession Booth",
                0.62,
                0.44,
                0.54,
                0.60,
                0.46,
                0.68,
                0.44,
                0.26,
                0.50,
                0.40,
                "art-pop",
            ),
        ];

        for (
            index,
            (
                title,
                artist,
                energy,
                valence,
                tension,
                density,
                warmth,
                movement,
                space,
                rawness,
                complexity,
                nostalgia,
                genre,
            ),
        ) in tracks.iter().enumerate()
        {
            let artist_id: i64 = conn
                .query_row(
                    "SELECT id FROM artists WHERE name = ?1",
                    params![artist],
                    |row| row.get(0),
                )
                .expect("artist id");
            conn.execute(
                "INSERT INTO tracks (artist_id, title, path, duration_seconds, imported_at) VALUES (?1, ?2, ?3, 180.0, '2026-03-08T00:00:00Z')",
                params![artist_id, title, format!("C:/Music/{index}.mp3")],
            )
            .expect("track");
            let track_id = conn.last_insert_rowid();
            conn.execute(
                "INSERT INTO track_scores (track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia, scored_at, score_version) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, '2026-03-08T00:00:00Z', 2)",
                params![track_id, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia],
            )
            .expect("score");
            conn.execute(
                "UPDATE tracks SET genre = ?1 WHERE id = ?2",
                params![genre, track_id],
            )
            .ok();
            if index % 3 == 0 {
                conn.execute(
                    "INSERT INTO playback_history (track_id, ts, context, completion_rate, skipped) VALUES (?1, '2026-03-08T00:00:00Z', 'test', 0.9, 0)",
                    params![track_id],
                )
                .expect("history");
            }
        }

        conn
    }

    fn setup_spotify_legacy_db() -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("lyra-spotify-pressure-{unique}.db"));
        let legacy = Connection::open(&path).expect("legacy db");
        legacy
            .execute_batch(
                "
                CREATE TABLE spotify_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT,
                    track TEXT,
                    album TEXT,
                    played_at TEXT,
                    ms_played INTEGER
                );
                CREATE TABLE spotify_library (
                    spotify_uri TEXT PRIMARY KEY,
                    artist TEXT NOT NULL,
                    title TEXT NOT NULL,
                    album TEXT,
                    source TEXT DEFAULT 'liked',
                    added_at TEXT
                );
                ",
            )
            .expect("spotify schema");
        legacy
            .execute(
                "INSERT INTO spotify_history (artist, track, album, played_at, ms_played)
                 VALUES ('Brand New', 'Soco Static', 'Anchor', '2026-03-08T23:30:00Z', 240000)",
                [],
            )
            .expect("history row");
        legacy
            .execute(
                "INSERT INTO spotify_history (artist, track, album, played_at, ms_played)
                 VALUES ('Brand New', 'Missing Halo', 'Anchor', '2026-03-08T23:40:00Z', 240000)",
                [],
            )
            .expect("history row 2");
        legacy
            .execute(
                "INSERT INTO spotify_library (spotify_uri, artist, title, album, source, added_at)
                 VALUES ('spotify:track:missing-halo', 'Brand New', 'Missing Halo', 'Anchor', 'liked', '2026-03-08T00:00:00Z')",
                [],
            )
            .expect("library row");
        legacy
            .execute(
                "INSERT INTO spotify_library (spotify_uri, artist, title, album, source, added_at)
                 VALUES ('spotify:track:missing-world', 'Brand New', 'Another Missing World', 'Anchor', 'liked', '2026-03-08T00:00:00Z')",
                [],
            )
            .expect("library row 2");
        path
    }

    #[test]
    fn detects_gradual_cooling_prompt() {
        let settings = SettingsPayload::default();
        let conn = setup_memory_db();
        let intent = heuristic_intent(
            &conn,
            "edm fire storm trickling into chill undercurrent of lofi covers",
            &settings,
            &TasteMemorySnapshot::default(),
        );
        assert_eq!(intent.source_energy, "high");
        assert_eq!(intent.destination_energy, "low");
        assert!(intent.transition_style.contains("gradual"));
        assert!(intent
            .texture_descriptors
            .iter()
            .any(|value| value.contains("lofi")));
    }

    #[test]
    fn extracts_json_object_from_wrapped_text() {
        let content = "here\n{\"source_energy\":\"high\"}\nthanks";
        assert_eq!(
            extract_json_object(content),
            Some("{\"source_energy\":\"high\"}")
        );
    }

    #[test]
    fn classifies_bridge_prompt_as_bridge_action() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "bridge from Brand New into late-night electronic melancholy",
            10,
            None,
        )
        .expect("compose");
        assert!(matches!(response.action, ComposerAction::Bridge));
        assert!(response.bridge.is_some());
        assert!(response.draft.is_none());
        assert_eq!(response.active_role, "recommender");
        assert!(matches!(
            response.framing.posture,
            ResponsePosture::Suggestive
        ));
        assert!(response.framing.route_comparison.is_some());
    }

    #[test]
    fn classifies_discovery_prompt_as_discovery_action() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "take me from this artist into something adjacent but less obvious",
            12,
            None,
        )
        .expect("compose");
        assert!(matches!(response.action, ComposerAction::Discovery));
        assert!(response.discovery.is_some());
        assert!(response.alternatives_considered.len() >= 2);
        assert!(response.framing.confidence.should_offer_alternatives);
    }

    #[test]
    fn classifies_refinement_prompt_as_steer_action() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "make this playlist less obvious in the middle without losing the ache",
            12,
            None,
        )
        .expect("compose");
        assert!(matches!(response.action, ComposerAction::Steer));
        assert!(response.draft.is_some());
        assert_eq!(response.active_role, "copilot");
        assert!(matches!(
            response.framing.posture,
            ResponsePosture::Collaborative
        ));
        assert!(response.framing.challenge.is_some());
    }

    #[test]
    fn classifies_explanation_prompt_as_oracle_action() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "why is this track here if I want more ache but less gloss",
            8,
            None,
        )
        .expect("compose");
        assert!(matches!(response.action, ComposerAction::Explain));
        assert!(response
            .explanation
            .as_deref()
            .unwrap_or("")
            .contains("Lyra is in oracle mode"));
        assert!(matches!(
            response.framing.posture,
            ResponsePosture::Revelatory
        ));
        assert!(matches!(response.framing.detail_depth, DetailDepth::Deep));
    }

    #[test]
    fn steering_payload_changes_novelty_and_fallback_reporting() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "sad bedroom static that eventually forgives me",
            12,
            Some(&SteerPayload {
                novelty_bias: Some(0.9),
                adventurousness: Some(0.85),
                contrast_sharpness: Some(0.2),
                warmth_bias: Some(0.88),
                explanation_depth: Some("deep".to_string()),
                ..SteerPayload::default()
            }),
        )
        .expect("compose");
        assert_eq!(response.intent.familiarity_vs_novelty, "novel leaning");
        assert_eq!(response.provider_status.provider_kind, "deterministic");
        assert!(response.framing.fallback.active);
        assert!(response.framing.fallback.message.contains("heuristics"));
        assert!(response
            .uncertainty
            .iter()
            .any(|note| note.contains("Heuristic fallback")));
    }

    #[test]
    fn coach_prompt_gets_refining_posture_and_sharpening_challenge() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response =
            compose_composer_response(&conn, &settings, "something good for later", 12, None)
                .expect("compose");
        assert_eq!(response.active_role, "coach");
        assert!(matches!(
            response.framing.posture,
            ResponsePosture::Refining
        ));
        assert!(response
            .framing
            .challenge
            .as_deref()
            .unwrap_or("")
            .contains("sharper landing"));
    }

    #[test]
    fn roles_do_not_flatten_into_same_posture() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let playlist = compose_composer_response(
            &conn,
            &settings,
            "sad bedroom static that eventually forgives me",
            12,
            None,
        )
        .expect("playlist");
        let steer = compose_composer_response(
            &conn,
            &settings,
            "make this less obvious in the middle without losing the ache",
            12,
            None,
        )
        .expect("steer");
        let explain = compose_composer_response(
            &conn,
            &settings,
            "why does this transition work better than the other one",
            12,
            None,
        )
        .expect("explain");

        assert!(matches!(
            playlist.framing.posture,
            ResponsePosture::Refining
        ));
        assert!(matches!(
            steer.framing.posture,
            ResponsePosture::Collaborative
        ));
        assert!(matches!(
            explain.framing.posture,
            ResponsePosture::Revelatory
        ));
    }

    #[test]
    fn protect_the_vibe_behavior_surfaces_on_revision_prompt() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "I want to stay in this mood but stop repeating myself",
            12,
            None,
        )
        .expect("compose");
        assert!(matches!(response.action, ComposerAction::Steer));
        assert!(response
            .framing
            .vibe_guard
            .as_deref()
            .unwrap_or("")
            .contains("protecting"));
    }

    #[test]
    fn discovery_prompt_can_shape_safe_interesting_dangerous_routes() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "give me three exits from this scene, one safe, one interesting, one dangerous",
            12,
            None,
        )
        .expect("compose");
        let labels = response
            .discovery
            .as_ref()
            .expect("discovery")
            .directions
            .iter()
            .map(|direction| direction.label.as_str())
            .collect::<Vec<_>>();
        assert_eq!(labels, vec!["Safe", "Interesting", "Dangerous"]);
        assert!(response.framing.route_comparison.is_some());
    }

    #[test]
    fn scene_exit_prompts_are_first_class_discovery_routes() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response =
            compose_composer_response(&conn, &settings, "same pulse, different world", 12, None)
                .expect("compose");
        let discovery = response.discovery.as_ref().expect("discovery");
        assert!(discovery.scene_exit);
        assert_eq!(discovery.primary_flavor, "interesting");
        assert!(response
            .framing
            .lyra_read
            .summary
            .to_ascii_lowercase()
            .contains("exit"));
    }

    #[test]
    fn route_variants_are_not_just_relabels() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "give me three exits from this scene, one safe, one interesting, one dangerous",
            12,
            None,
        )
        .expect("compose");
        let discovery = response.discovery.as_ref().expect("discovery");
        let safe = &discovery.directions[0];
        let interesting = &discovery.directions[1];
        let dangerous = &discovery.directions[2];
        assert_ne!(safe.risk_note, dangerous.risk_note);
        assert_ne!(safe.reward_note, dangerous.reward_note);
        assert_ne!(safe.description, interesting.description);
        let safe_ids = safe
            .tracks
            .iter()
            .map(|track| track.track.id)
            .collect::<Vec<_>>();
        let dangerous_ids = dangerous
            .tracks
            .iter()
            .map(|track| track.track.id)
            .collect::<Vec<_>>();
        assert_ne!(safe_ids, dangerous_ids);
    }

    #[test]
    fn accepted_route_feedback_can_bias_primary_discovery_lane() {
        let conn = setup_memory_db();
        crate::taste_memory::record_route_feedback(
            &conn,
            &crate::commands::RouteFeedbackPayload {
                route_kind: "dangerous".to_string(),
                action: "discovery".to_string(),
                outcome: "accepted".to_string(),
                source: "test".to_string(),
                note: Some("User keeps picking the rewarding risk.".to_string()),
            },
        )
        .expect("feedback");
        let settings = SettingsPayload::default();
        let response =
            compose_composer_response(&conn, &settings, "what's the rewarding risk here", 12, None)
                .expect("compose");
        assert_eq!(
            response
                .discovery
                .as_ref()
                .expect("discovery")
                .primary_flavor,
            "dangerous"
        );
    }

    #[test]
    fn provider_parse_is_sanitized_back_to_lyra_contract() {
        let fallback = PlaylistIntent {
            prompt: "bridge from Brand New into late-night electronic melancholy".to_string(),
            prompt_role: "recommender".to_string(),
            source_energy: "medium".to_string(),
            destination_energy: "low".to_string(),
            opening_state: PlaylistIntentState::default(),
            landing_state: PlaylistIntentState::default(),
            transition_style: "adjacent bridge".to_string(),
            emotional_arc: vec!["ache".to_string()],
            texture_descriptors: vec!["night-drive".to_string()],
            explicit_entities: vec!["Brand New".to_string()],
            familiarity_vs_novelty: "balanced".to_string(),
            discovery_aggressiveness: "assertive".to_string(),
            user_steer: Vec::new(),
            exclusions: Vec::new(),
            explanation_depth: "balanced".to_string(),
            sequencing_notes: Vec::new(),
            confidence_notes: Vec::new(),
            confidence: 0.62,
        };
        let sanitized = sanitize_provider_intent(
            &fallback.prompt,
            &fallback,
            PlaylistIntent {
                prompt: fallback.prompt.clone(),
                prompt_role: "assistant".to_string(),
                source_energy: "chaotic".to_string(),
                destination_energy: "still low".to_string(),
                opening_state: PlaylistIntentState::default(),
                landing_state: PlaylistIntentState::default(),
                transition_style: "just vibes".to_string(),
                emotional_arc: vec!["ache".to_string(), "ache".to_string()],
                texture_descriptors: vec!["night-drive".to_string()],
                explicit_entities: vec!["Invented Artist".to_string()],
                familiarity_vs_novelty: "super novel".to_string(),
                discovery_aggressiveness: "maybe".to_string(),
                user_steer: vec!["less obvious".to_string()],
                exclusions: Vec::new(),
                explanation_depth: "essay".to_string(),
                sequencing_notes: Vec::new(),
                confidence_notes: vec!["ambiguous".to_string()],
                confidence: 0.91,
            },
        );
        assert_eq!(sanitized.prompt_role, "recommender");
        assert_eq!(sanitized.source_energy, "medium");
        assert_eq!(sanitized.destination_energy, "low");
        assert_eq!(sanitized.transition_style, "adjacent bridge");
        assert!(sanitized.explicit_entities.is_empty());
        assert_eq!(sanitized.familiarity_vs_novelty, "balanced");
        assert_eq!(sanitized.discovery_aggressiveness, "assertive");
        assert_eq!(sanitized.explanation_depth, "balanced");
    }

    #[test]
    fn weird_prompt_fixture_suite_stays_deterministic_without_provider() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let prompts = [
            (
                "edm fire storm trickling into chill undercurrent of lofi covers",
                "playlist",
                "coach",
            ),
            (
                "sad bedroom static that eventually forgives me",
                "playlist",
                "coach",
            ),
            (
                "mall goth sprint into neon confession booth",
                "playlist",
                "coach",
            ),
            (
                "bridge from Brand New into late-night electronic melancholy",
                "bridge",
                "recommender",
            ),
            (
                "make this playlist less obvious in the middle without losing the ache",
                "steer",
                "copilot",
            ),
            (
                "give me a path from aggressive digital shimmer into warm analog regret",
                "bridge",
                "recommender",
            ),
            (
                "take me from this artist into something adjacent but less obvious",
                "discovery",
                "recommender",
            ),
            (
                "what should come after this if I want more ache but less gloss",
                "bridge",
                "recommender",
            ),
            (
                "give me three ways to leave this scene without losing the pulse",
                "discovery",
                "recommender",
            ),
        ];

        for (prompt, action, role) in prompts {
            let response =
                compose_composer_response(&conn, &settings, prompt, 12, None).expect("compose");
            assert_eq!(response.provider_status.provider_kind, "deterministic");
            assert_eq!(response.active_role, role);
            assert_eq!(
                format!("{:?}", response.action).to_ascii_lowercase(),
                action
            );
            assert!(!response.uncertainty.is_empty());
            assert!(!response.framing.lead.is_empty());
            assert!(!response.framing.rationale.is_empty());
            assert!(
                response.draft.is_some()
                    || response.bridge.is_some()
                    || response.discovery.is_some()
                    || response.explanation.is_some()
            );
        }
    }

    #[test]
    fn achy_prompt_uses_playlust_like_heartbreak_shape() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "sad bedroom static that eventually forgives me",
            12,
            None,
        )
        .expect("compose");
        let phases = &response.draft.as_ref().expect("draft").phases;
        assert!(phases.iter().any(|phase| phase.label.contains("Anger")));
        assert!(phases.iter().any(|phase| phase.label.contains("Bottom")));
    }

    #[test]
    fn graph_evidence_can_surface_in_route_reasons() {
        let conn = setup_memory_db();
        conn.execute(
            "INSERT INTO connections (source, target, type, weight, evidence, updated_at)
             VALUES ('Brand New', 'Midnight Circuit', 'dimension_affinity', 0.88, '{}', '2026-03-09T00:00:00Z')",
            [],
        )
        .expect("connection");
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "bridge from Brand New into late-night electronic melancholy",
            10,
            None,
        )
        .expect("compose");
        let bridge = response.bridge.as_ref().expect("bridge");
        assert!(bridge
            .steps
            .iter()
            .any(|step| step.why.contains("graph pull")
                || step
                    .adjacency_signals
                    .iter()
                    .any(|signal| signal.note.contains("scene"))));
    }

    #[test]
    fn spotify_missing_world_pressure_reaches_lyra_read_and_discovery_flavor() {
        let _guard = spotify_env_lock().lock().expect("spotify env lock");
        let legacy_path = setup_spotify_legacy_db();
        std::env::set_var("LYRA_DB_PATH", &legacy_path);

        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let response = compose_composer_response(
            &conn,
            &settings,
            "give me three exits from this Brand New scene, same pulse, different world",
            12,
            None,
        )
        .expect("compose");

        let discovery = response.discovery.as_ref().expect("discovery");
        assert_ne!(discovery.primary_flavor, "safe");
        assert!(
            response.framing.lyra_read.summary.contains("missing-world")
                || response
                    .framing
                    .lyra_read
                    .cues
                    .iter()
                    .any(|cue| cue.contains("Spotify history says"))
        );

        std::env::remove_var("LYRA_DB_PATH");
        let _ = std::fs::remove_file(legacy_path);
    }

    #[test]
    fn mood_pressure_changes_phase_shape_for_late_night_melancholy() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let intent = heuristic_intent(
            &conn,
            "late-night melancholy that trickles into warmer lofi forgiveness",
            &settings,
            &TasteMemorySnapshot::default(),
        );
        let behavior = role_behavior(&intent, &ComposerAction::Playlist);
        let phases = build_phase_plan(&intent, 12, &behavior, &SpotifyPressure::default());
        assert!(phases[2].target_space > phases[0].target_space);
        assert!(phases[3].target_warmth > phases[0].target_warmth);
    }

    #[test]
    fn dangerous_route_prefers_deeper_cut_pressure_than_safe_route() {
        let candidate = CandidateTrack {
            track: TrackRecord {
                id: 1,
                title: "Test".to_string(),
                artist: "Test Artist".to_string(),
                album: "".to_string(),
                path: "C:/Music/test.mp3".to_string(),
                duration_seconds: 180.0,
                genre: Some("post-punk".to_string()),
                year: Some("2003".to_string()),
                bpm: Some(122.0),
                key_signature: None,
                liked: false,
                liked_at: None,
            },
            dims: [0.55, 0.32, 0.61, 0.48, 0.52, 0.58, 0.49, 0.72, 0.47, 0.51],
            play_count: 0,
            artist_lower: "test artist".to_string(),
            title_lower: "test".to_string(),
            scene_family: "nocturnal".to_string(),
        };
        let intent = PlaylistIntent {
            prompt: "take me somewhere adjacent but not the canon, rougher and more human"
                .to_string(),
            prompt_role: "recommender".to_string(),
            source_energy: "medium".to_string(),
            destination_energy: "medium".to_string(),
            opening_state: PlaylistIntentState::default(),
            landing_state: PlaylistIntentState::default(),
            transition_style: "scene exit".to_string(),
            emotional_arc: vec!["ache".to_string()],
            texture_descriptors: vec!["night-drive".to_string()],
            explicit_entities: Vec::new(),
            familiarity_vs_novelty: "novel leaning".to_string(),
            discovery_aggressiveness: "assertive".to_string(),
            user_steer: vec!["less obvious".to_string()],
            exclusions: Vec::new(),
            explanation_depth: "balanced".to_string(),
            sequencing_notes: Vec::new(),
            confidence_notes: Vec::new(),
            confidence: 0.7,
        };
        let safe = deep_cut_pressure(
            &candidate,
            &intent,
            Some(&discovery_route_specs()[0]),
            &SpotifyPressure::default(),
        );
        let dangerous = deep_cut_pressure(
            &candidate,
            &intent,
            Some(&discovery_route_specs()[2]),
            &SpotifyPressure::default(),
        );
        assert!(dangerous > safe);
    }
}

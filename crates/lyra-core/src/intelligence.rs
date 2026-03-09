use std::cmp::Ordering;
use std::collections::{HashSet};

use rusqlite::{params, Connection};
use serde_json::{json, Value};

use crate::commands::{
    BridgePath, BridgeStep, ComposerAction, ComposerProviderStatus, ComposerResponse,
    ComposedPlaylistDraft, ComposedPlaylistTrack, ConfidenceVoice, DetailDepth,
    DiscoveryDirection, DiscoveryRoute, FallbackVoice, GeneratedPlaylist, LyraFraming,
    PlaylistIntent, PlaylistIntentState, PlaylistPhase, PlaylistTrackWithReason,
    ResponsePosture, RouteComparison, SettingsPayload, SteerPayload, TasteProfile,
    TrackReasonPayload, TrackRecord,
};
use crate::errors::{LyraError, LyraResult};
use crate::playlists;

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
    candidates: &'a [CandidateTrack],
}

#[derive(Clone)]
struct CandidateTrack {
    track: TrackRecord,
    dims: Dims,
    play_count: i64,
    artist_lower: String,
    title_lower: String,
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
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent>;
    fn narrate(
        &self,
        config: &ProviderConfig,
        prompt: &str,
        phases: &[PlaylistPhase],
        tracks: &[ComposedPlaylistTrack],
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
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent> {
        let base_url =
            config_string(&config.config, &["base_url", "ollama_base_url"]).unwrap_or("http://127.0.0.1:11434");
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
        prompt: &str,
        phases: &[PlaylistPhase],
        tracks: &[ComposedPlaylistTrack],
    ) -> Option<String> {
        let base_url =
            config_string(&config.config, &["base_url", "ollama_base_url"]).unwrap_or("http://127.0.0.1:11434");
        let model = config_string(&config.config, &["model", "ollama_model"])?;
        let response = ureq::post(&format!("{}/api/chat", base_url.trim_end_matches('/')))
            .send_json(json!({
                "model": model,
                "stream": false,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Lyra. Write 2 concise sentences explaining the emotional arc of a playlist without inventing tracks."
                    },
                    {
                        "role": "user",
                        "content": narrative_prompt(prompt, phases, tracks)
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
            &["model", "cloud_model", "openai_model", "groq_model", "openrouter_model"],
        )
        .unwrap_or("");
        let api_key = config_string(
            &config.config,
            &["api_key", "token", "openai_api_key", "groq_api_key", "openrouter_api_key"],
        )
        .unwrap_or("");
        !model.trim().is_empty() && !api_key.trim().is_empty()
    }

    fn parse_intent(
        &self,
        config: &ProviderConfig,
        prompt: &str,
        fallback: &PlaylistIntent,
    ) -> Option<PlaylistIntent> {
        let response = openai_compatible_completion(
            config,
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
        prompt: &str,
        phases: &[PlaylistPhase],
        tracks: &[ComposedPlaylistTrack],
    ) -> Option<String> {
        openai_compatible_completion(
            config,
            json!([
                {
                    "role": "system",
                    "content": "You are Lyra. Write 2 concise sentences explaining the emotional arc of a playlist without inventing tracks."
                },
                {
                    "role": "user",
                    "content": narrative_prompt(prompt, phases, tracks)
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

    let requested_provider = normalize_provider_preference(&settings.composer_provider_preference);
    let provider_configs = load_llm_provider_configs(conn)?;
    let heuristic_intent = heuristic_intent(conn, trimmed_prompt, settings);
    let (provider_status, parsed_intent) = select_and_parse_intent(
        trimmed_prompt,
        &heuristic_intent,
        requested_provider.as_str(),
        &provider_configs,
    );
    let steered_intent = apply_steer(&parsed_intent, steer);
    let action = detect_composer_action(trimmed_prompt, &steered_intent);
    let behavior = role_behavior(&steered_intent, &action);
    let taste = load_taste_profile(conn);
    let candidates = load_candidates(conn)?;
    let runtime = ComposeRuntime {
        provider_status: &provider_status,
        provider_configs: &provider_configs,
        behavior: &behavior,
        taste: &taste,
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
    response
        .draft
        .ok_or_else(|| LyraError::Message("Prompt did not resolve to a playlist draft.".to_string()))
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
    let phases = build_phase_plan(intent, track_count, runtime.behavior);
    let tracks = sequence_tracks(
        runtime.candidates,
        &phases,
        intent,
        runtime.taste,
        track_count,
        runtime.behavior,
    );
    let narrative = select_narrative(
        prompt,
        runtime.provider_status,
        runtime.provider_configs,
        &phases,
        &tracks,
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
        Some(route_comparison_for_phases(&phases)),
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
    }
}

fn compose_bridge_response(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> ComposerResponse {
    let phases = build_bridge_phase_plan(intent, track_count, runtime.behavior);
    let tracks = sequence_tracks(
        runtime.candidates,
        &phases,
        intent,
        runtime.taste,
        track_count,
        runtime.behavior,
    );
    let (source_label, destination_label) = bridge_labels(prompt, intent);
    let narrative = select_narrative(
        prompt,
        runtime.provider_status,
        runtime.provider_configs,
        &phases,
        &tracks,
    )
        .or_else(|| Some(template_bridge_narrative(intent, &source_label, &destination_label)));
    let steps = tracks
        .iter()
        .enumerate()
        .map(|(idx, item)| BridgeStep {
            track: item.track.clone(),
            fit_score: item.fit_score,
            role: bridge_step_role(idx, tracks.len()),
            why: format!("{} {}", item.reason.why_this_track, item.reason.transition_note),
            distance_from_source: bridge_distance(idx, tracks.len(), false),
            distance_from_destination: bridge_distance(idx, tracks.len(), true),
        })
        .collect::<Vec<_>>();
    let bridge = BridgePath {
        source_label,
        destination_label,
        steps,
        narrative,
        confidence: intent.confidence,
        alternate_directions: alternatives_for_action(intent, &ComposerAction::Bridge),
    };
    let framing = build_lyra_framing(
        prompt,
        intent,
        &ComposerAction::Bridge,
        runtime.provider_status,
        runtime.behavior,
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
    }
}

fn compose_discovery_response(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> ComposerResponse {
    let seed_label = intent
        .explicit_entities
        .first()
        .cloned()
        .unwrap_or_else(|| title_case(prompt));
    let route = DiscoveryRoute {
        seed_label,
        directions: discovery_directions(
            prompt,
            track_count,
            intent,
            runtime,
        ),
        narrative: Some(template_discovery_narrative(intent)),
        confidence: intent.confidence,
    };
    let framing = build_lyra_framing(
        prompt,
        intent,
        &ComposerAction::Discovery,
        runtime.provider_status,
        runtime.behavior,
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
            None,
        ),
        draft: None,
        bridge: None,
        discovery: None,
        explanation: Some(template_explanation(intent, provider_status, behavior)),
        active_role: behavior.role.clone(),
        uncertainty: uncertainty_notes(intent, provider_status, behavior),
        alternatives_considered: alternatives_for_action(intent, &ComposerAction::Explain),
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
            offer_alternatives: matches!(action, ComposerAction::Bridge | ComposerAction::Discovery),
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
        let Some(provider) = providers.iter().find(|provider| provider.provider_key() == provider_key)
        else {
            continue;
        };
        if !provider.is_available(config) {
            continue;
        }
        if let Some(parsed) = provider.parse_intent(config, prompt, heuristic) {
            return (
                ComposerProviderStatus {
                    requested_provider: requested_provider.to_string(),
                    selected_provider: provider.provider_key().to_string(),
                    provider_kind: provider.provider_kind().to_string(),
                    mode: if parsed.confidence > heuristic.confidence {
                        "provider-assisted".to_string()
                    } else {
                        "provider-assisted-with-heuristic-merge".to_string()
                    },
                    fallback_reason: None,
                },
                parsed,
            );
        }
    }

    (
        ComposerProviderStatus {
            requested_provider: requested_provider.to_string(),
            selected_provider: "heuristic".to_string(),
            provider_kind: "deterministic".to_string(),
            mode: "heuristic-fallback".to_string(),
            fallback_reason: Some("No configured LLM provider was available for this prompt.".to_string()),
        },
        heuristic.clone(),
    )
}

fn select_narrative(
    prompt: &str,
    provider_status: &ComposerProviderStatus,
    provider_configs: &[ProviderConfig],
    phases: &[PlaylistPhase],
    tracks: &[ComposedPlaylistTrack],
) -> Option<String> {
    if provider_status.provider_kind == "deterministic" {
        return None;
    }
    let provider_key = provider_status.selected_provider.clone();
    let config = provider_configs
        .iter()
        .find(|config| config.provider_key == provider_key)?;
    match provider_key.as_str() {
        "ollama" => OllamaProvider.narrate(config, prompt, phases, tracks),
        "openai" => OpenAiCompatibleProvider { provider_key: "openai" }.narrate(config, prompt, phases, tracks),
        "openrouter" => OpenAiCompatibleProvider { provider_key: "openrouter" }.narrate(config, prompt, phases, tracks),
        "groq" => OpenAiCompatibleProvider { provider_key: "groq" }.narrate(config, prompt, phases, tracks),
        _ => None,
    }
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

fn heuristic_intent(conn: &Connection, prompt: &str, settings: &SettingsPayload) -> PlaylistIntent {
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
        user_steer: merge_taste_memory(&user_steer, &settings.composer_taste_memory),
        exclusions,
        explanation_depth: settings.composer_explanation_depth.clone(),
        sequencing_notes,
        confidence_notes,
        confidence: heuristic_confidence(prompt),
    }
}

fn build_phase_plan(intent: &PlaylistIntent, track_count: usize, behavior: &RoleBehavior) -> Vec<PlaylistPhase> {
    let start_energy = energy_value(&intent.source_energy);
    let end_energy = energy_value(&intent.destination_energy);
    let gradual = intent.transition_style.contains("gradual") || intent.transition_style.contains("glide");
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
            let energy = lerp(start_energy, end_energy, eased);
            let valence = if intent.emotional_arc.iter().any(|value| value.contains("ache")) {
                lerp(0.38 + role_valence_bias, 0.56 + role_valence_bias, eased)
            } else {
                lerp(0.48 + role_valence_bias, 0.64 + role_valence_bias, eased)
            };
            let tension = if idx < 2 {
                lerp(0.78, 0.5, eased)
            } else {
                lerp(0.5, 0.32, eased)
            };
            let warmth = if intent.texture_descriptors.iter().any(|value| value.contains("lofi")) {
                lerp(0.34, 0.78, eased)
            } else {
                lerp(0.38, 0.62, eased)
            };
            let space = if idx >= 2 { lerp(0.42, 0.82, eased) } else { lerp(0.28, 0.58, eased) };
            PlaylistPhase {
                key: (*key).to_string(),
                label: (*label).to_string(),
                summary: phase_summary(intent, label, idx),
                target_energy: energy,
                target_valence: valence,
                target_tension: tension,
                target_warmth: warmth,
                target_space: space,
                novelty_bias: novelty_bias(intent, idx),
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

fn sequence_tracks(
    candidates: &[CandidateTrack],
    phases: &[PlaylistPhase],
    intent: &PlaylistIntent,
    taste: &TasteProfile,
    track_count: usize,
    behavior: &RoleBehavior,
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
                let taste_fit = taste_fit(candidate, taste);
                let novelty_fit = 1.0 - (novelty_score(candidate) - novelty_target).abs();
                let entity_bonus = entity_bonus(candidate, &entity_needles);
                let transition_fit = previous_dims
                    .map(|prev| transition_fit(prev, candidate.dims, &intent.transition_style))
                    .unwrap_or(0.64);
                let vibe_guard_fit = vibe_guard_fit(candidate, intent, behavior);
                let sideways_fit = sideways_fit(candidate, intent, behavior);
                let (fit_weight, taste_weight, novelty_weight, transition_weight, entity_weight) =
                    score_weights(&behavior.role, &intent.prompt_role);
                let score = fit * fit_weight
                    + taste_fit * taste_weight
                    + novelty_fit * novelty_weight
                    + transition_fit * transition_weight
                    + entity_bonus * entity_weight
                    + vibe_guard_fit * 0.08
                    + sideways_fit * 0.06;
                (score, candidate)
            })
            .filter(|(score, _)| *score >= 0.32)
            .collect();
        scored.sort_by(|left, right| {
            right
                .0
                .partial_cmp(&left.0)
                .unwrap_or(Ordering::Equal)
                .then_with(|| left.1.play_count.cmp(&right.1.play_count))
        });

        for (score, candidate) in scored.into_iter().take(per_phase) {
            let summary = reason_summary(candidate, phase, score, behavior);
            let why_this_track = format!(
                "{} anchors {} by matching {} energy with {} texture while Lyra works in {} mode.",
                candidate.track.title,
                phase.label,
                intent_phrase(&phase.label),
                descriptor_phrase(candidate, intent),
                behavior.role
            );
            let transition_note = previous_dims
                .map(|prev| transition_sentence(prev, candidate.dims, &intent.transition_style))
                .unwrap_or_else(|| "Opens the arc without forcing the landing too early.".to_string());
            let reason = TrackReasonPayload {
                summary,
                phase: phase.label.clone(),
                why_this_track,
                transition_note,
                evidence: evidence_for_candidate(candidate, phase, taste),
                explicit_from_prompt: explicit_hits(candidate, &entity_needles),
                inferred_by_lyra: inferred_notes(candidate, phase, intent, behavior),
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
    ordered
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

fn merge_taste_memory(user_steer: &[String], memory: &[String]) -> Vec<String> {
    let mut merged = user_steer.to_vec();
    merged.extend(memory.iter().cloned());
    merged.sort();
    merged.dedup();
    merged
}

fn detect_composer_action(prompt: &str, intent: &PlaylistIntent) -> ComposerAction {
    let lower = prompt.to_ascii_lowercase();
    if has_any(&lower, &["bridge from", "show me a path", "path from", "what should come after this"]) {
        ComposerAction::Bridge
    } else if has_any(&lower, &["three ways", "leave this scene", "three exits", "one safe, one interesting, one dangerous"]) {
        ComposerAction::Discovery
    } else if has_any(
        &lower,
        &["adjacent", "less obvious", "three ways", "leave this scene", "discover", "something adjacent"],
    ) {
        if has_any(&lower, &["make this", "without losing", "keep the", "stay in this mood"]) {
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
    } else if has_any(lower, &["adjacent", "discover", "bridge", "path from", "come after this", "what should come after this", "three ways", "three exits", "one safe, one interesting, one dangerous"]) {
        "recommender".to_string()
    } else {
        "coach".to_string()
    }
}

fn detect_source_energy(lower: &str) -> String {
    if has_any(lower, &["fire", "storm", "sprint", "high-energy", "blast", "frenzy", "edm"]) {
        "high".to_string()
    } else if has_any(lower, &["calm", "soft", "still", "lofi", "chill", "gentle"]) {
        "low".to_string()
    } else {
        "medium".to_string()
    }
}

fn detect_destination_energy(lower: &str, source: &str) -> String {
    if has_any(lower, &["into chill", "lofi", "undercurrent", "forgives", "nocturnal", "calm"]) {
        "low".to_string()
    } else if has_any(lower, &["erupts", "ends loud", "climax", "blast"]) {
        "high".to_string()
    } else {
        source.to_string()
    }
}

fn detect_transition_style(lower: &str) -> String {
    if has_any(lower, &["trickling", "gradual", "glide", "undercurrent", "slowly", "eventually"]) {
        "gradual cooling".to_string()
    } else if has_any(lower, &["sharper contrast", "hard pivot", "leave this scene"]) {
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
    if has_any(lower, &["regret", "late-night", "melancholy", "bedroom static"]) {
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
    if has_any(lower, &["less obvious", "adjacent but less obvious", "adventurous", "deeper cut"]) {
        "novel leaning".to_string()
    } else if has_any(lower, &["more obvious", "familiar", "recognizable"]) {
        "familiar leaning".to_string()
    } else if has_any(lower, &["familiar", "keep the ache", "covers"]) {
        "familiar landing".to_string()
    } else {
        "balanced".to_string()
    }
}

fn detect_discovery_aggressiveness(lower: &str) -> String {
    if has_any(lower, &["less obvious", "adjacent", "bridge", "adventurous"]) {
        "assertive".to_string()
    } else if has_any(lower, &["three ways", "leave this scene", "path from"]) {
        "exploratory".to_string()
    } else if has_any(lower, &["keep", "gently", "familiar"]) {
        "gentle".to_string()
    } else {
        "medium".to_string()
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
        values.push("Make the pivot legible with intermediate adjacency, not a blind jump.".to_string());
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
        values.push("Destination energy is inferred because the prompt does not state an explicit landing.".to_string());
    }
    if has_any(lower, &["bridge", "adjacent", "less obvious", "leave this scene"]) {
        values.push("This prompt implies a route choice, so Lyra may offer alternate directions instead of one supposedly final answer.".to_string());
    }
    values
}

fn heuristic_confidence(prompt: &str) -> f64 {
    let words = prompt.split_whitespace().count() as f64;
    (0.46 + (words.min(16.0) / 40.0)).clamp(0.46, 0.82)
}

fn energy_value(label: &str) -> f64 {
    match label {
        "high" => 0.82,
        "low" => 0.28,
        _ => 0.54,
    }
}

fn phase_summary(intent: &PlaylistIntent, _label: &str, idx: usize) -> String {
    match idx {
        0 => format!(
            "Open with {} energy and {} texture.",
            intent.source_energy,
            intent.opening_state.descriptors.join(", ")
        ),
        1 => format!("Keep motion alive while {} starts to show.", intent.texture_descriptors.join(", ")),
        2 => format!("Bridge toward {} without dropping the emotional thread.", intent.destination_energy),
        _ => format!(
            "Land in {} with {} descriptors still audible.",
            intent.destination_energy,
            intent.landing_state.descriptors.join(", ")
        ),
    }
}

fn novelty_bias(intent: &PlaylistIntent, idx: usize) -> f64 {
    match intent.familiarity_vs_novelty.as_str() {
        "novel leaning" if (1..=2).contains(&idx) => 0.84,
        "familiar landing" if idx == 3 => 0.34,
        _ => 0.56,
    }
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

fn entity_bonus(candidate: &CandidateTrack, entities: &[String]) -> f64 {
    if entities.is_empty() {
        return 0.4;
    }
    if entities.iter().any(|entity| candidate.artist_lower.contains(entity) || candidate.title_lower.contains(entity)) {
        1.0
    } else {
        0.18
    }
}

fn vibe_guard_fit(candidate: &CandidateTrack, intent: &PlaylistIntent, behavior: &RoleBehavior) -> f64 {
    if !behavior.protect_vibe {
        return 0.5;
    }
    let mut score: f64 = 0.5;
    if intent.emotional_arc.iter().any(|value| value == "ache") {
        score += (1.0 - (candidate.dims[1] - 0.34).abs()).clamp(0.0, 1.0) * 0.2;
        score += (1.0 - (candidate.dims[4] - 0.52).abs()).clamp(0.0, 1.0) * 0.15;
    }
    if has_any(&intent.prompt.to_ascii_lowercase(), &["keep", "without losing", "stay in this mood"]) {
        score += (1.0 - (candidate.dims[9] - 0.56).abs()).clamp(0.0, 1.0) * 0.15;
    }
    score.clamp(0.0, 1.0)
}

fn sideways_fit(candidate: &CandidateTrack, intent: &PlaylistIntent, behavior: &RoleBehavior) -> f64 {
    if !behavior.tempt_sideways {
        return 0.4;
    }
    let novelty = novelty_score(candidate);
    let texture_shift = candidate.dims[7];
    let appetite = if intent.familiarity_vs_novelty == "novel leaning" { 0.72 } else { 0.52 };
    (1.0 - (novelty - appetite).abs() + texture_shift * 0.2).clamp(0.0, 1.0)
}

fn reason_summary(
    candidate: &CandidateTrack,
    phase: &PlaylistPhase,
    fit_score: f64,
    behavior: &RoleBehavior,
) -> String {
    format!(
        "{} sits in {} because it scores {:.0}% against the phase target and supports Lyra's {} stance.",
        candidate.track.title,
        phase.label,
        fit_score * 100.0,
        behavior.role
    )
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
    if style.contains("gradual") {
        format!(
            "Transitions with a {:.0}% energy {} so the arc cools instead of snapping.",
            change.abs() * 100.0,
            if change < 0.0 { "drop" } else { "lift" }
        )
    } else {
        format!(
            "Keeps the move readable with {:.0}% energy change across adjacent tracks.",
            change.abs() * 100.0
        )
    }
}

fn evidence_for_candidate(candidate: &CandidateTrack, phase: &PlaylistPhase, taste: &TasteProfile) -> Vec<String> {
    let mut evidence = vec![
        format!("Phase target energy {:.2}; track energy {:.2}.", phase.target_energy, candidate.dims[0]),
        format!("Phase target warmth {:.2}; track warmth {:.2}.", phase.target_warmth, candidate.dims[4]),
        format!("Track play count in local history: {}.", candidate.play_count),
    ];
    if !taste.dimensions.is_empty() {
        evidence.push(format!(
            "Taste confidence {:.0}% contributed to reranking.",
            taste.confidence * 100.0
        ));
    }
    evidence
}

fn explicit_hits(candidate: &CandidateTrack, entities: &[String]) -> Vec<String> {
    entities
        .iter()
        .filter(|entity| candidate.artist_lower.contains(entity.as_str()) || candidate.title_lower.contains(entity.as_str()))
        .cloned()
        .collect()
}

fn inferred_notes(
    candidate: &CandidateTrack,
    phase: &PlaylistPhase,
    intent: &PlaylistIntent,
    behavior: &RoleBehavior,
) -> Vec<String> {
    let mut notes = vec![format!("Assigned to {} from local score fit.", phase.label)];
    if !intent.texture_descriptors.is_empty() {
        notes.push(format!(
            "Texture interpretation leaned on {}.",
            intent.texture_descriptors.join(", ")
        ));
    }
    if !behavior.silent_inference_ok {
        notes.push("Lyra is surfacing inference explicitly because this role should not hide uncertainty.".to_string());
    }
    if candidate.play_count == 0 {
        notes.push("Boosted as a fresh library path with no prior playback history.".to_string());
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
) -> Vec<PlaylistPhase> {
    let mut phases = build_phase_plan(intent, track_count.max(5), behavior);
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
        entities.first().cloned().unwrap_or_else(|| intent.opening_state.descriptors.join(" ")),
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
    if reverse { 1.0 - progress } else { progress }
}

fn discovery_directions(
    prompt: &str,
    track_count: usize,
    intent: &PlaylistIntent,
    runtime: &ComposeRuntime<'_>,
) -> Vec<DiscoveryDirection> {
    let direction_specs = if has_any(&prompt.to_ascii_lowercase(), &["safe", "interesting", "dangerous"]) {
        [
            ("Safe", "Stay emotionally faithful and keep the landmarks legible.", "familiar landing"),
            ("Interesting", "Slip sideways into a more revealing adjacent route.", "balanced"),
            ("Dangerous", "Break the scene harder while protecting one live wire from the original mood.", "novel leaning"),
        ]
    } else {
        [
            ("Closer in", "Stay near the source, but sand off the obvious picks.", "balanced"),
            ("Side door", "Move into adjacent territory with stronger novelty pressure.", "novel leaning"),
            ("Scene break", "Keep the pulse but let the texture family change on purpose.", "familiar landing"),
        ]
    };
    direction_specs
        .iter()
        .map(|(label, description, novelty)| {
            let mut direction_intent = intent.clone();
            direction_intent.familiarity_vs_novelty = (*novelty).to_string();
            let phases = build_phase_plan(&direction_intent, (track_count / 3).max(3), runtime.behavior);
            let tracks = sequence_tracks(
                runtime.candidates,
                &phases,
                &direction_intent,
                runtime.taste,
                (track_count / 3).max(3),
                runtime.behavior,
            );
            let why = select_narrative(
                prompt,
                runtime.provider_status,
                runtime.provider_configs,
                &phases,
                &tracks,
            )
                .unwrap_or_else(|| format!("{description} Lyra kept {} in play.", direction_intent.emotional_arc.join(", ")));
            DiscoveryDirection {
                label: (*label).to_string(),
                description: (*description).to_string(),
                tracks,
                why,
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
    route_comparison: Option<RouteComparison>,
) -> LyraFraming {
    let posture = posture_for(action, &behavior.role);
    let detail_depth = detail_depth_for(behavior, action, intent);
    let confidence = confidence_voice(intent, provider_status, action);
    let fallback = fallback_voice(provider_status);
    let challenge = challenge_line(prompt, intent, action, behavior);
    let memory = taste_memory_hint(intent);

    LyraFraming {
        posture,
        detail_depth,
        lead: lead_line(intent, action, behavior),
        rationale: rationale_line(intent, action, behavior),
        presence_note: presence_note(intent, action, behavior),
        challenge,
        vibe_guard: vibe_guard_line(intent, action, behavior),
        confidence,
        fallback,
        route_comparison,
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
        should_offer_alternatives: level != "high" || matches!(action, ComposerAction::Bridge | ComposerAction::Discovery),
    }
}

fn presence_note(intent: &PlaylistIntent, action: &ComposerAction, behavior: &RoleBehavior) -> Option<String> {
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

fn vibe_guard_line(intent: &PlaylistIntent, action: &ComposerAction, behavior: &RoleBehavior) -> Option<String> {
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

fn taste_memory_hint(intent: &PlaylistIntent) -> Option<String> {
    if intent.user_steer.is_empty() {
        None
    } else {
        Some(format!(
            "Recent steer language is clustering around {}.",
            intent.user_steer.join(", ")
        ))
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
            "This wants a hinge, not a leap. Lyra is threading {} into {} without dropping {}.",
            intent.opening_state.descriptors.join(", "),
            intent.landing_state.descriptors.join(", "),
            intent.emotional_arc.join(", ")
        ),
        ComposerAction::Discovery => "There is more than one good way out of this scene, so Lyra is treating discovery as a set of directions rather than one neat answer.".to_string(),
        ComposerAction::Steer => "Lyra is treating this as a revision pass, not a fresh command. The goal is to keep the spine and move the surface.".to_string(),
        ComposerAction::Explain => "There is structure under this move. Lyra is naming the pressure points instead of waving at 'vibes'.".to_string(),
        ComposerAction::Playlist => match behavior.role.as_str() {
            "coach" => "Lyra has a read on the mood, but it is also sharpening what the prompt is really asking for.".to_string(),
            _ => "Lyra is shaping this like a journey, not a bucket of matching tracks.".to_string(),
        },
    }
}

fn rationale_line(intent: &PlaylistIntent, action: &ComposerAction, behavior: &RoleBehavior) -> String {
    match action {
        ComposerAction::Bridge => format!(
            "The priority is legibility: keep {} audible early, let {} emerge late, and use the middle to make the turn feel earned.",
            intent.opening_state.descriptors.join(", "),
            intent.landing_state.descriptors.join(", ")
        ),
        ComposerAction::Discovery => "Lyra is separating familiar, adjacent, and scene-breaking exits so the user can choose what kind of risk feels right.".to_string(),
        ComposerAction::Steer => format!(
            "Because this is {} mode, Lyra preserves the emotional thread while moving obviousness, contrast, and texture on purpose.",
            behavior.role
        ),
        ComposerAction::Explain => "The explanation stays concrete: bridge logic, emotional pressure, transition readability, and where uncertainty still lives.".to_string(),
        ComposerAction::Playlist => format!(
            "The sequence prioritizes {} over generic genre matching, so the arc can feel authored instead of auto-filled.",
            intent.emotional_arc.join(", ")
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
    if matches!(action, ComposerAction::Steer) {
        Some("If you want this less obvious, Lyra will protect the ache first and sacrifice the easy landmarks second.".to_string())
    } else if behavior.role == "coach" && intent.explicit_entities.is_empty() && !has_any(&lower, &["into", "from", "after"]) {
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
            let mut nudges = vec!["Make it less obvious.".to_string(), "Push it more nocturnal.".to_string()];
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
    }
}

fn route_comparison_for_discovery(_route: &DiscoveryRoute) -> RouteComparison {
    RouteComparison {
        headline: "How the exits differ".to_string(),
        summary: "Lyra separated the routes so one stays nearest the source, one slips sideways into adjacency, and one breaks scene while protecting the pulse.".to_string(),
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
        notes.push("This role exposes interpretation seams instead of silently smoothing them over.".to_string());
    }
    if behavior.prefer_revision {
        notes.push("Lyra is treating this as a revisable working route, not a final immutable answer.".to_string());
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

fn template_narrative(intent: &PlaylistIntent, phases: &[PlaylistPhase], behavior: &RoleBehavior) -> String {
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

fn template_bridge_narrative(intent: &PlaylistIntent, source_label: &str, destination_label: &str) -> String {
    format!(
        "Lyra treats this as a bridge problem, not a generic draft: start at {}, loosen the obvious markers, and arrive at {} through {} without losing {}.",
        source_label,
        destination_label,
        intent.texture_descriptors.join(", "),
        intent.emotional_arc.join(", ")
    )
}

fn template_discovery_narrative(intent: &PlaylistIntent) -> String {
    format!(
        "Lyra is offering multiple exits from the current scene so discovery stays steerable. The directions vary novelty pressure while keeping {} and {} legible.",
        intent.texture_descriptors.join(", "),
        intent.emotional_arc.join(", ")
    )
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
    "You are Lyra, a music intelligence companion. Interpret poetic music prompts for local-library retrieval. Do not invent tracks, artists, or library state. Distinguish bridge/discovery/steering/explanation intent from ordinary playlist drafting. Return only JSON with keys: prompt_role, source_energy, destination_energy, transition_style, emotional_arc, texture_descriptors, explicit_entities, familiarity_vs_novelty, discovery_aggressiveness, user_steer, exclusions, explanation_depth, sequencing_notes, confidence_notes, confidence. Keep confidence_notes honest when the prompt is ambiguous."
}

fn intent_user_prompt(prompt: &str, fallback: &PlaylistIntent) -> String {
    format!(
        "Prompt: {prompt}\nFallback interpretation: {}\nUse the fallback if the prompt is underspecified, but improve it when the language clearly implies bridge, discovery, coaching, or explanation behavior.\nReturn only JSON.",
        serde_json::to_string(fallback).unwrap_or_default()
    )
}

fn narrative_prompt(prompt: &str, phases: &[PlaylistPhase], tracks: &[ComposedPlaylistTrack]) -> String {
    let phase_text = phases
        .iter()
        .map(|phase| format!("{}: {}", phase.label, phase.summary))
        .collect::<Vec<_>>()
        .join(" | ");
    let track_text = tracks
        .iter()
        .take(6)
        .map(|track| format!("{} - {} [{}]", track.track.artist, track.track.title, track.phase_label))
        .collect::<Vec<_>>()
        .join(" | ");
    format!(
        "Prompt: {prompt}\nPhases: {phase_text}\nRepresentative tracks: {track_text}\nExplain the journey in 2 concise sentences."
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
    intent.texture_descriptors = string_array(&payload, "texture_descriptors", &intent.texture_descriptors);
    intent.explicit_entities = string_array(&payload, "explicit_entities", &intent.explicit_entities);
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
    Some(intent)
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

fn openai_compatible_completion(config: &ProviderConfig, messages: Value) -> Option<String> {
    let base_url = config_string(
        &config.config,
        &["base_url", "openai_base_url", "openrouter_base_url", "groq_base_url"],
    )
    .unwrap_or(match config.provider_key.as_str() {
            "openai" => "https://api.openai.com/v1",
            "openrouter" => "https://openrouter.ai/api/v1",
            "groq" => "https://api.groq.com/openai/v1",
            _ => return None,
        });
    let model = config_string(
        &config.config,
        &["model", "cloud_model", "openai_model", "groq_model", "openrouter_model"],
    )?;
    let api_key = config_string(
        &config.config,
        &["api_key", "token", "openai_api_key", "groq_api_key", "openrouter_api_key"],
    )?;

    let response = ureq::post(&format!("{}/chat/completions", base_url.trim_end_matches('/')))
        .set("Authorization", &format!("Bearer {api_key}"))
        .set("Content-Type", "application/json")
        .send_json(json!({
            "model": model,
            "temperature": 0.2,
            "messages": messages,
        }))
        .ok()?;
    let payload: Value = response.into_json().ok()?;
    payload
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
        .and_then(|choice| choice.get("message"))
        .and_then(|message| message.get("content"))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
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
            conn.execute("INSERT INTO artists (name) VALUES (?1)", params![artist]).expect("artist");
        }
        let tracks = [
            ("Soco Static", "Brand New", 0.46, 0.34, 0.62, 0.52, 0.44, 0.40, 0.32, 0.38, 0.56, 0.68, "emo"),
            ("Late Train Pulse", "Midnight Circuit", 0.58, 0.28, 0.56, 0.48, 0.38, 0.54, 0.52, 0.36, 0.62, 0.44, "electronic"),
            ("Bedroom Static", "Glass Static", 0.24, 0.30, 0.40, 0.34, 0.66, 0.22, 0.64, 0.48, 0.42, 0.74, "lofi"),
            ("Neon Confession", "Neon Chapel", 0.72, 0.48, 0.58, 0.70, 0.36, 0.78, 0.42, 0.28, 0.52, 0.34, "synthpop"),
            ("Warm Analog Regret", "Warm Tape", 0.36, 0.32, 0.44, 0.42, 0.82, 0.30, 0.58, 0.34, 0.46, 0.86, "indie"),
            ("Chill Undercurrent", "Lofi Haze", 0.18, 0.42, 0.22, 0.30, 0.72, 0.18, 0.76, 0.24, 0.38, 0.62, "lofi"),
            ("Aggressive Shimmer", "Digital Ash", 0.82, 0.40, 0.68, 0.78, 0.22, 0.84, 0.26, 0.30, 0.64, 0.20, "edm"),
            ("Eventually Forgives", "Soft Signal", 0.22, 0.54, 0.26, 0.32, 0.78, 0.20, 0.72, 0.22, 0.34, 0.80, "dream-pop"),
            ("Mall Goth Sprint", "Mall Ghost", 0.76, 0.38, 0.60, 0.74, 0.28, 0.80, 0.30, 0.42, 0.58, 0.32, "post-punk"),
            ("Analog Afterglow", "Analog Regret", 0.34, 0.36, 0.32, 0.40, 0.84, 0.26, 0.66, 0.20, 0.40, 0.90, "ambient"),
            ("Fire Storm Trickle", "Fire Run", 0.88, 0.52, 0.72, 0.82, 0.24, 0.90, 0.18, 0.32, 0.48, 0.26, "edm"),
            ("Confession Neon Booth", "Confession Booth", 0.62, 0.44, 0.54, 0.60, 0.46, 0.68, 0.44, 0.26, 0.50, 0.40, "art-pop"),
        ];

        for (index, (title, artist, energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia, genre)) in tracks.iter().enumerate() {
            let artist_id: i64 = conn
                .query_row("SELECT id FROM artists WHERE name = ?1", params![artist], |row| row.get(0))
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
            conn.execute("UPDATE tracks SET genre = ?1 WHERE id = ?2", params![genre, track_id]).ok();
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

    #[test]
    fn detects_gradual_cooling_prompt() {
        let settings = SettingsPayload::default();
        let conn = setup_memory_db();
        let intent = heuristic_intent(
            &conn,
            "edm fire storm trickling into chill undercurrent of lofi covers",
            &settings,
        );
        assert_eq!(intent.source_energy, "high");
        assert_eq!(intent.destination_energy, "low");
        assert!(intent.transition_style.contains("gradual"));
        assert!(intent.texture_descriptors.iter().any(|value| value.contains("lofi")));
    }

    #[test]
    fn extracts_json_object_from_wrapped_text() {
        let content = "here\n{\"source_energy\":\"high\"}\nthanks";
        assert_eq!(extract_json_object(content), Some("{\"source_energy\":\"high\"}"));
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
        assert!(matches!(response.framing.posture, ResponsePosture::Suggestive));
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
        assert!(matches!(response.framing.posture, ResponsePosture::Collaborative));
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
        assert!(response.explanation.as_deref().unwrap_or("").contains("Lyra is in oracle mode"));
        assert!(matches!(response.framing.posture, ResponsePosture::Revelatory));
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
        let response = compose_composer_response(&conn, &settings, "something good for later", 12, None)
            .expect("compose");
        assert_eq!(response.active_role, "coach");
        assert!(matches!(response.framing.posture, ResponsePosture::Refining));
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

        assert!(matches!(playlist.framing.posture, ResponsePosture::Refining));
        assert!(matches!(steer.framing.posture, ResponsePosture::Collaborative));
        assert!(matches!(explain.framing.posture, ResponsePosture::Revelatory));
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
    fn weird_prompt_fixture_suite_stays_deterministic_without_provider() {
        let conn = setup_memory_db();
        let settings = SettingsPayload::default();
        let prompts = [
            ("edm fire storm trickling into chill undercurrent of lofi covers", "playlist", "coach"),
            ("sad bedroom static that eventually forgives me", "playlist", "coach"),
            ("mall goth sprint into neon confession booth", "playlist", "coach"),
            ("bridge from Brand New into late-night electronic melancholy", "bridge", "recommender"),
            ("make this playlist less obvious in the middle without losing the ache", "steer", "copilot"),
            ("give me a path from aggressive digital shimmer into warm analog regret", "bridge", "recommender"),
            ("take me from this artist into something adjacent but less obvious", "discovery", "recommender"),
            ("what should come after this if I want more ache but less gloss", "bridge", "recommender"),
            ("give me three ways to leave this scene without losing the pulse", "discovery", "recommender"),
        ];

        for (prompt, action, role) in prompts {
            let response = compose_composer_response(&conn, &settings, prompt, 12, None).expect("compose");
            assert_eq!(response.provider_status.provider_kind, "deterministic");
            assert_eq!(response.active_role, role);
            assert_eq!(format!("{:?}", response.action).to_ascii_lowercase(), action);
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
}

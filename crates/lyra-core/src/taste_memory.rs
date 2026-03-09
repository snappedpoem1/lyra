use chrono::{DateTime, Duration, Utc};
use rusqlite::{params, Connection};

use crate::commands::{
    ComposerAction, ComposerResponse, RememberedPreference, RouteChoicePreference,
    RouteFeedbackPayload, SessionTastePosture, SteerPayload, TasteMemorySnapshot,
};
use crate::errors::LyraResult;

#[derive(Clone, Debug)]
struct ObservedPreference {
    axis_key: &'static str,
    axis_label: &'static str,
    preferred_pole: &'static str,
    phrase: String,
    weight: f64,
}

const SESSION_KEY: &str = "taste_memory_session";

pub fn capture_compose_memory(
    conn: &Connection,
    prompt: &str,
    steer: Option<&SteerPayload>,
    response: &ComposerResponse,
) -> LyraResult<TasteMemorySnapshot> {
    let now = Utc::now();
    let observations = observe_preferences(prompt, steer);
    for observation in &observations {
        upsert_preference(conn, observation, now)?;
    }
    let route_preference = observe_route_preference(prompt, response);
    if let Some(route) = route_preference {
        insert_route_preference(conn, &route)?;
    }

    let session = SessionTastePosture {
        active_signals: active_session_signals(prompt, steer, response),
        summary: session_summary(prompt, response),
        confidence_note: session_confidence_note(observations.len(), response),
        updated_at: now.to_rfc3339(),
    };
    conn.execute(
        "INSERT INTO session_state (key, value_json) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
        params![SESSION_KEY, serde_json::to_string(&session)?],
    )?;

    load_snapshot(conn)
}

pub fn load_snapshot(conn: &Connection) -> LyraResult<TasteMemorySnapshot> {
    let session_posture = conn
        .query_row(
            "SELECT value_json FROM session_state WHERE key = ?1",
            params![SESSION_KEY],
            |row| row.get::<_, String>(0),
        )
        .ok()
        .and_then(|value| serde_json::from_str::<SessionTastePosture>(&value).ok())
        .unwrap_or_default();

    let mut stmt = conn.prepare(
        "SELECT axis_key,
                axis_label,
                preferred_pole,
                confidence,
                evidence_count,
                last_seen_at,
                supporting_phrases_json
         FROM taste_memory_preferences
         ORDER BY confidence DESC, last_seen_at DESC
         LIMIT 8",
    )?;
    let remembered_preferences = stmt
        .query_map([], |row| {
            let last_seen_at: String = row.get(5)?;
            let supporting_phrases_json: String = row.get(6)?;
            let supporting_phrases =
                serde_json::from_str::<Vec<String>>(&supporting_phrases_json).unwrap_or_default();
            Ok(RememberedPreference {
                axis_key: row.get(0)?,
                axis_label: row.get(1)?,
                preferred_pole: row.get(2)?,
                confidence: row.get::<_, f64>(3)?.clamp(0.0, 1.0),
                evidence_count: row.get(4)?,
                recency_note: recency_note(&last_seen_at),
                confidence_note: confidence_note(row.get::<_, f64>(3)?, row.get::<_, i64>(4)?),
                last_seen_at,
                supporting_phrases,
            })
        })?
        .filter_map(Result::ok)
        .collect::<Vec<_>>();

    let mut route_stmt = conn.prepare(
        "SELECT route_kind, action, source, note, outcome, confidence, observed_at
         FROM taste_route_history
         ORDER BY observed_at DESC
         LIMIT 6",
    )?;
    let route_preferences = route_stmt
        .query_map([], |row| {
            Ok(RouteChoicePreference {
                route_kind: row.get(0)?,
                action: row.get(1)?,
                source: row.get(2)?,
                note: row.get(3)?,
                outcome: row.get(4)?,
                confidence: row.get::<_, f64>(5)?.clamp(0.0, 1.0),
                observed_at: row.get(6)?,
            })
        })?
        .filter_map(Result::ok)
        .collect::<Vec<_>>();

    let summary_lines = summary_lines(
        &session_posture,
        &remembered_preferences,
        &route_preferences,
    );

    Ok(TasteMemorySnapshot {
        session_posture,
        remembered_preferences,
        route_preferences,
        summary_lines,
    })
}

pub fn record_route_feedback(
    conn: &Connection,
    payload: &RouteFeedbackPayload,
) -> LyraResult<TasteMemorySnapshot> {
    let confidence = match payload.outcome.as_str() {
        "accepted" => 0.8,
        "rejected" => 0.72,
        _ => 0.54,
    };
    let note = payload
        .note
        .clone()
        .unwrap_or_else(|| route_note(&payload.route_kind).to_string());
    let route = RouteChoicePreference {
        route_kind: payload.route_kind.clone(),
        action: payload.action.clone(),
        source: payload.source.clone(),
        note,
        outcome: payload.outcome.clone(),
        confidence,
        observed_at: Utc::now().to_rfc3339(),
    };
    insert_route_preference(conn, &route)?;
    load_snapshot(conn)
}

fn upsert_preference(
    conn: &Connection,
    observation: &ObservedPreference,
    now: DateTime<Utc>,
) -> LyraResult<()> {
    let existing = conn
        .query_row(
            "SELECT confidence, evidence_count, supporting_phrases_json
             FROM taste_memory_preferences
             WHERE axis_key = ?1",
            params![observation.axis_key],
            |row| {
                Ok((
                    row.get::<_, f64>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, String>(2)?,
                ))
            },
        )
        .ok();

    let (existing_confidence, evidence_count, phrases_json) =
        existing.unwrap_or((0.0, 0, "[]".to_string()));
    let mut phrases = serde_json::from_str::<Vec<String>>(&phrases_json).unwrap_or_default();
    if !phrases.contains(&observation.phrase) {
        phrases.insert(0, observation.phrase.clone());
    }
    phrases.truncate(6);
    let next_evidence_count = evidence_count + 1;
    let next_confidence =
        (existing_confidence * 0.72 + observation.weight * 0.28).clamp(0.18, 0.82);

    conn.execute(
        "INSERT INTO taste_memory_preferences (
            axis_key,
            axis_label,
            preferred_pole,
            confidence,
            evidence_count,
            last_seen_at,
            supporting_phrases_json
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(axis_key) DO UPDATE SET
            axis_label = excluded.axis_label,
            preferred_pole = excluded.preferred_pole,
            confidence = excluded.confidence,
            evidence_count = excluded.evidence_count,
            last_seen_at = excluded.last_seen_at,
            supporting_phrases_json = excluded.supporting_phrases_json",
        params![
            observation.axis_key,
            observation.axis_label,
            observation.preferred_pole,
            next_confidence,
            next_evidence_count,
            now.to_rfc3339(),
            serde_json::to_string(&phrases)?,
        ],
    )?;
    Ok(())
}

fn observe_preferences(prompt: &str, steer: Option<&SteerPayload>) -> Vec<ObservedPreference> {
    let lower = prompt.to_ascii_lowercase();
    let mut observed = Vec::new();
    for (needle, axis_key, axis_label, preferred_pole, weight) in [
        (
            "less obvious",
            "obviousness",
            "Obvious vs less obvious",
            "less obvious",
            0.74,
        ),
        (
            "adjacent but not the canon",
            "obviousness",
            "Obvious vs less obvious",
            "less obvious",
            0.8,
        ),
        (
            "more obvious",
            "obviousness",
            "Obvious vs less obvious",
            "more obvious",
            0.72,
        ),
        (
            "more adventurous",
            "familiarity",
            "Familiar vs adventurous",
            "adventurous",
            0.74,
        ),
        (
            "less adventurous",
            "familiarity",
            "Familiar vs adventurous",
            "familiar",
            0.66,
        ),
        (
            "smoother",
            "transition",
            "Smoother vs sharper",
            "smoother",
            0.7,
        ),
        (
            "sharper",
            "transition",
            "Smoother vs sharper",
            "sharper",
            0.72,
        ),
        (
            "more nocturnal",
            "daylight",
            "Brighter vs nocturnal",
            "nocturnal",
            0.76,
        ),
        (
            "brighter",
            "daylight",
            "Brighter vs nocturnal",
            "brighter",
            0.7,
        ),
        ("warmer", "warmth", "Cooler vs warmer", "warmer", 0.72),
        (
            "rougher",
            "polish",
            "Rougher and human vs cleaner and polished",
            "rougher",
            0.78,
        ),
        (
            "more human",
            "polish",
            "Rougher and human vs cleaner and polished",
            "more human",
            0.8,
        ),
        (
            "dirtier",
            "polish",
            "Rougher and human vs cleaner and polished",
            "rougher",
            0.78,
        ),
        (
            "cleaner",
            "polish",
            "Rougher and human vs cleaner and polished",
            "cleaner",
            0.72,
        ),
        (
            "keep the ache",
            "ache",
            "Preserve ache",
            "keep the ache",
            0.82,
        ),
        (
            "don't lose the pulse",
            "pulse",
            "Preserve pulse",
            "keep the pulse",
            0.82,
        ),
        (
            "less obvious, still aching, keep the pulse",
            "ache",
            "Preserve ache",
            "keep the ache",
            0.84,
        ),
    ] {
        if lower.contains(needle) {
            observed.push(ObservedPreference {
                axis_key,
                axis_label,
                preferred_pole,
                phrase: needle.to_string(),
                weight,
            });
        }
    }

    if let Some(steer) = steer {
        if steer.novelty_bias.unwrap_or(0.5) >= 0.68 {
            observed.push(observed_from_steer(
                "obviousness",
                "Obvious vs less obvious",
                "less obvious",
                "novelty bias",
                0.68,
            ));
        } else if steer.novelty_bias.unwrap_or(0.5) <= 0.32 {
            observed.push(observed_from_steer(
                "obviousness",
                "Obvious vs less obvious",
                "more obvious",
                "novelty bias",
                0.64,
            ));
        }
        if steer.adventurousness.unwrap_or(0.5) >= 0.68 {
            observed.push(observed_from_steer(
                "familiarity",
                "Familiar vs adventurous",
                "adventurous",
                "adventurousness",
                0.7,
            ));
        } else if steer.adventurousness.unwrap_or(0.5) <= 0.32 {
            observed.push(observed_from_steer(
                "familiarity",
                "Familiar vs adventurous",
                "familiar",
                "adventurousness",
                0.64,
            ));
        }
        if steer.contrast_sharpness.unwrap_or(0.5) >= 0.68 {
            observed.push(observed_from_steer(
                "transition",
                "Smoother vs sharper",
                "sharper",
                "contrast sharpness",
                0.68,
            ));
        } else if steer.contrast_sharpness.unwrap_or(0.5) <= 0.32 {
            observed.push(observed_from_steer(
                "transition",
                "Smoother vs sharper",
                "smoother",
                "contrast sharpness",
                0.66,
            ));
        }
        if steer.warmth_bias.unwrap_or(0.5) >= 0.68 {
            observed.push(observed_from_steer(
                "daylight",
                "Brighter vs nocturnal",
                "nocturnal",
                "warmth bias",
                0.68,
            ));
            observed.push(observed_from_steer(
                "warmth",
                "Cooler vs warmer",
                "warmer",
                "warmth bias",
                0.66,
            ));
        } else if steer.warmth_bias.unwrap_or(0.5) <= 0.32 {
            observed.push(observed_from_steer(
                "daylight",
                "Brighter vs nocturnal",
                "brighter",
                "warmth bias",
                0.62,
            ));
        }
    }

    dedupe_preferences(observed)
}

fn observed_from_steer(
    axis_key: &'static str,
    axis_label: &'static str,
    preferred_pole: &'static str,
    phrase: &'static str,
    weight: f64,
) -> ObservedPreference {
    ObservedPreference {
        axis_key,
        axis_label,
        preferred_pole,
        phrase: phrase.to_string(),
        weight,
    }
}

fn dedupe_preferences(observed: Vec<ObservedPreference>) -> Vec<ObservedPreference> {
    let mut deduped = Vec::new();
    for item in observed {
        if !deduped.iter().any(|existing: &ObservedPreference| {
            existing.axis_key == item.axis_key && existing.preferred_pole == item.preferred_pole
        }) {
            deduped.push(item);
        }
    }
    deduped
}

fn insert_route_preference(conn: &Connection, route: &RouteChoicePreference) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO taste_route_history (
            action,
            route_kind,
            source,
            outcome,
            note,
            confidence,
            observed_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
        params![
            route.action,
            route.route_kind,
            route.source,
            route.outcome,
            route.note,
            route.confidence,
            route.observed_at,
        ],
    )?;
    Ok(())
}

fn observe_route_preference(
    prompt: &str,
    response: &ComposerResponse,
) -> Option<RouteChoicePreference> {
    let lower = prompt.to_ascii_lowercase();
    let route_kind = if lower.contains("safe") {
        "safe"
    } else if lower.contains("dangerous") || lower.contains("rewarding risk") {
        "dangerous"
    } else if lower.contains("interesting") || lower.contains("adjacent but not the canon") {
        "interesting"
    } else {
        match response.action {
            ComposerAction::Bridge => response
                .bridge
                .as_ref()
                .map(|bridge| bridge.route_flavor.as_str())
                .unwrap_or("direct_bridge"),
            ComposerAction::Discovery => response
                .discovery
                .as_ref()
                .and_then(|route| route.directions.first())
                .map(|direction| direction.flavor.as_str())
                .unwrap_or("interesting"),
            _ => return None,
        }
    };
    Some(RouteChoicePreference {
        route_kind: route_kind.to_string(),
        action: format!("{:?}", response.action).to_ascii_lowercase(),
        source: if lower.contains("three exits") || lower.contains("three ways") {
            "explicit route ask".to_string()
        } else {
            "prompt pressure".to_string()
        },
        note: route_note(route_kind).to_string(),
        outcome: "observed".to_string(),
        confidence: (response.intent.confidence * 0.84).clamp(0.24, 0.78),
        observed_at: Utc::now().to_rfc3339(),
    })
}

fn route_note(route_kind: &str) -> &'static str {
    match route_kind {
        "safe" => "When routes are compared explicitly, the safer lane still gets asked for.",
        "dangerous" => "When the user asks for risk, it is framed as rewarding rather than random.",
        "interesting" => "Lyra keeps seeing pressure toward the more interesting lane once the obvious choice is named.",
        "scenic" => "The user tolerates a longer scenic hinge when it preserves the emotional weather.",
        "contrast" => "The user will accept a sharper jump if one live wire survives it.",
        _ => "Route selection is still light evidence, not a fixed preference.",
    }
}

fn active_session_signals(
    prompt: &str,
    steer: Option<&SteerPayload>,
    response: &ComposerResponse,
) -> Vec<String> {
    let mut signals = observe_preferences(prompt, steer)
        .into_iter()
        .map(|item| item.preferred_pole.to_string())
        .collect::<Vec<_>>();
    if response.action == ComposerAction::Discovery {
        signals.push("adjacency hunting".to_string());
    }
    if response.action == ComposerAction::Bridge {
        signals.push("hinge-sensitive".to_string());
    }
    signals.sort();
    signals.dedup();
    signals.truncate(6);
    signals
}

fn session_summary(prompt: &str, response: &ComposerResponse) -> String {
    let lower = prompt.to_ascii_lowercase();
    if lower.contains("keep the ache") || lower.contains("ache") {
        "Session posture is protecting the ache before spending novelty.".to_string()
    } else if lower.contains("pulse") {
        "Session posture is preserving pulse while changing surface.".to_string()
    } else if matches!(
        response.action,
        ComposerAction::Discovery | ComposerAction::Bridge
    ) {
        "Session posture is looking for believable adjacency, not just nearest-neighbor similarity."
            .to_string()
    } else {
        "Session posture is still light; Lyra only has recent steering pressure, not a durable profile.".to_string()
    }
}

fn session_confidence_note(observation_count: usize, response: &ComposerResponse) -> String {
    if observation_count <= 1 {
        "This is a thin read from one move, so Lyra is keeping the memory provisional.".to_string()
    } else if response.intent.confidence < 0.6 {
        "The signals are real but the prompt landing stayed ambiguous, so memory confidence stays moderate.".to_string()
    } else {
        "Recent steering is coherent enough to shape the next route, but not strong enough to overrule the prompt.".to_string()
    }
}

fn summary_lines(
    session_posture: &SessionTastePosture,
    remembered_preferences: &[RememberedPreference],
    route_preferences: &[RouteChoicePreference],
) -> Vec<String> {
    let mut lines = Vec::new();
    if !session_posture.summary.is_empty() {
        lines.push(session_posture.summary.clone());
    }
    if let Some(preference) = remembered_preferences.first() {
        lines.push(format!(
            "Recent memory leans {} on {}.",
            preference.preferred_pole, preference.axis_label
        ));
    }
    if let Some(route) = route_preferences.first() {
        let route_read = match route.outcome.as_str() {
            "accepted" => format!(
                "you accepted the {} lane {}",
                route.route_kind,
                recency_note(&route.observed_at)
            ),
            "rejected" => format!(
                "you rejected the {} lane {}",
                route.route_kind,
                recency_note(&route.observed_at)
            ),
            _ => format!(
                "{} showed up {}",
                route.route_kind,
                recency_note(&route.observed_at)
            ),
        };
        lines.push(format!("Route history is still light, but {}.", route_read));
    }
    lines.truncate(3);
    lines
}

fn recency_note(timestamp: &str) -> String {
    let parsed = DateTime::parse_from_rfc3339(timestamp)
        .map(|value| value.with_timezone(&Utc))
        .ok();
    match parsed.map(|value| Utc::now() - value) {
        Some(delta) if delta <= Duration::hours(4) => "in the last few hours".to_string(),
        Some(delta) if delta <= Duration::days(2) => "recently".to_string(),
        Some(_) => "a while ago".to_string(),
        None => "recently".to_string(),
    }
}

fn confidence_note(confidence: f64, evidence_count: i64) -> String {
    if evidence_count <= 1 || confidence < 0.45 {
        "Very light evidence; this is a nudge, not a stable rule.".to_string()
    } else if evidence_count <= 3 || confidence < 0.68 {
        "Some repetition is present, but Lyra is still treating this as a soft preference."
            .to_string()
    } else {
        "Repeated enough to bias route choices, but still overrideable by the prompt.".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::commands::{
        ComposerProviderStatus, ConfidenceVoice, DetailDepth, FallbackVoice, LyraFraming,
        LyraReadSurface, PlaylistIntent, ResponsePosture,
    };
    use crate::db;

    fn setup() -> Connection {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("db");
        conn
    }

    fn response(action: ComposerAction) -> ComposerResponse {
        ComposerResponse {
            action,
            prompt: "less obvious, still aching, keep the pulse".to_string(),
            intent: PlaylistIntent {
                prompt: "less obvious, still aching, keep the pulse".to_string(),
                prompt_role: "copilot".to_string(),
                source_energy: "medium".to_string(),
                destination_energy: "low".to_string(),
                opening_state: Default::default(),
                landing_state: Default::default(),
                transition_style: "gradual cooling".to_string(),
                emotional_arc: vec!["ache".to_string()],
                texture_descriptors: vec!["rough".to_string()],
                explicit_entities: Vec::new(),
                familiarity_vs_novelty: "novel leaning".to_string(),
                discovery_aggressiveness: "assertive".to_string(),
                user_steer: Vec::new(),
                exclusions: Vec::new(),
                explanation_depth: "balanced".to_string(),
                sequencing_notes: Vec::new(),
                confidence_notes: Vec::new(),
                confidence: 0.66,
            },
            provider_status: ComposerProviderStatus {
                requested_provider: "auto".to_string(),
                selected_provider: "heuristic".to_string(),
                provider_kind: "deterministic".to_string(),
                mode: "fallback".to_string(),
                fallback_reason: None,
            },
            framing: LyraFraming {
                posture: ResponsePosture::Collaborative,
                detail_depth: DetailDepth::Medium,
                lead: String::new(),
                rationale: String::new(),
                presence_note: None,
                challenge: None,
                vibe_guard: None,
                confidence: ConfidenceVoice {
                    level: "medium".to_string(),
                    phrasing: String::new(),
                    should_offer_alternatives: true,
                },
                fallback: FallbackVoice {
                    active: true,
                    label: "heuristic".to_string(),
                    message: String::new(),
                },
                route_comparison: None,
                lyra_read: LyraReadSurface {
                    summary: String::new(),
                    cues: Vec::new(),
                    confidence_note: String::new(),
                },
                sideways_temptations: Vec::new(),
                memory_hint: None,
                next_nudges: Vec::new(),
            },
            draft: None,
            bridge: None,
            discovery: None,
            explanation: None,
            active_role: "copilot".to_string(),
            uncertainty: Vec::new(),
            alternatives_considered: Vec::new(),
            taste_memory: TasteMemorySnapshot::default(),
        }
    }

    #[test]
    fn captures_memory_without_overclaiming() {
        let conn = setup();
        let snapshot = capture_compose_memory(
            &conn,
            "less obvious, still aching, keep the pulse",
            Some(&SteerPayload {
                novelty_bias: Some(0.8),
                warmth_bias: Some(0.7),
                ..SteerPayload::default()
            }),
            &response(ComposerAction::Discovery),
        )
        .expect("snapshot");

        assert!(!snapshot.remembered_preferences.is_empty());
        assert!(snapshot
            .remembered_preferences
            .iter()
            .any(
                |preference| preference.confidence_note.contains("light evidence")
                    || preference.confidence_note.contains("soft preference")
            ));
        assert!(snapshot
            .summary_lines
            .iter()
            .any(|line| line.contains("ache") || line.contains("recent memory")));
    }

    #[test]
    fn explicit_route_feedback_enters_memory_without_overclaiming() {
        let conn = setup();
        let snapshot = record_route_feedback(
            &conn,
            &RouteFeedbackPayload {
                route_kind: "interesting".to_string(),
                action: "discovery".to_string(),
                outcome: "accepted".to_string(),
                source: "ui route comparison".to_string(),
                note: Some(
                    "User chose the more interesting lane once the options were visible."
                        .to_string(),
                ),
            },
        )
        .expect("snapshot");

        assert_eq!(snapshot.route_preferences.len(), 1);
        assert_eq!(snapshot.route_preferences[0].outcome, "accepted");
        assert!(snapshot
            .summary_lines
            .iter()
            .any(|line| line.contains("accepted")));
    }
}

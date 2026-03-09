use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{
    GeneratedPlaylist, PlaylistDetail, PlaylistSummary, PlaylistTrackReasonRecord,
    PlaylistTrackWithReason, TrackReasonPayload, TrackRecord,
};
use crate::errors::{LyraError, LyraResult};
use crate::library::get_track_by_id;
use crate::llm_client::LlmClient;

pub fn list_playlists(conn: &Connection) -> LyraResult<Vec<PlaylistSummary>> {
    let mut stmt = conn.prepare(
        "
        SELECT p.id, p.name, p.description, COUNT(pi.id)
        FROM playlists p
        LEFT JOIN playlist_items pi ON pi.playlist_id = p.id
        GROUP BY p.id, p.name, p.description
        ORDER BY p.updated_at DESC, p.name ASC
        ",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(PlaylistSummary {
            id: row.get(0)?,
            name: row.get(1)?,
            description: row.get(2)?,
            item_count: row.get(3)?,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn create_playlist(conn: &Connection, name: &str) -> LyraResult<i64> {
    conn.execute(
        "INSERT INTO playlists (name, description, created_at, updated_at) VALUES (?1, '', ?2, ?2)",
        params![name, Utc::now().to_rfc3339()],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn ensure_playlist(conn: &Connection, name: &str, description: &str) -> LyraResult<i64> {
    if let Some(id) = conn
        .query_row(
            "SELECT id FROM playlists WHERE name = ?1",
            params![name],
            |row| row.get::<_, i64>(0),
        )
        .optional()?
    {
        return Ok(id);
    }
    conn.execute(
        "INSERT INTO playlists (name, description, created_at, updated_at) VALUES (?1, ?2, ?3, ?3)",
        params![name, description, Utc::now().to_rfc3339()],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn rename_playlist(conn: &Connection, playlist_id: i64, name: &str) -> LyraResult<()> {
    conn.execute(
        "UPDATE playlists SET name = ?2, updated_at = ?3 WHERE id = ?1",
        params![playlist_id, name, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

pub fn delete_playlist(conn: &Connection, playlist_id: i64) -> LyraResult<()> {
    conn.execute("DELETE FROM playlists WHERE id = ?1", params![playlist_id])?;
    Ok(())
}

pub fn get_playlist_detail(conn: &Connection, playlist_id: i64) -> LyraResult<PlaylistDetail> {
    let header = conn
        .query_row(
            "SELECT id, name, description FROM playlists WHERE id = ?1",
            params![playlist_id],
            |row| {
                Ok((
                    row.get::<_, i64>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                ))
            },
        )
        .optional()?
        .ok_or(LyraError::NotFound("playlist"))?;
    let mut stmt = conn.prepare(
        "SELECT track_id FROM playlist_items WHERE playlist_id = ?1 ORDER BY position ASC",
    )?;
    let rows = stmt.query_map(params![playlist_id], |row| row.get::<_, i64>(0))?;
    let mut items: Vec<TrackRecord> = Vec::new();
    for row in rows {
        if let Some(track) = get_track_by_id(conn, row?)? {
            items.push(track);
        }
    }
    Ok(PlaylistDetail {
        id: header.0,
        name: header.1,
        description: header.2,
        items,
    })
}

pub fn playlist_track_ids(conn: &Connection, playlist_id: i64) -> LyraResult<Vec<i64>> {
    let mut stmt = conn.prepare(
        "SELECT track_id FROM playlist_items WHERE playlist_id = ?1 ORDER BY position ASC",
    )?;
    let rows = stmt.query_map(params![playlist_id], |row| row.get::<_, i64>(0))?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn add_track_to_playlist(conn: &Connection, playlist_id: i64, track_id: i64) -> LyraResult<()> {
    let max_pos: i64 = conn
        .query_row(
            "SELECT COALESCE(MAX(position), -1) FROM playlist_items WHERE playlist_id = ?1",
            params![playlist_id],
            |row| row.get(0),
        )
        .unwrap_or(-1);
    conn.execute(
        "INSERT OR IGNORE INTO playlist_items (playlist_id, track_id, position) VALUES (?1, ?2, ?3)",
        params![playlist_id, track_id, max_pos + 1],
    )?;
    conn.execute(
        "UPDATE playlists SET updated_at = ?2 WHERE id = ?1",
        params![playlist_id, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

pub fn remove_track_from_playlist(
    conn: &Connection,
    playlist_id: i64,
    track_id: i64,
) -> LyraResult<()> {
    conn.execute(
        "DELETE FROM playlist_items WHERE playlist_id = ?1 AND track_id = ?2",
        params![playlist_id, track_id],
    )?;
    conn.execute(
        "UPDATE playlists SET updated_at = ?2 WHERE id = ?1",
        params![playlist_id, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

pub fn reorder_playlist_item(
    conn: &Connection,
    playlist_id: i64,
    track_id: i64,
    new_position: i64,
) -> LyraResult<()> {
    let mut items = playlist_track_ids(conn, playlist_id)?;
    if let Some(current_idx) = items.iter().position(|&id| id == track_id) {
        items.remove(current_idx);
        let insert_at = (new_position as usize).min(items.len());
        items.insert(insert_at, track_id);
    }
    for (idx, tid) in items.iter().enumerate() {
        conn.execute(
            "UPDATE playlist_items SET position = ?3 WHERE playlist_id = ?1 AND track_id = ?2",
            params![playlist_id, tid, idx as i64],
        )?;
    }
    conn.execute(
        "UPDATE playlists SET updated_at = ?2 WHERE id = ?1",
        params![playlist_id, Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

// ── Playlust: 4-Act HALFCOCKED.EXE dimensional targets ──────────────────────

/// Dimensional profile (energy, valence, tension, density, warmth, movement,
/// space, rawness, complexity, nostalgia) — all values 0.0–1.0.
type Dims = [f64; 10];

struct PlaylustAct {
    name: &'static str,
    label: &'static str,
    target: Dims,
    narrative_tone: &'static str,
    proportion: f64,
}

const ACTS: [PlaylustAct; 4] = [
    PlaylustAct {
        name: "aggressive",
        label: "Act I — Aggressive",
        // energy, valence, tension, density, warmth, movement, space, rawness, complexity, nostalgia
        target: [0.88, 0.38, 0.82, 0.78, 0.28, 0.85, 0.30, 0.80, 0.58, 0.35],
        narrative_tone: "confrontational, visceral, urgent",
        proportion: 0.25,
    },
    PlaylustAct {
        name: "seductive",
        label: "Act II — Seductive",
        target: [0.58, 0.72, 0.28, 0.52, 0.82, 0.68, 0.55, 0.32, 0.52, 0.55],
        narrative_tone: "seductive, hypnotic, inviting",
        proportion: 0.25,
    },
    PlaylustAct {
        name: "breakdown",
        label: "Act III — Breakdown",
        target: [0.22, 0.32, 0.62, 0.28, 0.38, 0.22, 0.85, 0.42, 0.42, 0.68],
        narrative_tone: "introspective, desolate, cavernous",
        proportion: 0.25,
    },
    PlaylustAct {
        name: "sublime",
        label: "Act IV — Sublime",
        target: [0.72, 0.82, 0.22, 0.62, 0.72, 0.62, 0.78, 0.28, 0.78, 0.48],
        narrative_tone: "transcendent, euphoric, resolved",
        proportion: 0.25,
    },
];

const DIM_NAMES: [&str; 10] = [
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

fn l1_distance(a: &Dims, b: &Dims) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| (x - y).abs()).sum()
}

/// Return the dimension name and fit score where track best matches target.
fn best_dim_fit(track: &Dims, target: &Dims) -> (&'static str, f64) {
    let mut best_name = DIM_NAMES[0];
    let mut best_fit = 0.0_f64;
    for (i, name) in DIM_NAMES.iter().enumerate() {
        let fit = 1.0 - (track[i] - target[i]).abs();
        if fit > best_fit {
            best_fit = fit;
            best_name = name;
        }
    }
    (best_name, best_fit)
}

/// Load taste profile as a Dims array (0.5 default per missing dimension).
fn load_taste_dims(conn: &Connection) -> Dims {
    let mut dims = [0.5_f64; 10];
    let Ok(mut stmt) = conn.prepare("SELECT dimension, value FROM taste_profile") else {
        return dims;
    };
    let rows = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
    });
    if let Ok(rows) = rows {
        for (dim_name, val) in rows.filter_map(Result::ok) {
            if let Some(idx) = DIM_NAMES.iter().position(|&n| n == dim_name.as_str()) {
                dims[idx] = val.clamp(0.0, 1.0);
            }
        }
    }
    dims
}

/// Blend act target with taste: `blended = (1-w)*target + w*taste`.
fn blend_target(target: &Dims, taste: &Dims, taste_weight: f64) -> Dims {
    let mut out = [0.0_f64; 10];
    for i in 0..10 {
        out[i] = (1.0 - taste_weight) * target[i] + taste_weight * taste[i];
    }
    out
}

/// Build a human-readable reason for a track within an act.
fn act_reason(act: &PlaylustAct, track_dims: &Dims, fit_score: f64) -> String {
    let (best_dim, best_fit) = best_dim_fit(track_dims, &act.target);
    let tone = act.narrative_tone.split(',').next().unwrap_or(act.name);
    if best_fit > 0.88 {
        format!(
            "{} — strong {} match ({:.0}% fit)",
            act.label,
            best_dim,
            fit_score * 100.0
        )
    } else {
        format!(
            "{} — {} ({:.0}% dimensional fit)",
            act.label,
            tone,
            fit_score * 100.0
        )
    }
}

/// Call the configured LLM (Groq/OpenRouter) to generate playlist liner notes.
/// Silent failure — returns None if the LLM is unavailable or unconfigured.
fn narrate_playlist_llm(
    act_openers: &[(&str, Vec<String>)],
    mood: &str,
    track_count: usize,
    conn: &Connection,
) -> Option<String> {
    let llm_client = LlmClient::from_connection(conn)?;

    let mood_line = if !mood.is_empty() && mood != "smart" {
        format!("The mood seed is: \"{}\".\n\n", mood)
    } else {
        String::new()
    };

    let acts_text: String = act_openers
        .iter()
        .map(|(label, tracks)| {
            if tracks.is_empty() {
                format!("  {}: (no tracks)\n", label)
            } else {
                format!("  {}: opens with {}\n", label, tracks.join(" / "))
            }
        })
        .collect();

    let prompt = format!(
        "You are writing liner notes for a carefully constructed playlist.\n\n\
         The playlist has four acts:\n\
         - Act I (Aggressive): confrontational, high-tension, maximum density\n\
         - Act II (Seductive): warmth floods in, tension dissolves, hypnotic groove\n\
         - Act III (Breakdown): everything strips back, vast space, introspection\n\
         - Act IV (Sublime): transcendent return, euphoric complexity, resolution\n\n\
         {}Total tracks: {}\n\nOpening acts:\n{}\n\
         Write 2-3 sentences of evocative liner notes. Be literary but concise. \
         No bullet points. First sentence establishes the journey. Last hints at catharsis.",
        mood_line, track_count, acts_text
    );

    let text = llm_client.chat_completion_text(
        "You are Lyra, a poetic music intelligence. \
         Describe playlists with evocative, sensory language. Be concise.",
        &prompt,
        200,
        0.85,
    )?;
    let trimmed = text.trim();
    if trimmed.len() > 20 {
        Some(trimmed.to_string())
    } else {
        None
    }
}

/// Generate a playlist using the 4-act HALFCOCKED.EXE methodology.
///
/// The `intent` string is used as a mood seed for narrative generation.
/// The four acts (Aggressive → Seductive → Breakdown → Sublime) are always
/// built from the dimensional targets regardless of intent, blended with the
/// user's taste profile at 35% weight.
pub fn generate_act_playlist(
    intent: &str,
    track_count: usize,
    conn: &Connection,
) -> LyraResult<GeneratedPlaylist> {
    use std::cmp::Ordering;
    use std::collections::HashSet;

    let taste = load_taste_dims(conn);
    let total = track_count.max(4);

    // Load all scored tracks once
    let mut stmt = conn.prepare(
        "SELECT ts.track_id,
                COALESCE(ts.energy, 0.5), COALESCE(ts.valence, 0.5),
                COALESCE(ts.tension, 0.5), COALESCE(ts.density, 0.5),
                COALESCE(ts.warmth, 0.5), COALESCE(ts.movement, 0.5),
                COALESCE(ts.space, 0.5), COALESCE(ts.rawness, 0.5),
                COALESCE(ts.complexity, 0.5), COALESCE(ts.nostalgia, 0.5),
                t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path,
                COALESCE(t.duration_seconds, 0), t.genre, t.year, t.bpm,
                t.key_signature, t.liked_at
         FROM track_scores ts
         JOIN tracks t ON t.id = ts.track_id
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
         LIMIT 5000",
    )?;

    let all_rows: Vec<(i64, Dims, TrackRecord)> = stmt
        .query_map([], |row| {
            let id: i64 = row.get(0)?;
            let dims: Dims = [
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
                row.get(7)?,
                row.get(8)?,
                row.get(9)?,
                row.get(10)?,
            ];
            let liked_at: Option<String> = row.get(20)?;
            let track = TrackRecord {
                id,
                title: row.get(11)?,
                artist: row.get(12)?,
                album: row.get(13)?,
                path: row.get(14)?,
                duration_seconds: row.get(15)?,
                genre: row.get(16)?,
                year: row.get(17)?,
                bpm: row.get(18)?,
                key_signature: row.get(19)?,
                liked: liked_at.is_some(),
                liked_at,
            };
            Ok((id, dims, track))
        })?
        .filter_map(Result::ok)
        .collect();

    let mut playlist_tracks: Vec<PlaylistTrackWithReason> = Vec::new();
    let mut used_ids: HashSet<i64> = HashSet::new();
    let mut act_openers: Vec<(&str, Vec<String>)> = Vec::new();

    for act in &ACTS {
        let n_act = ((act.proportion * total as f64).round() as usize).max(1);
        let blended = blend_target(&act.target, &taste, 0.35);

        // Sort unused tracks by L1 distance to blended target
        let mut candidates: Vec<(f64, usize)> = all_rows
            .iter()
            .enumerate()
            .filter(|(_, (id, _, _))| !used_ids.contains(id))
            .map(|(idx, (_, dims, _))| (l1_distance(dims, &blended), idx))
            .collect();
        candidates.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(Ordering::Equal));

        let mut openers: Vec<String> = Vec::new();
        for (rank_in_act, (dist, idx)) in candidates.iter().take(n_act).enumerate() {
            let (id, dims, track) = &all_rows[*idx];
            let fit_score = (1.0 - dist / 10.0).clamp(0.0, 1.0);
            let reason = act_reason(act, dims, fit_score);
            let position = playlist_tracks.len();
            if rank_in_act < 2 {
                openers.push(format!("{} - {}", track.artist, track.title));
            }
            playlist_tracks.push(PlaylistTrackWithReason {
                track: track.clone(),
                reason,
                position,
            });
            used_ids.insert(*id);
        }
        act_openers.push((act.label, openers));
    }

    // LLM narrative — silent failure, template fallback
    let narrative = narrate_playlist_llm(&act_openers, intent, playlist_tracks.len(), conn)
        .or_else(|| {
            let mood_clause = if !intent.is_empty() && intent != "smart" {
                format!(" seeded from \"{}\"", intent)
            } else {
                String::new()
            };
            Some(format!(
                "A {}-track journey{}. Four acts: aggressive confrontation, \
                 seductive warmth, stripped breakdown, and transcendent resolution. \
                 Built from your library using dimensional profiling.",
                playlist_tracks.len(),
                mood_clause
            ))
        });

    let name = format!("{} Journey", capitalize_first(intent));
    Ok(GeneratedPlaylist {
        name,
        intent: intent.to_string(),
        narrative,
        tracks: playlist_tracks,
    })
}

fn capitalize_first(s: &str) -> String {
    let mut chars = s.chars();
    match chars.next() {
        None => String::new(),
        Some(c) => c.to_uppercase().collect::<String>() + chars.as_str(),
    }
}

/// Save a generated playlist and persist per-track reasons.
pub fn save_generated_playlist(
    name: &str,
    playlist: &GeneratedPlaylist,
    conn: &Connection,
) -> LyraResult<i64> {
    let playlist_id = create_playlist(conn, name)?;
    for item in &playlist.tracks {
        add_track_to_playlist(conn, playlist_id, item.track.id)?;
        // Store reason
        conn.execute(
            "INSERT OR REPLACE INTO playlist_track_reasons (playlist_id, track_id, reason, reason_json, phase_key, phase_label, position)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
            params![
                playlist_id,
                item.track.id,
                item.reason,
                Option::<String>::None,
                Option::<String>::None,
                Option::<String>::None,
                item.position as i64
            ],
        )?;
    }
    Ok(playlist_id)
}

/// Return persisted reason payloads for a playlist.
pub fn get_playlist_track_reasons(
    conn: &Connection,
    playlist_id: i64,
) -> LyraResult<Vec<PlaylistTrackReasonRecord>> {
    let mut stmt = conn.prepare(
        "SELECT track_id, reason, reason_json, phase_key, phase_label, position
         FROM playlist_track_reasons
         WHERE playlist_id = ?1 ORDER BY position ASC",
    )?;
    let rows = stmt.query_map(params![playlist_id], |row| {
        let reason_json: Option<String> = row.get(2)?;
        let reason_payload = reason_json
            .as_deref()
            .and_then(|value| serde_json::from_str::<TrackReasonPayload>(value).ok());
        Ok(PlaylistTrackReasonRecord {
            track_id: row.get(0)?,
            reason: row.get(1)?,
            reason_payload,
            phase_key: row.get(3)?,
            phase_label: row.get(4)?,
            position: row.get::<_, i64>(5)? as usize,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn create_playlist_from_queue(conn: &Connection, name: &str) -> LyraResult<i64> {
    let playlist_id = create_playlist(conn, name)?;
    let track_ids: Vec<i64> = conn
        .prepare("SELECT track_id FROM queue_items ORDER BY position ASC")?
        .query_map([], |row| row.get::<_, i64>(0))?
        .filter_map(Result::ok)
        .collect();
    for (idx, track_id) in track_ids.iter().enumerate() {
        conn.execute(
            "INSERT OR IGNORE INTO playlist_items (playlist_id, track_id, position) VALUES (?1, ?2, ?3)",
            params![playlist_id, track_id, idx as i64],
        )?;
    }
    Ok(playlist_id)
}

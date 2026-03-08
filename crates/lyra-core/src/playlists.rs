use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{GeneratedPlaylist, PlaylistDetail, PlaylistSummary, PlaylistTrackWithReason, TrackRecord};
use crate::errors::{LyraError, LyraResult};
use crate::library::get_track_by_id;

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

/// Generate a playlist from an intent using taste scores.
pub fn generate_act_playlist(
    intent: &str,
    track_count: usize,
    conn: &Connection,
) -> LyraResult<GeneratedPlaylist> {
    use std::cmp::Ordering;

    // Fetch all scored tracks
    let mut stmt = conn.prepare(
        "SELECT ts.track_id, ts.energy, ts.valence, ts.tension, ts.space, ts.density,
                ts.warmth, ts.movement, ts.rawness, ts.complexity, ts.nostalgia,
                t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path,
                COALESCE(t.duration_seconds, 0), t.genre, t.year, t.bpm, t.key_signature,
                t.liked_at
         FROM track_scores ts
         JOIN tracks t ON t.id = ts.track_id
         LEFT JOIN artists ar ON ar.id = t.artist_id
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
         LIMIT 5000",
    )?;

    #[allow(clippy::type_complexity)]
    let rows: Vec<(i64, f64, f64, f64, f64, f64, f64, f64, f64, f64, f64, TrackRecord)> = stmt
        .query_map([], |row| {
            let track_id: i64 = row.get(0)?;
            let energy: f64 = row.get(1)?;
            let valence: f64 = row.get(2)?;
            let tension: f64 = row.get(3)?;
            let space: f64 = row.get(4)?;
            let density: f64 = row.get(5)?;
            let warmth: f64 = row.get(6)?;
            let movement: f64 = row.get(7)?;
            let rawness: f64 = row.get(8)?;
            let complexity: f64 = row.get(9)?;
            let nostalgia: f64 = row.get(10)?;
            let liked_at: Option<String> = row.get(20)?;
            let track = TrackRecord {
                id: track_id,
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
            Ok((track_id, energy, valence, tension, space, density, warmth, movement, rawness, complexity, nostalgia, track))
        })?
        .filter_map(Result::ok)
        .collect();

    // Score tracks based on intent
    let mut scored: Vec<(f64, String, TrackRecord)> = rows
        .into_iter()
        .map(|(_, energy, valence, tension, _space, _density, warmth, movement, rawness, complexity, _nostalgia, track)| {
            let (score, reason) = match intent {
                "energy" => (
                    energy,
                    format!("High energy track ({:.0}% energy)", energy * 100.0),
                ),
                "chill" => (
                    valence * 0.6 + (1.0 - tension) * 0.4,
                    format!("Chill profile: {:.0}% positive, {:.0}% low-tension", valence * 100.0, (1.0 - tension) * 100.0),
                ),
                "discovery" => (
                    (complexity + rawness) * 0.5,
                    format!("Discovery pick: complexity {:.0}%, rawness {:.0}%", complexity * 100.0, rawness * 100.0),
                ),
                "journey" => {
                    // Will re-sort for arc later — use energy as primary sort
                    (energy, format!("Journey arc track ({:.0}% energy)", energy * 100.0))
                },
                _ => {
                    // Smart mix: blend of warmth, valence, movement
                    let smart = warmth * 0.3 + valence * 0.4 + movement * 0.3;
                    (smart, format!("Smart mix: {:.0}% match across warmth, valence, movement", smart * 100.0))
                }
            };
            (score, reason, track)
        })
        .collect();

    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(Ordering::Equal));
    scored.truncate(track_count * 3); // pool for arc reordering

    // For journey intent, build a narrative arc
    let final_tracks: Vec<(TrackRecord, String)> = if intent == "journey" && scored.len() >= 4 {
        let count = track_count.min(scored.len());
        let mut result = Vec::with_capacity(count);
        let selected: Vec<_> = scored.into_iter().take(count).collect();

        // Sort by energy ascending, then build arc: low → rising → peak → cool-down
        let mut arc = selected;
        arc.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(Ordering::Equal));

        let mid = arc.len() / 2;
        let peak_start = (arc.len() * 3) / 4;

        for (pos, (score, _reason, track)) in arc.iter().enumerate() {
            let reason = if pos == 0 {
                format!("Opener: sets the tone with {:.0}% energy", score * 100.0)
            } else if pos < mid {
                format!("Rising energy: building to the peak ({:.0}%)", score * 100.0)
            } else if pos >= peak_start {
                format!("Peak moment: highest energy segment ({:.0}%)", score * 100.0)
            } else {
                format!("Cool-down: winding down gracefully ({:.0}% energy)", score * 100.0)
            };
            result.push((track.clone(), reason));
        }
        result
    } else {
        scored
            .into_iter()
            .take(track_count)
            .map(|(_, reason, track)| (track, reason))
            .collect()
    };

    let name = format!("{} Mix", capitalize_first(intent));
    let tracks = final_tracks
        .into_iter()
        .enumerate()
        .map(|(pos, (track, reason))| PlaylistTrackWithReason { track, reason, position: pos })
        .collect();

    Ok(GeneratedPlaylist {
        name,
        intent: intent.to_string(),
        tracks,
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
            "INSERT OR REPLACE INTO playlist_track_reasons (playlist_id, track_id, reason, position)
             VALUES (?1, ?2, ?3, ?4)",
            params![playlist_id, item.track.id, item.reason, item.position as i64],
        )?;
    }
    Ok(playlist_id)
}

/// Return (track_id, reason) pairs for a playlist.
pub fn get_playlist_track_reasons(
    conn: &Connection,
    playlist_id: i64,
) -> LyraResult<Vec<(i64, String)>> {
    let mut stmt = conn.prepare(
        "SELECT track_id, reason FROM playlist_track_reasons
         WHERE playlist_id = ?1 ORDER BY position ASC",
    )?;
    let rows = stmt.query_map(params![playlist_id], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
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

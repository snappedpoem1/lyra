use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{PlaylistDetail, PlaylistSummary, TrackRecord};
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

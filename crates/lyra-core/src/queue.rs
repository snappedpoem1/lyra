use rusqlite::{params, Connection};

use crate::commands::QueueItemRecord;
use crate::errors::{LyraError, LyraResult};
use crate::library::get_track_by_id;

pub fn enqueue_tracks(conn: &Connection, track_ids: &[i64]) -> LyraResult<()> {
    let base = next_position(conn)?;
    for (offset, track_id) in track_ids.iter().enumerate() {
        conn.execute(
            "INSERT INTO queue_items (track_id, position) VALUES (?1, ?2)",
            params![track_id, base + offset as i64],
        )?;
    }
    Ok(())
}

pub fn ensure_track_in_queue(conn: &Connection, track_id: i64) -> LyraResult<()> {
    let existing = conn.query_row(
        "SELECT id FROM queue_items WHERE track_id = ?1 LIMIT 1",
        params![track_id],
        |row| row.get::<_, i64>(0),
    );
    if existing.is_err() {
        enqueue_tracks(conn, &[track_id])?;
    }
    Ok(())
}

pub fn get_queue(conn: &Connection) -> LyraResult<Vec<QueueItemRecord>> {
    let mut stmt =
        conn.prepare("SELECT id, track_id, position FROM queue_items ORDER BY position ASC")?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, i64>(1)?,
            row.get::<_, i64>(2)?,
        ))
    })?;
    let mut items = Vec::new();
    for row in rows {
        let (id, track_id, position) = row?;
        if let Some(track) = get_track_by_id(conn, track_id)? {
            items.push(QueueItemRecord {
                id,
                position,
                track_id,
                title: track.title,
                artist: track.artist,
                album: track.album,
                path: track.path,
            });
        }
    }
    Ok(items)
}

pub fn move_queue_item(conn: &Connection, queue_item_id: i64, new_position: i64) -> LyraResult<()> {
    let queue = get_queue(conn)?;
    let mut ids: Vec<i64> = queue.iter().map(|item| item.id).collect();
    let index = ids
        .iter()
        .position(|id| *id == queue_item_id)
        .ok_or(LyraError::NotFound("queue item"))?;
    let item = ids.remove(index);
    let bounded = new_position.clamp(0, ids.len() as i64);
    ids.insert(bounded as usize, item);
    rewrite_positions(conn, &ids)
}

pub fn remove_queue_item(conn: &Connection, queue_item_id: i64) -> LyraResult<()> {
    conn.execute(
        "DELETE FROM queue_items WHERE id = ?1",
        params![queue_item_id],
    )?;
    let ids: Vec<i64> = conn
        .prepare("SELECT id FROM queue_items ORDER BY position ASC")?
        .query_map([], |row| row.get::<_, i64>(0))?
        .filter_map(Result::ok)
        .collect();
    rewrite_positions(conn, &ids)
}

pub fn clear_queue(conn: &Connection) -> LyraResult<()> {
    conn.execute("DELETE FROM queue_items", [])?;
    Ok(())
}

pub fn replace_queue(conn: &Connection, track_ids: &[i64]) -> LyraResult<()> {
    clear_queue(conn)?;
    enqueue_tracks(conn, track_ids)
}

fn next_position(conn: &Connection) -> LyraResult<i64> {
    conn.query_row(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM queue_items",
        [],
        |row| row.get(0),
    )
    .map_err(Into::into)
}

fn rewrite_positions(conn: &Connection, ids: &[i64]) -> LyraResult<()> {
    for (position, id) in ids.iter().enumerate() {
        conn.execute(
            "UPDATE queue_items SET position = ?2 WHERE id = ?1",
            params![id, position as i64],
        )?;
    }
    Ok(())
}

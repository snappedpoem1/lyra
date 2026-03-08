use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::AcquisitionQueueItem;
use crate::errors::LyraResult;

pub fn list_acquisition_queue(
    conn: &Connection,
    status_filter: Option<&str>,
) -> LyraResult<Vec<AcquisitionQueueItem>> {
    let sql = if status_filter.is_some() {
        "SELECT id, artist, title, album, status, priority_score, source, added_at,
                completed_at, error, retry_count
         FROM acquisition_queue WHERE status = ?1 ORDER BY priority_score DESC, id ASC"
    } else {
        "SELECT id, artist, title, album, status, priority_score, source, added_at,
                completed_at, error, retry_count
         FROM acquisition_queue ORDER BY priority_score DESC, id ASC"
    };

    let mut stmt = conn.prepare(sql)?;
    let mapper = |row: &rusqlite::Row<'_>| {
        Ok(AcquisitionQueueItem {
            id: row.get(0)?,
            artist: row.get(1)?,
            title: row.get(2)?,
            album: row.get(3)?,
            status: row.get(4)?,
            priority_score: row.get(5)?,
            source: row.get(6)?,
            added_at: row.get(7)?,
            completed_at: row.get(8)?,
            error: row.get(9)?,
            retry_count: row.get(10)?,
        })
    };

    let rows = if let Some(s) = status_filter {
        stmt.query_map(params![s], mapper)?
    } else {
        stmt.query_map([], mapper)?
    };

    Ok(rows.filter_map(Result::ok).collect())
}

pub fn add_acquisition_item(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
    source: Option<&str>,
    priority: f64,
) -> LyraResult<AcquisitionQueueItem> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO acquisition_queue (artist, title, album, status, priority_score, source, added_at)
         VALUES (?1, ?2, ?3, 'pending', ?4, ?5, ?6)",
        params![artist, title, album, priority, source, now],
    )?;
    let id = conn.last_insert_rowid();
    Ok(AcquisitionQueueItem {
        id,
        artist: artist.to_string(),
        title: title.to_string(),
        album: album.map(String::from),
        status: "pending".to_string(),
        priority_score: priority,
        source: source.map(String::from),
        added_at: now,
        completed_at: None,
        error: None,
        retry_count: 0,
    })
}

pub fn update_acquisition_status(
    conn: &Connection,
    id: i64,
    status: &str,
    error: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let completed_at = if status == "completed" || status == "failed" {
        Some(now.clone())
    } else {
        None
    };
    conn.execute(
        "UPDATE acquisition_queue SET status=?1, error=?2, completed_at=COALESCE(?3, completed_at)
         WHERE id=?4",
        params![status, error, completed_at, id],
    )?;
    let item = conn
        .query_row(
            "SELECT id, artist, title, album, status, priority_score, source, added_at,
                    completed_at, error, retry_count
             FROM acquisition_queue WHERE id=?1",
            params![id],
            |row| {
                Ok(AcquisitionQueueItem {
                    id: row.get(0)?,
                    artist: row.get(1)?,
                    title: row.get(2)?,
                    album: row.get(3)?,
                    status: row.get(4)?,
                    priority_score: row.get(5)?,
                    source: row.get(6)?,
                    added_at: row.get(7)?,
                    completed_at: row.get(8)?,
                    error: row.get(9)?,
                    retry_count: row.get(10)?,
                })
            },
        )
        .optional()?;
    Ok(item)
}

pub fn pending_count(conn: &Connection) -> i64 {
    conn.query_row(
        "SELECT COUNT(*) FROM acquisition_queue WHERE status='pending'",
        [],
        |row| row.get(0),
    )
    .unwrap_or(0)
}

pub fn import_queue_from_legacy(conn: &Connection, legacy: &Connection) -> LyraResult<usize> {
    let mut stmt = legacy.prepare(
        "SELECT artist, title, album, priority_score, source, added_at
         FROM acquisition_queue WHERE status='pending'",
    )?;
    let rows: Vec<_> = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, Option<f64>>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, Option<String>>(5)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();

    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;
    for (artist, title, album, priority, source, added_at) in rows {
        // Skip if already in queue
        let exists: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM acquisition_queue WHERE artist=?1 AND title=?2 AND status='pending'",
                params![artist, title],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if exists > 0 {
            continue;
        }
        conn.execute(
            "INSERT INTO acquisition_queue
             (artist, title, album, status, priority_score, source, added_at)
             VALUES (?1, ?2, ?3, 'pending', ?4, ?5, ?6)",
            params![
                artist,
                title,
                album,
                priority.unwrap_or(0.0),
                source,
                added_at.unwrap_or_else(|| now.clone()),
            ],
        )?;
        count += 1;
    }
    Ok(count)
}

pub fn import_spotify_library_as_queue(
    conn: &Connection,
    legacy: &Connection,
) -> LyraResult<usize> {
    // Import liked Spotify tracks that have no local match as acquisition targets
    let mut stmt = legacy.prepare(
        "SELECT sl.artist, sl.title, sl.album FROM spotify_library sl
         WHERE sl.source = 'liked'
         AND NOT EXISTS (
           SELECT 1 FROM tracks t
           WHERE lower(t.artist) = lower(sl.artist) AND lower(t.title) = lower(sl.title)
         )",
    )?;
    let rows: Vec<(String, String, Option<String>)> = stmt
        .query_map([], |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)))?
        .filter_map(Result::ok)
        .collect();

    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;
    for (artist, title, album) in rows {
        let exists: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM acquisition_queue WHERE artist=?1 AND title=?2",
                params![artist, title],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if exists > 0 {
            continue;
        }
        conn.execute(
            "INSERT INTO acquisition_queue
             (artist, title, album, status, priority_score, source, added_at)
             VALUES (?1, ?2, ?3, 'pending', 0.3, 'spotify_liked', ?4)",
            params![artist, title, album, now],
        )?;
        count += 1;
    }
    Ok(count)
}

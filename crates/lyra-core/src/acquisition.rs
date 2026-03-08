use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::commands::AcquisitionQueueItem;
use crate::errors::LyraResult;

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionQueueSummary {
    pub total_count: i64,
    pub pending_count: i64,
    pub completed_count: i64,
    pub failed_count: i64,
    pub skipped_count: i64,
    pub retrying_count: i64,
    pub average_priority: f64,
    pub oldest_pending_added_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionSourceSummary {
    pub source: String,
    pub total_count: i64,
    pub pending_count: i64,
    pub completed_count: i64,
    pub failed_count: i64,
    pub average_priority: f64,
}

pub fn list_acquisition_queue(
    conn: &Connection,
    status_filter: Option<&str>,
) -> LyraResult<Vec<AcquisitionQueueItem>> {
    let sql = if status_filter.is_some() {
        "SELECT id, artist, title, album, status, priority_score, source, added_at,
                completed_at, error, retry_count, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at
         FROM acquisition_queue WHERE status = ?1 ORDER BY priority_score DESC, id ASC"
    } else {
        "SELECT id, artist, title, album, status, priority_score, source, added_at,
                completed_at, error, retry_count, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at
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
            lifecycle_stage: row.get(11)?,
            lifecycle_progress: row.get(12)?,
            lifecycle_note: row.get(13)?,
            updated_at: row.get(14)?,
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
        "INSERT INTO acquisition_queue
         (artist, title, album, status, priority_score, source, added_at, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at)
         VALUES (?1, ?2, ?3, 'pending', ?4, ?5, ?6, 'acquire', 0.0, 'Queued', ?6)",
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
        added_at: now.clone(),
        completed_at: None,
        error: None,
        retry_count: 0,
        lifecycle_stage: Some("acquire".to_string()),
        lifecycle_progress: Some(0.0),
        lifecycle_note: Some("Queued".to_string()),
        updated_at: Some(now),
    })
}

pub fn update_acquisition_status(
    conn: &Connection,
    id: i64,
    status: &str,
    error: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let completed_at = if status == "completed" || status == "failed" || status == "skipped" {
        Some(now.clone())
    } else {
        None
    };
    let lifecycle_note = if status == "pending" {
        Some("Retry queued")
    } else {
        None
    };
    conn.execute(
        "UPDATE acquisition_queue
         SET status=?1,
             error=CASE WHEN ?1='pending' THEN NULL ELSE ?2 END,
             completed_at=CASE WHEN ?3 IS NULL THEN NULL ELSE ?3 END,
             retry_count=CASE WHEN ?1='pending' AND status='failed' THEN retry_count + 1 ELSE retry_count END,
             lifecycle_stage=CASE WHEN ?1='pending' THEN 'acquire' ELSE lifecycle_stage END,
             lifecycle_progress=CASE WHEN ?1='pending' THEN 0.0 ELSE lifecycle_progress END,
             lifecycle_note=CASE WHEN ?1='pending' THEN ?6 ELSE lifecycle_note END,
             updated_at=?4
         WHERE id=?5",
        params![status, error, completed_at, now, id, lifecycle_note],
    )?;
    let item = conn
        .query_row(
            "SELECT id, artist, title, album, status, priority_score, source, added_at,
                    completed_at, error, retry_count, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at
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
                    lifecycle_stage: row.get(11)?,
                    lifecycle_progress: row.get(12)?,
                    lifecycle_note: row.get(13)?,
                    updated_at: row.get(14)?,
                })
            },
        )
        .optional()?;
    Ok(item)
}

pub fn update_lifecycle(
    conn: &Connection,
    id: i64,
    stage: &str,
    progress: f64,
    note: Option<&str>,
) -> LyraResult<()> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET lifecycle_stage=?1, lifecycle_progress=?2, lifecycle_note=?3, updated_at=?4
         WHERE id=?5",
        params![stage, progress, note, now, id],
    )?;
    Ok(())
}

pub fn clear_completed(conn: &Connection) -> LyraResult<i64> {
    let affected = conn.execute(
        "DELETE FROM acquisition_queue WHERE status='completed' OR status='skipped'",
        [],
    )?;
    Ok(affected as i64)
}

pub fn set_priority(conn: &Connection, id: i64, priority_score: f64) -> LyraResult<()> {
    conn.execute(
        "UPDATE acquisition_queue SET priority_score=?1, updated_at=?2 WHERE id=?3",
        params![priority_score, Utc::now().to_rfc3339(), id],
    )?;
    Ok(())
}

pub fn pending_count(conn: &Connection) -> i64 {
    conn.query_row(
        "SELECT COUNT(*) FROM acquisition_queue WHERE status='pending'",
        [],
        |row| row.get(0),
    )
    .unwrap_or(0)
}

pub fn summarize_acquisition_queue(conn: &Connection) -> LyraResult<AcquisitionQueueSummary> {
    Ok(conn.query_row(
        "SELECT COUNT(*),
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END),
                SUM(CASE WHEN retry_count > 0 AND status != 'completed' THEN 1 ELSE 0 END),
                AVG(priority_score),
                MIN(CASE WHEN status = 'pending' THEN added_at ELSE NULL END)
         FROM acquisition_queue",
        [],
        |row| {
            Ok(AcquisitionQueueSummary {
                total_count: row.get(0)?,
                pending_count: row.get(1)?,
                completed_count: row.get(2)?,
                failed_count: row.get(3)?,
                skipped_count: row.get(4)?,
                retrying_count: row.get(5)?,
                average_priority: row.get::<_, Option<f64>>(6)?.unwrap_or(0.0),
                oldest_pending_added_at: row.get(7)?,
            })
        },
    )?)
}

pub fn list_acquisition_sources(conn: &Connection) -> LyraResult<Vec<AcquisitionSourceSummary>> {
    let mut stmt = conn.prepare(
        "SELECT COALESCE(NULLIF(source, ''), 'manual') AS source_key,
                COUNT(*) AS total_count,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                AVG(priority_score) AS average_priority
         FROM acquisition_queue
         GROUP BY source_key
         ORDER BY pending_count DESC, average_priority DESC, source_key ASC",
    )?;

    let rows = stmt.query_map([], |row| {
        Ok(AcquisitionSourceSummary {
            source: row.get(0)?,
            total_count: row.get(1)?,
            pending_count: row.get(2)?,
            completed_count: row.get(3)?,
            failed_count: row.get(4)?,
            average_priority: row.get::<_, Option<f64>>(5)?.unwrap_or(0.0),
        })
    })?;

    Ok(rows.filter_map(Result::ok).collect())
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

#[cfg(test)]
mod tests {
    use rusqlite::{params, Connection};

    use super::{
        add_acquisition_item, list_acquisition_sources, summarize_acquisition_queue,
        update_acquisition_status,
    };

    fn setup_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE acquisition_queue (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              artist TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL DEFAULT '',
              album TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              priority_score REAL NOT NULL DEFAULT 0.0,
              source TEXT,
              added_at TEXT NOT NULL,
              completed_at TEXT,
              error TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              lifecycle_stage TEXT,
              lifecycle_progress REAL,
              lifecycle_note TEXT,
              updated_at TEXT
            );
            ",
        )
        .expect("queue schema");
        conn
    }

    #[test]
    fn summarizes_queue_state() {
        let conn = setup_conn();
        let rows = [
            ("A", "One", Some("Album"), "pending", 0.9, Some("wishlist"), "2026-03-08T01:00:00Z", None::<String>, None::<String>, 0_i64),
            ("B", "Two", None, "failed", 0.6, Some("manual"), "2026-03-08T02:00:00Z", Some("2026-03-08T03:00:00Z".to_string()), Some("boom".to_string()), 2_i64),
            ("C", "Three", None, "completed", 0.4, Some("recommendation"), "2026-03-08T04:00:00Z", Some("2026-03-08T05:00:00Z".to_string()), None::<String>, 1_i64),
            ("D", "Four", None, "skipped", 0.2, None, "2026-03-08T06:00:00Z", Some("2026-03-08T07:00:00Z".to_string()), None::<String>, 0_i64),
        ];

        for (artist, title, album, status, priority, source, added_at, completed_at, error, retry_count) in rows {
            conn.execute(
                "INSERT INTO acquisition_queue
                 (artist, title, album, status, priority_score, source, added_at, completed_at, error, retry_count)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
                params![artist, title, album, status, priority, source, added_at, completed_at, error, retry_count],
            )
            .expect("insert acquisition row");
        }

        let summary = summarize_acquisition_queue(&conn).expect("summary");
        assert_eq!(summary.total_count, 4);
        assert_eq!(summary.pending_count, 1);
        assert_eq!(summary.completed_count, 1);
        assert_eq!(summary.failed_count, 1);
        assert_eq!(summary.skipped_count, 1);
        assert_eq!(summary.retrying_count, 1);
        assert_eq!(summary.oldest_pending_added_at.as_deref(), Some("2026-03-08T01:00:00Z"));
        assert!((summary.average_priority - 0.525).abs() < f64::EPSILON);
    }

    #[test]
    fn groups_queue_by_source() {
        let conn = setup_conn();
        let rows = [
            ("A", "One", "pending", 0.9, Some("wishlist")),
            ("B", "Two", "failed", 0.6, Some("wishlist")),
            ("C", "Three", "completed", 0.3, Some("manual")),
            ("D", "Four", "pending", 0.5, None),
        ];

        for (artist, title, status, priority, source) in rows {
            conn.execute(
                "INSERT INTO acquisition_queue
                 (artist, title, status, priority_score, source, added_at, retry_count)
                 VALUES (?1, ?2, ?3, ?4, ?5, '2026-03-08T01:00:00Z', 0)",
                params![artist, title, status, priority, source],
            )
            .expect("insert acquisition row");
        }

        let sources = list_acquisition_sources(&conn).expect("source summary");
        assert_eq!(sources.len(), 2);
        assert_eq!(sources[0].source, "wishlist");
        assert_eq!(sources[0].total_count, 2);
        assert_eq!(sources[0].pending_count, 1);
        assert_eq!(sources[0].failed_count, 1);
        assert_eq!(sources[1].source, "manual");
        assert_eq!(sources[1].total_count, 2);
        assert_eq!(sources[1].completed_count, 1);
        assert_eq!(sources[1].pending_count, 1);
    }

    #[test]
    fn retrying_failed_item_increments_retry_and_clears_error() {
        let conn = setup_conn();
        let item = add_acquisition_item(&conn, "A", "One", None, Some("manual"), 0.8)
            .expect("item inserted");
        let failed = update_acquisition_status(&conn, item.id, "failed", Some("boom"))
            .expect("failed update")
            .expect("item present");
        assert_eq!(failed.status, "failed");
        assert_eq!(failed.retry_count, 0);
        assert_eq!(failed.error.as_deref(), Some("boom"));
        assert!(failed.completed_at.is_some());

        let retried = update_acquisition_status(&conn, item.id, "pending", None)
            .expect("retry update")
            .expect("item present");
        assert_eq!(retried.status, "pending");
        assert_eq!(retried.retry_count, 1);
        assert_eq!(retried.error, None);
        assert_eq!(retried.completed_at, None);
        assert_eq!(retried.lifecycle_stage.as_deref(), Some("acquire"));
        assert_eq!(retried.lifecycle_progress, Some(0.0));
        assert_eq!(retried.lifecycle_note.as_deref(), Some("Retry queued"));
    }
}

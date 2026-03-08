use std::ffi::OsStr;
use std::path::Path;

use chrono::Utc;
use lofty::prelude::{Accessor, AudioFile, TaggedFileExt};
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{DuplicateCluster, LibraryOverview, LibraryRootRecord, ScanJobRecord, TrackRecord};
use crate::errors::LyraResult;

pub fn is_supported_audio_file(path: &Path) -> bool {
    matches!(
        path.extension().and_then(OsStr::to_str).map(|value| value.to_ascii_lowercase()),
        Some(ext) if ["mp3", "flac", "wav", "ogg", "m4a", "aac"].contains(&ext.as_str())
    )
}

pub fn add_library_root(conn: &Connection, path: &Path) -> LyraResult<()> {
    conn.execute(
        "INSERT OR IGNORE INTO library_roots (path, added_at) VALUES (?1, ?2)",
        params![path.to_string_lossy().to_string(), Utc::now().to_rfc3339()],
    )?;
    Ok(())
}

pub fn remove_library_root(conn: &Connection, root_id: i64) -> LyraResult<()> {
    conn.execute("DELETE FROM library_roots WHERE id = ?1", params![root_id])?;
    Ok(())
}

pub fn list_library_roots(conn: &Connection) -> LyraResult<Vec<LibraryRootRecord>> {
    let mut stmt =
        conn.prepare("SELECT id, path, added_at FROM library_roots ORDER BY added_at ASC")?;
    let rows = stmt.query_map([], |row| {
        Ok(LibraryRootRecord {
            id: row.get(0)?,
            path: row.get(1)?,
            added_at: row.get(2)?,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn get_library_overview(conn: &Connection) -> LyraResult<LibraryOverview> {
    Ok(LibraryOverview {
        track_count: count(conn, "tracks")?,
        album_count: count(conn, "albums")?,
        artist_count: count(conn, "artists")?,
        root_count: count(conn, "library_roots")?,
    })
}

pub fn list_tracks(conn: &Connection, query: Option<String>) -> LyraResult<Vec<TrackRecord>> {
    let q = query.unwrap_or_default();
    if q.trim().is_empty() {
        let mut stmt = conn.prepare(
            "
            SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
                   t.genre, t.year, t.bpm, t.key_signature, t.liked_at
            FROM tracks t
            LEFT JOIN artists ar ON ar.id = t.artist_id
            LEFT JOIN albums al ON al.id = t.album_id
            ORDER BY ar.name ASC, al.title ASC, t.title ASC
            LIMIT 500
            ",
        )?;
        let rows = stmt.query_map([], map_track)?;
        return Ok(rows.filter_map(Result::ok).collect());
    }

    // FTS5 search — sanitize query to safe prefix tokens
    let fts_query = sanitize_fts_query(&q);
    let fts_results: Vec<TrackRecord> = if !fts_query.is_empty() {
        let mut stmt = conn.prepare(
            "
            SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
                   t.genre, t.year, t.bpm, t.key_signature, t.liked_at
            FROM tracks t
            LEFT JOIN artists ar ON ar.id = t.artist_id
            LEFT JOIN albums al ON al.id = t.album_id
            JOIN tracks_fts ON tracks_fts.rowid = t.id
            WHERE tracks_fts MATCH ?1
            ORDER BY rank
            LIMIT 200
            ",
        )?;
        let rows = stmt.query_map(params![fts_query], map_track)?;
        rows.filter_map(Result::ok).collect()
    } else {
        Vec::new()
    };

    if !fts_results.is_empty() {
        return Ok(fts_results);
    }

    // Fallback to LIKE when FTS yields nothing (e.g., index not yet populated)
    let like_pattern = format!("%{}%", q);
    let mut stmt = conn.prepare(
        "
        SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
               t.genre, t.year, t.bpm, t.key_signature
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE t.title LIKE ?1 OR ar.name LIKE ?1 OR al.title LIKE ?1
        ORDER BY ar.name ASC, al.title ASC, t.title ASC
        LIMIT 200
        ",
    )?;
    let rows = stmt.query_map(params![like_pattern], map_track)?;
    Ok(rows.filter_map(Result::ok).collect())
}

/// Sanitize a user search string into a safe FTS5 MATCH expression.
/// Each whitespace-delimited token becomes a `"token"*` prefix clause joined by AND.
fn sanitize_fts_query(q: &str) -> String {
    let parts: Vec<String> = q
        .split_whitespace()
        .filter_map(|w| {
            let clean: String = w.chars().filter(|c| !r#""():*^+-"#.contains(*c)).collect();
            if clean.is_empty() { None } else { Some(format!("\"{clean}\"*")) }
        })
        .collect();
    parts.join(" AND ")
}

pub fn find_duplicates(conn: &Connection) -> LyraResult<Vec<DuplicateCluster>> {
    // Groups of tracks sharing the same (lower title, lower artist name) with > 1 entry
    let mut stmt = conn.prepare(
        "
        SELECT GROUP_CONCAT(t.id) AS ids
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        GROUP BY LOWER(t.title), LOWER(COALESCE(ar.name, ''))
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 100
        ",
    )?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(0))?;
    let id_groups: Vec<Vec<i64>> = rows
        .filter_map(Result::ok)
        .map(|ids_str| {
            ids_str
                .split(',')
                .filter_map(|s| s.trim().parse::<i64>().ok())
                .collect()
        })
        .collect();

    let mut clusters = Vec::new();
    for ids in id_groups {
        let mut tracks = Vec::new();
        for id in ids {
            if let Ok(Some(tr)) = get_track_by_id(conn, id) {
                tracks.push(tr);
            }
        }
        if tracks.len() > 1 {
            clusters.push(DuplicateCluster { tracks });
        }
    }
    Ok(clusters)
}

pub fn get_track_by_id(conn: &Connection, track_id: i64) -> LyraResult<Option<TrackRecord>> {
    conn.query_row(
        "
        SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
               t.genre, t.year, t.bpm, t.key_signature, t.liked_at
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE t.id = ?1
        ",
        params![track_id],
        map_track,
    )
    .optional()
    .map_err(Into::into)
}

pub fn list_track_ids_for_artist(conn: &Connection, artist_name: &str, limit: i64) -> LyraResult<Vec<i64>> {
    let mut stmt = conn.prepare(
        "
        SELECT t.id
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
        ORDER BY al.title ASC, t.title ASC
        LIMIT ?2
        ",
    )?;
    let rows = stmt.query_map(params![artist_name, limit], |row| row.get::<_, i64>(0))?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn list_track_ids_for_album(
    conn: &Connection,
    artist_name: &str,
    album_title: &str,
    limit: i64,
) -> LyraResult<Vec<i64>> {
    let mut stmt = conn.prepare(
        "
        SELECT t.id
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
          AND lower(trim(COALESCE(al.title, ''))) = lower(trim(?2))
        ORDER BY t.title ASC
        LIMIT ?3
        ",
    )?;
    let rows =
        stmt.query_map(params![artist_name, album_title, limit], |row| row.get::<_, i64>(0))?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn create_scan_job(conn: &Connection) -> LyraResult<ScanJobRecord> {
    conn.execute(
        "INSERT INTO scan_jobs (status, started_at) VALUES ('queued', ?1)",
        params![Utc::now().to_rfc3339()],
    )?;
    get_scan_job(conn, conn.last_insert_rowid())
}

pub fn get_scan_jobs(conn: &Connection) -> LyraResult<Vec<ScanJobRecord>> {
    let mut stmt = conn.prepare(
        "SELECT id, status, files_scanned, tracks_imported, started_at, finished_at FROM scan_jobs ORDER BY id DESC LIMIT 20",
    )?;
    let rows = stmt.query_map([], map_scan_job)?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn update_scan_job_status(
    conn: &Connection,
    job_id: i64,
    status: &str,
    files_scanned: i64,
    tracks_imported: i64,
) -> LyraResult<()> {
    let finished_at = if status == "completed" {
        Some(Utc::now().to_rfc3339())
    } else {
        None
    };
    conn.execute(
        "
        UPDATE scan_jobs
        SET status = ?2,
            files_scanned = ?3,
            tracks_imported = ?4,
            finished_at = COALESCE(?5, finished_at)
        WHERE id = ?1
        ",
        params![job_id, status, files_scanned, tracks_imported, finished_at],
    )?;
    Ok(())
}

pub fn import_track_from_path(conn: &Connection, path: &Path) -> LyraResult<bool> {
    let (title, artist, album, duration_seconds, genre, year) = read_audio_tags(path);
    let inserted = import_legacy_track(
        conn,
        &path.to_string_lossy(),
        &title,
        &artist,
        &album,
        duration_seconds,
    )?;
    if inserted && (genre.is_some() || year.is_some()) {
        let _ = conn.execute(
            "UPDATE tracks SET genre = COALESCE(?1, genre), year = COALESCE(?2, year) WHERE path = ?3",
            params![genre, year, path.to_string_lossy().as_ref()],
        );
    }
    Ok(inserted)
}

fn read_audio_tags(path: &Path) -> (String, String, String, f64, Option<String>, Option<String>) {
    let fallback_title = path
        .file_stem()
        .and_then(OsStr::to_str)
        .unwrap_or("Unknown Track")
        .to_string();
    let fallback_album = path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(OsStr::to_str)
        .unwrap_or("Unknown Album")
        .to_string();
    let fallback_artist = path
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.file_name())
        .and_then(OsStr::to_str)
        .unwrap_or("Unknown Artist")
        .to_string();

    let Ok(tagged) = lofty::read_from_path(path) else {
        return (
            fallback_title,
            fallback_artist,
            fallback_album,
            0.0,
            None,
            None,
        );
    };

    let duration = tagged.properties().duration().as_secs_f64();
    let tag = tagged.primary_tag().or_else(|| tagged.first_tag());

    let Some(tag) = tag else {
        return (
            fallback_title,
            fallback_artist,
            fallback_album,
            duration,
            None,
            None,
        );
    };

    let title = tag
        .title()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or(fallback_title);
    let artist = tag
        .artist()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or(fallback_artist);
    let album = tag
        .album()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or(fallback_album);
    let genre = tag.genre().filter(|s| !s.is_empty()).map(|s| s.to_string());
    let year = tag.year().map(|y| y.to_string());

    (title, artist, album, duration, genre, year)
}

pub fn import_legacy_track(
    conn: &Connection,
    path: &str,
    title: &str,
    artist: &str,
    album: &str,
    duration_seconds: f64,
) -> LyraResult<bool> {
    if conn
        .query_row(
            "SELECT id FROM tracks WHERE path = ?1",
            params![path],
            |row| row.get::<_, i64>(0),
        )
        .optional()?
        .is_some()
    {
        return Ok(false);
    }
    let artist_id = ensure_artist(conn, artist)?;
    let album_id = ensure_album(conn, artist_id, album)?;
    conn.execute(
        "
        INSERT INTO tracks (legacy_track_key, artist_id, album_id, title, path, duration_seconds, imported_at)
        VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
        ",
        params![path, artist_id, album_id, title, path, duration_seconds, Utc::now().to_rfc3339()],
    )?;
    Ok(true)
}

pub fn map_legacy_track_id(conn: &Connection, legacy_track_id: &str) -> LyraResult<Option<i64>> {
    conn.query_row(
        "SELECT id FROM tracks WHERE legacy_track_key = ?1 OR CAST(id AS TEXT) = ?1 OR path = ?1",
        params![legacy_track_id],
        |row| row.get::<_, i64>(0),
    )
    .optional()
    .map_err(Into::into)
}

/// Toggle the liked state of a track. Returns `true` if track is now liked.
pub fn toggle_like(conn: &Connection, track_id: i64) -> LyraResult<bool> {
    let liked_at: Option<String> = conn
        .query_row(
            "SELECT liked_at FROM tracks WHERE id = ?1",
            params![track_id],
            |row| row.get(0),
        )
        .optional()?
        .flatten();
    if liked_at.is_some() {
        conn.execute("UPDATE tracks SET liked_at = NULL WHERE id = ?1", params![track_id])?;
        Ok(false)
    } else {
        conn.execute(
            "UPDATE tracks SET liked_at = ?1 WHERE id = ?2",
            params![Utc::now().to_rfc3339(), track_id],
        )?;
        Ok(true)
    }
}

/// Return all liked tracks in order of when they were liked (newest first).
pub fn list_liked_tracks(conn: &Connection) -> LyraResult<Vec<TrackRecord>> {
    let mut stmt = conn.prepare(
        "
        SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
               t.genre, t.year, t.bpm, t.key_signature, t.liked_at
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE t.liked_at IS NOT NULL
        ORDER BY t.liked_at DESC
        LIMIT 1000
        ",
    )?;
    let rows = stmt.query_map([], map_track)?;
    Ok(rows.filter_map(Result::ok).collect())
}

fn ensure_artist(conn: &Connection, name: &str) -> LyraResult<i64> {
    conn.execute(
        "INSERT OR IGNORE INTO artists (name) VALUES (?1)",
        params![name],
    )?;
    conn.query_row(
        "SELECT id FROM artists WHERE name = ?1",
        params![name],
        |row| row.get(0),
    )
    .map_err(Into::into)
}

fn ensure_album(conn: &Connection, artist_id: i64, title: &str) -> LyraResult<i64> {
    conn.execute(
        "INSERT OR IGNORE INTO albums (artist_id, title) VALUES (?1, ?2)",
        params![artist_id, title],
    )?;
    conn.query_row(
        "SELECT id FROM albums WHERE artist_id = ?1 AND title = ?2",
        params![artist_id, title],
        |row| row.get(0),
    )
    .map_err(Into::into)
}

fn count(conn: &Connection, table: &str) -> LyraResult<i64> {
    let sql = format!("SELECT COUNT(*) FROM {table}");
    conn.query_row(&sql, [], |row| row.get(0))
        .map_err(Into::into)
}

fn get_scan_job(conn: &Connection, job_id: i64) -> LyraResult<ScanJobRecord> {
    conn.query_row(
        "SELECT id, status, files_scanned, tracks_imported, started_at, finished_at FROM scan_jobs WHERE id = ?1",
        params![job_id],
        map_scan_job,
    )
    .map_err(Into::into)
}

fn map_track(row: &rusqlite::Row<'_>) -> rusqlite::Result<TrackRecord> {
    let liked_at: Option<String> = row.get(10).unwrap_or(None);
    Ok(TrackRecord {
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
    })
}

fn map_scan_job(row: &rusqlite::Row<'_>) -> rusqlite::Result<ScanJobRecord> {
    Ok(ScanJobRecord {
        id: row.get(0)?,
        status: row.get(1)?,
        files_scanned: row.get(2)?,
        tracks_imported: row.get(3)?,
        started_at: row.get(4)?,
        finished_at: row.get(5)?,
    })
}

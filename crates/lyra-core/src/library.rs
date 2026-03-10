use std::ffi::OsStr;
use std::path::Path;

use chrono::Utc;
use lofty::prelude::{Accessor, AudioFile, TaggedFileExt};
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{
    CleanupIssue, CurationLogEntry, DuplicateCluster, LibraryCleanupPreview, LibraryOverview,
    LibraryRootRecord, ScanJobRecord, TrackRecord,
};
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

pub fn list_tracks(
    conn: &Connection,
    query: Option<String>,
    sort: Option<String>,
) -> LyraResult<Vec<TrackRecord>> {
    let q = query.unwrap_or_default();
    if q.trim().is_empty() {
        // Recently-added sort: most recently imported tracks first
        if sort.as_deref() == Some("recently_added") {
            let mut stmt = conn.prepare(
                "
                SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
                       t.genre, t.year, t.bpm, t.key_signature, t.liked_at
                FROM tracks t
                LEFT JOIN artists ar ON ar.id = t.artist_id
                LEFT JOIN albums al ON al.id = t.album_id
                WHERE (t.quarantined IS NULL OR t.quarantined = 0)
                ORDER BY t.imported_at DESC
                LIMIT 200
                ",
            )?;
            let rows = stmt.query_map([], map_track)?;
            return Ok(rows.filter_map(Result::ok).collect());
        }

        let mut stmt = conn.prepare(
            "
            SELECT t.id, t.title, COALESCE(ar.name, ''), COALESCE(al.title, ''), t.path, t.duration_seconds,
                   t.genre, t.year, t.bpm, t.key_signature, t.liked_at
            FROM tracks t
            LEFT JOIN artists ar ON ar.id = t.artist_id
            LEFT JOIN albums al ON al.id = t.album_id
            WHERE (t.quarantined IS NULL OR t.quarantined = 0)
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
              AND (t.quarantined IS NULL OR t.quarantined = 0)
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
               t.genre, t.year, t.bpm, t.key_signature, t.liked_at
        FROM tracks t
        LEFT JOIN artists ar ON ar.id = t.artist_id
        LEFT JOIN albums al ON al.id = t.album_id
        WHERE (t.title LIKE ?1 OR ar.name LIKE ?1 OR al.title LIKE ?1)
          AND (t.quarantined IS NULL OR t.quarantined = 0)
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
            if clean.is_empty() {
                None
            } else {
                Some(format!("\"{clean}\"*"))
            }
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
        WHERE (t.quarantined IS NULL OR t.quarantined = 0)
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

pub fn list_track_ids_for_artist(
    conn: &Connection,
    artist_name: &str,
    limit: i64,
) -> LyraResult<Vec<i64>> {
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
    let rows = stmt.query_map(params![artist_name, album_title, limit], |row| {
        row.get::<_, i64>(0)
    })?;
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

struct AudioTags {
    title: String,
    artist: String,
    album: String,
    duration_seconds: f64,
    genre: Option<String>,
    year: Option<String>,
    track_number: Option<u32>,
    disc_number: Option<u32>,
}

fn content_hash_fast(path: &Path) -> Option<String> {
    use std::io::Read;
    let mut buf = vec![0u8; 65536];
    let mut file = std::fs::File::open(path).ok()?;
    let n = file.read(&mut buf).ok()?;
    Some(format!("{:x}", md5::compute(&buf[..n])))
}

fn strip_feat(artist: &str) -> String {
    const MARKERS: &[&str] = &[
        " (feat.",
        " (ft.",
        " feat.",
        " feat ",
        " ft.",
        " ft ",
        " featuring ",
    ];
    let lower = artist.to_ascii_lowercase();
    for marker in MARKERS {
        if let Some(pos) = lower.find(marker) {
            return artist[..pos].trim().to_string();
        }
    }
    artist.trim().to_string()
}

fn read_audio_tags(path: &Path) -> AudioTags {
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
        return AudioTags {
            title: fallback_title,
            artist: fallback_artist,
            album: fallback_album,
            duration_seconds: 0.0,
            genre: None,
            year: None,
            track_number: None,
            disc_number: None,
        };
    };

    let duration = tagged.properties().duration().as_secs_f64();
    let tag = tagged.primary_tag().or_else(|| tagged.first_tag());

    let Some(tag) = tag else {
        return AudioTags {
            title: fallback_title,
            artist: fallback_artist,
            album: fallback_album,
            duration_seconds: duration,
            genre: None,
            year: None,
            track_number: None,
            disc_number: None,
        };
    };

    let title = tag
        .title()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or(fallback_title);
    let artist = tag
        .artist()
        .filter(|s| !s.is_empty())
        .map(|s| strip_feat(s.as_ref()))
        .unwrap_or(fallback_artist);
    let album = tag
        .album()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or(fallback_album);
    let genre = tag.genre().filter(|s| !s.is_empty()).map(|s| s.to_string());
    let year = tag.year().map(|y| y.to_string());
    let track_number = tag.track();
    let disc_number = tag.disk();

    AudioTags {
        title,
        artist,
        album,
        duration_seconds: duration,
        genre,
        year,
        track_number,
        disc_number,
    }
}

pub fn import_track_from_path(conn: &Connection, path: &Path) -> LyraResult<bool> {
    let tags = read_audio_tags(path);
    let path_str = path.to_string_lossy();
    let hash = content_hash_fast(path);
    let now = Utc::now().to_rfc3339();

    let existing_id: Option<i64> = conn
        .query_row(
            "SELECT id FROM tracks WHERE path = ?1",
            params![path_str.as_ref()],
            |row| row.get(0),
        )
        .optional()?;

    if let Some(track_id) = existing_id {
        let artist_id = ensure_artist(conn, &tags.artist)?;
        let album_id = ensure_album(conn, artist_id, &tags.album)?;
        conn.execute(
            "UPDATE tracks SET
                artist_id = ?1,
                album_id = ?2,
                title = ?3,
                duration_seconds = CASE WHEN ?4 > 0 THEN ?4 ELSE duration_seconds END,
                genre = COALESCE(NULLIF(?5, ''), genre),
                year = COALESCE(NULLIF(?6, ''), year),
                content_hash = COALESCE(?7, content_hash),
                track_number = COALESCE(?8, track_number),
                disc_number = COALESCE(?9, disc_number)
             WHERE id = ?10",
            params![
                artist_id,
                album_id,
                tags.title,
                tags.duration_seconds,
                tags.genre,
                tags.year,
                hash,
                tags.track_number.map(|n| n as i64),
                tags.disc_number.map(|n| n as i64),
                track_id
            ],
        )?;
        return Ok(false);
    }

    // New track — INSERT
    let artist_id = ensure_artist(conn, &tags.artist)?;
    let album_id = ensure_album(conn, artist_id, &tags.album)?;
    conn.execute(
        "INSERT INTO tracks
            (legacy_track_key, artist_id, album_id, title, path, duration_seconds,
             genre, year, content_hash, track_number, disc_number, imported_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
        params![
            path_str.as_ref(),
            artist_id,
            album_id,
            tags.title,
            path_str.as_ref(),
            tags.duration_seconds,
            tags.genre,
            tags.year,
            hash,
            tags.track_number.map(|n| n as i64),
            tags.disc_number.map(|n| n as i64),
            now
        ],
    )?;
    Ok(true)
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
        conn.execute(
            "UPDATE tracks SET liked_at = NULL WHERE id = ?1",
            params![track_id],
        )?;
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

/// Mark a set of tracks as quarantined (resolved duplicate). Logs the action.
pub fn resolve_duplicate_cluster(
    conn: &Connection,
    keep_track_id: i64,
    remove_track_ids: Vec<i64>,
) -> LyraResult<()> {
    // Ensure quarantined column exists (idempotent)
    let _ = conn.execute(
        "ALTER TABLE tracks ADD COLUMN quarantined INTEGER DEFAULT 0",
        [],
    );

    for &tid in &remove_track_ids {
        conn.execute(
            "UPDATE tracks SET quarantined = 1 WHERE id = ?1",
            params![tid],
        )?;
    }

    // Log the action
    let now = Utc::now().to_rfc3339();
    let all_ids = remove_track_ids
        .iter()
        .map(|id| id.to_string())
        .collect::<Vec<_>>()
        .join(",");
    let detail = format!("Kept track {keep_track_id}, quarantined: {all_ids}");
    let track_ids_json = serde_json::to_string(&remove_track_ids).unwrap_or_default();
    conn.execute(
        "INSERT INTO curation_log (action, track_ids_json, detail, created_at, undone)
         VALUES (?1, ?2, ?3, ?4, 0)",
        params!["resolve_duplicate", track_ids_json, detail, now],
    )?;
    Ok(())
}

/// Return recent curation log entries.
pub fn get_curation_log(conn: &Connection) -> LyraResult<Vec<CurationLogEntry>> {
    let mut stmt = conn.prepare(
        "SELECT id, action, track_ids_json, detail, created_at, undone
         FROM curation_log ORDER BY created_at DESC LIMIT 50",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
            row.get::<_, String>(3)?,
            row.get::<_, String>(4)?,
            row.get::<_, i64>(5)?,
        ))
    })?;
    let mut entries = Vec::new();
    for row in rows.filter_map(Result::ok) {
        let (log_id, action, track_ids_json, detail, created_at, undone) = row;
        let track_ids: Vec<i64> = serde_json::from_str(&track_ids_json).unwrap_or_default();
        entries.push(CurationLogEntry {
            log_id,
            action,
            track_ids,
            detail,
            created_at,
            undone: undone != 0,
        });
    }
    Ok(entries)
}

/// Undo a curation action by restoring quarantined tracks.
pub fn undo_curation(conn: &Connection, log_id: i64) -> LyraResult<()> {
    let track_ids_json: Option<String> = conn
        .query_row(
            "SELECT track_ids_json FROM curation_log WHERE id = ?1 AND undone = 0",
            params![log_id],
            |row| row.get(0),
        )
        .optional()?;

    if let Some(json) = track_ids_json {
        let track_ids: Vec<i64> = serde_json::from_str(&json).unwrap_or_default();
        for tid in track_ids {
            conn.execute(
                "UPDATE tracks SET quarantined = 0 WHERE id = ?1",
                params![tid],
            )?;
        }
        conn.execute(
            "UPDATE curation_log SET undone = 1 WHERE id = ?1",
            params![log_id],
        )?;
    }
    Ok(())
}

/// Scan the library for naming issues and return a preview of proposed fixes.
pub fn preview_library_cleanup(conn: &Connection) -> LyraResult<LibraryCleanupPreview> {
    let mut issues = Vec::new();

    // Missing artist
    let mut stmt = conn.prepare(
        "SELECT t.id, t.title, COALESCE(ar.name, '')
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE trim(COALESCE(ar.name, '')) = '' OR COALESCE(ar.name, '') = 'Unknown Artist'
         LIMIT 100",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;
    for row in rows.filter_map(Result::ok) {
        let (track_id, title, current_value) = row;
        issues.push(CleanupIssue {
            issue_type: "missing_artist".to_string(),
            track_id,
            current_value: current_value.clone(),
            suggested_value: "Tag from filename or enrich".to_string(),
            severity: "high".to_string(),
        });
        let _ = title;
    }

    // Missing album
    let mut stmt = conn.prepare(
        "SELECT t.id, COALESCE(al.title, '')
         FROM tracks t
         LEFT JOIN albums al ON al.id = t.album_id
         WHERE trim(COALESCE(al.title, '')) = '' OR COALESCE(al.title, '') = 'Unknown Album'
         LIMIT 100",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((row.get::<_, i64>(0)?, row.get::<_, String>(1)?))
    })?;
    for row in rows.filter_map(Result::ok) {
        let (track_id, current_value) = row;
        issues.push(CleanupIssue {
            issue_type: "missing_album".to_string(),
            track_id,
            current_value,
            suggested_value: "Tag from folder name or enrich".to_string(),
            severity: "medium".to_string(),
        });
    }

    // Suspected duplicates (same title+artist, multiple entries)
    let mut stmt = conn.prepare(
        "SELECT t.id, t.title, COALESCE(ar.name, '')
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND (LOWER(t.title), LOWER(COALESCE(ar.name, ''))) IN (
             SELECT LOWER(t2.title), LOWER(COALESCE(ar2.name, ''))
             FROM tracks t2
             LEFT JOIN artists ar2 ON ar2.id = t2.artist_id
             WHERE (t2.quarantined IS NULL OR t2.quarantined = 0)
             GROUP BY LOWER(t2.title), LOWER(COALESCE(ar2.name, ''))
             HAVING COUNT(*) > 1
         )
         LIMIT 100",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((
            row.get::<_, i64>(0)?,
            row.get::<_, String>(1)?,
            row.get::<_, String>(2)?,
        ))
    })?;
    for row in rows.filter_map(Result::ok) {
        let (track_id, title, artist) = row;
        issues.push(CleanupIssue {
            issue_type: "suspected_duplicate".to_string(),
            track_id,
            current_value: format!("{artist} - {title}"),
            suggested_value: "Review and resolve in Duplicates panel".to_string(),
            severity: "medium".to_string(),
        });
    }

    Ok(LibraryCleanupPreview { issues })
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

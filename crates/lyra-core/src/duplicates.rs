//! Duplicate detection for the Lyra library.
//!
//! Three strategies (matching the Python original):
//! - **Exact hash**: bit-perfect duplicates via `tracks.content_hash`
//! - **Metadata fuzzy**: same artist+title via string similarity (≥ threshold)
//! - **Path hygiene**: identical `path` stored under multiple track IDs
//!
//! AcoustID fingerprint matching is **[AcoustID Duplicate Detection?]** —
//! deferred, requires `fpcalc` external binary and belongs in the enricher
//! pipeline.  This module reads only from SQLite.

use rusqlite::Connection;

use crate::errors::LyraResult;

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct DupTrack {
    pub id: i64,
    pub path: String,
    pub artist: String,
    pub title: String,
    pub content_hash: Option<String>,
}

#[derive(Debug, Default)]
pub struct DuplicateSummary {
    pub exact_groups: usize,
    pub exact_tracks: usize,
    pub metadata_groups: usize,
    pub metadata_tracks: usize,
    pub path_groups: usize,
    pub path_tracks: usize,
    pub metadata_threshold: f64,
}

// ── String similarity (Ratcliff/Obershelp approximation) ────────────────────

/// Simple bigram-overlap similarity in [0.0, 1.0].
/// Fast enough for O(n²) library scans up to ~5 000 tracks.
fn similarity(a: &str, b: &str) -> f64 {
    if a == b {
        return 1.0;
    }
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }
    let bigrams_a = bigrams(a);
    let bigrams_b = bigrams(b);
    let total = bigrams_a.len() + bigrams_b.len();
    if total == 0 {
        return 0.0;
    }
    let mut b_remaining = bigrams_b.clone();
    let mut hits = 0usize;
    for bg in &bigrams_a {
        if let Some(pos) = b_remaining.iter().position(|x| x == bg) {
            hits += 1;
            b_remaining.remove(pos);
        }
    }
    2.0 * hits as f64 / total as f64
}

fn bigrams(s: &str) -> Vec<[char; 2]> {
    let chars: Vec<char> = s.chars().collect();
    chars.windows(2).map(|w| [w[0], w[1]]).collect()
}

fn normalize(s: &str) -> String {
    s.trim().to_lowercase()
}

// ── Strategies ───────────────────────────────────────────────────────────────

/// Groups of tracks sharing the same `content_hash`.
pub fn find_exact_duplicates(conn: &Connection) -> LyraResult<Vec<Vec<DupTrack>>> {
    let hashes: Vec<String> = conn
        .prepare(
            "SELECT content_hash FROM tracks
             WHERE content_hash IS NOT NULL AND content_hash != ''
             GROUP BY content_hash HAVING COUNT(*) > 1",
        )?
        .query_map([], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();

    let mut groups = Vec::new();
    for hash in &hashes {
        let members: Vec<DupTrack> = conn
            .prepare(
                "SELECT t.id, t.path, COALESCE(ar.name,''), COALESCE(t.title,''), t.content_hash
                 FROM tracks t
                 LEFT JOIN artists ar ON ar.id = t.artist_id
                 WHERE t.content_hash = ?1
                 ORDER BY LENGTH(t.path) ASC",
            )?
            .query_map([hash], |row| {
                Ok(DupTrack {
                    id: row.get(0)?,
                    path: row.get(1)?,
                    artist: row.get(2)?,
                    title: row.get(3)?,
                    content_hash: row.get(4)?,
                })
            })?
            .filter_map(Result::ok)
            .collect();

        if members.len() > 1 {
            groups.push(members);
        }
    }
    Ok(groups)
}

/// Groups of tracks with similar artist + title (combined similarity ≥ threshold).
pub fn find_metadata_duplicates(
    conn: &Connection,
    threshold: f64,
) -> LyraResult<Vec<Vec<DupTrack>>> {
    let tracks: Vec<DupTrack> = conn
        .prepare(
            "SELECT t.id, t.path, COALESCE(ar.name,''), COALESCE(t.title,''), t.content_hash
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE t.title IS NOT NULL AND t.title != ''
             ORDER BY ar.name, t.title",
        )?
        .query_map([], |row| {
            Ok(DupTrack {
                id: row.get(0)?,
                path: row.get(1)?,
                artist: row.get(2)?,
                title: row.get(3)?,
                content_hash: row.get(4)?,
            })
        })?
        .filter_map(Result::ok)
        .collect();

    let mut visited: std::collections::HashSet<i64> = std::collections::HashSet::new();
    let mut groups: Vec<Vec<DupTrack>> = Vec::new();

    for i in 0..tracks.len() {
        if visited.contains(&tracks[i].id) {
            continue;
        }
        let anchor = &tracks[i];
        let anchor_artist = normalize(&anchor.artist);
        let anchor_title = normalize(&anchor.title);

        let mut group = vec![anchor.clone()];
        visited.insert(anchor.id);

        for candidate in tracks.iter().skip(i + 1) {
            if visited.contains(&candidate.id) {
                continue;
            }
            // Quick length pre-filter
            if anchor_artist.len().abs_diff(candidate.artist.len()) > 8 {
                continue;
            }
            let artist_sim = similarity(&anchor_artist, &normalize(&candidate.artist));
            if artist_sim < 0.6 {
                continue;
            }
            let title_sim = similarity(&anchor_title, &normalize(&candidate.title));
            let combined = (artist_sim + title_sim) / 2.0;
            if combined >= threshold {
                group.push(candidate.clone());
                visited.insert(candidate.id);
            }
        }

        if group.len() > 1 {
            groups.push(group);
        }
    }
    Ok(groups)
}

/// Groups of tracks sharing the same file `path`.
pub fn find_path_duplicates(conn: &Connection) -> LyraResult<Vec<Vec<DupTrack>>> {
    let paths: Vec<String> = conn
        .prepare(
            "SELECT path FROM tracks
             WHERE path IS NOT NULL AND path != ''
             GROUP BY path HAVING COUNT(*) > 1",
        )?
        .query_map([], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();

    let mut groups = Vec::new();
    for path in &paths {
        let members: Vec<DupTrack> = conn
            .prepare(
                "SELECT t.id, t.path, COALESCE(ar.name,''), COALESCE(t.title,''), t.content_hash
                 FROM tracks t
                 LEFT JOIN artists ar ON ar.id = t.artist_id
                 WHERE t.path = ?1
                 ORDER BY t.id ASC",
            )?
            .query_map([path], |row| {
                Ok(DupTrack {
                    id: row.get(0)?,
                    path: row.get(1)?,
                    artist: row.get(2)?,
                    title: row.get(3)?,
                    content_hash: row.get(4)?,
                })
            })?
            .filter_map(Result::ok)
            .collect();

        if members.len() > 1 {
            groups.push(members);
        }
    }
    Ok(groups)
}

/// Run all three strategies and return a summary.
pub fn get_duplicate_summary(
    conn: &Connection,
    metadata_threshold: f64,
) -> LyraResult<DuplicateSummary> {
    let exact = find_exact_duplicates(conn)?;
    let metadata = find_metadata_duplicates(conn, metadata_threshold)?;
    let path = find_path_duplicates(conn)?;

    Ok(DuplicateSummary {
        exact_groups: exact.len(),
        exact_tracks: exact.iter().map(|g| g.len()).sum(),
        metadata_groups: metadata.len(),
        metadata_tracks: metadata.iter().map(|g| g.len()).sum(),
        path_groups: path.len(),
        path_tracks: path.iter().map(|g| g.len()).sum(),
        metadata_threshold,
    })
}

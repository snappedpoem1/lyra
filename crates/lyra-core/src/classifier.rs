//! Track version-type classifier.
//!
//! Detects junk, remix, live, cover, and special versions via token matching
//! against title + album + filename.  Priority: junk > cover > live > remix >
//! special > original.
//!
//! A **[LLM Second-Pass Classifier?]** for low-confidence originals is
//! acknowledged but deferred — requires `LlmClient::classify()` structured
//! output, not yet implemented.

use std::path::Path;

use rusqlite::{params, Connection, OptionalExtension};
use serde::Serialize;

use crate::errors::LyraResult;

// ── Token lists ──────────────────────────────────────────────────────────────

static JUNK_TOKENS: &[&str] = &[
    "vevo",
    "official video",
    "official audio",
    "official music video",
    "lyrics",
    "lyric video",
    "hd",
    "4k",
    "8k",
    "visualizer",
    "official visualizer",
    "audio",
    "free download",
    "full album",
    "full ep",
    "full mixtape",
    "playlist",
    "compilation",
];

static REMIX_TOKENS: &[&str] = &[
    "remix", "edit", "rework", "bootleg", "vip", "flip", "refix", "version", "mix", "mashup",
    "blend",
];

static LIVE_TOKENS: &[&str] = &[
    "live",
    "concert",
    "acoustic",
    "unplugged",
    "session",
    "live at",
    "live from",
    "live session",
    "live performance",
    "bbc live",
    "kexp",
    "tiny desk",
];

static COVER_TOKENS: &[&str] = &[
    "cover",
    "rendition",
    "tribute",
    "originally by",
    "cover version",
    "interpretation",
];

static SPECIAL_TOKENS: &[&str] = &[
    "sped up",
    "speed up",
    "slowed",
    "slowed down",
    "reverb",
    "nightcore",
    "8d audio",
    "8d",
    "bass boosted",
    "boosted",
    "extended",
    "extended mix",
    "radio edit",
    "clean",
    "explicit",
    "instrumental",
    "acapella",
    "a cappella",
];

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum VersionType {
    Original,
    Remix,
    Live,
    Cover,
    Junk,
    Special,
    Unknown,
}

impl VersionType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Original => "original",
            Self::Remix => "remix",
            Self::Live => "live",
            Self::Cover => "cover",
            Self::Junk => "junk",
            Self::Special => "special",
            Self::Unknown => "unknown",
        }
    }
}

impl std::fmt::Display for VersionType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct ClassifyResult {
    pub version_type: VersionType,
    pub confidence: f64,
    pub tokens_found: Vec<String>,
    pub reason: String,
}

// ── Core logic ───────────────────────────────────────────────────────────────

/// Detect which tokens from `list` appear as whole words in `text`.
fn detect_tokens(text: &str, list: &[&str]) -> Vec<String> {
    let lower = text.to_lowercase();
    list.iter()
        .filter(|&&token| {
            let t = token.to_lowercase();
            // word-boundary: must be preceded and followed by non-alphanumeric
            // or be at start/end of string
            if let Some(pos) = lower.find(t.as_str()) {
                let before_ok = pos == 0 || !lower.as_bytes()[pos - 1].is_ascii_alphanumeric();
                let end = pos + t.len();
                let after_ok = end >= lower.len() || !lower.as_bytes()[end].is_ascii_alphanumeric();
                before_ok && after_ok
            } else {
                false
            }
        })
        .map(|t| t.to_string())
        .collect()
}

/// Classify a track from raw strings (no DB access).
pub fn classify_text(title: &str, album: &str, file_path: &str) -> ClassifyResult {
    let filename = Path::new(file_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("");

    let search = format!("{} {} {}", title, album, filename);

    // Priority: junk > cover > live > remix > special > original
    macro_rules! check {
        ($tokens:expr, $vtype:expr, $base_conf:expr) => {{
            let found = detect_tokens(&search, $tokens);
            if !found.is_empty() {
                let conf = ($base_conf + found.len() as f64 * 0.1_f64).min(1.0);
                let reason = format!("Detected tokens: {}", found.join(", "));
                return ClassifyResult {
                    version_type: $vtype,
                    confidence: conf,
                    tokens_found: found,
                    reason,
                };
            }
        }};
    }

    check!(JUNK_TOKENS, VersionType::Junk, 0.7);
    check!(COVER_TOKENS, VersionType::Cover, 0.8);
    check!(LIVE_TOKENS, VersionType::Live, 0.7);
    check!(REMIX_TOKENS, VersionType::Remix, 0.7);
    check!(SPECIAL_TOKENS, VersionType::Special, 0.6);

    ClassifyResult {
        version_type: VersionType::Original,
        confidence: 0.5,
        tokens_found: vec![],
        reason: "No special tokens detected, assuming original".into(),
    }
}

/// Classify a track by ID and persist `version_type` + `confidence` to DB.
pub fn classify_and_update(conn: &Connection, track_id: i64) -> LyraResult<ClassifyResult> {
    let row: Option<(String, String, String, String)> = conn
        .query_row(
            "SELECT COALESCE(t.title,''), COALESCE(al.title,''), t.path,
                    COALESCE(ar.name,'')
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             LEFT JOIN albums  al ON al.id = t.album_id
             WHERE t.id = ?1",
            params![track_id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?;

    let result = match row {
        None => ClassifyResult {
            version_type: VersionType::Unknown,
            confidence: 0.0,
            tokens_found: vec![],
            reason: "track not found".into(),
        },
        Some((title, album, path, _artist)) => classify_text(&title, &album, &path),
    };

    conn.execute(
        "UPDATE tracks SET version_type = ?2, confidence = ?3 WHERE id = ?1",
        params![track_id, result.version_type.as_str(), result.confidence],
    )?;

    Ok(result)
}

/// Classify every track in the library and return counts per version type.
pub fn classify_library(conn: &Connection, limit: usize) -> LyraResult<LibrarySummary> {
    let sql = if limit > 0 {
        format!("SELECT id FROM tracks LIMIT {}", limit)
    } else {
        "SELECT id FROM tracks".into()
    };

    let mut stmt = conn.prepare(&sql)?;
    let ids: Vec<i64> = stmt
        .query_map([], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();

    let mut summary = LibrarySummary {
        total: ids.len(),
        ..Default::default()
    };

    for id in ids {
        let r = classify_and_update(conn, id)?;
        match r.version_type {
            VersionType::Original => summary.original += 1,
            VersionType::Remix => summary.remix += 1,
            VersionType::Live => summary.live += 1,
            VersionType::Cover => summary.cover += 1,
            VersionType::Junk => summary.junk += 1,
            VersionType::Special => summary.special += 1,
            VersionType::Unknown => summary.unknown += 1,
        }
    }

    Ok(summary)
}

#[derive(Debug, Default, Serialize)]
pub struct LibrarySummary {
    pub total: usize,
    pub original: usize,
    pub remix: usize,
    pub live: usize,
    pub cover: usize,
    pub junk: usize,
    pub special: usize,
    pub unknown: usize,
}

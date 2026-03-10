//! Post-download track validation — deterministic text-cleaning and junk
//! guard that runs before a file enters the library.
//!
//! Network lookup orchestration (MusicBrainz, Discogs, iTunes) is
//! **[Network Metadata Validation?]** — deferred, handled by the existing
//! enrichment adapter pipeline.
//!
//! AcoustID fingerprint pass is **[AcoustID Fingerprint Validator?]** —
//! deferred, requires `fpcalc` external binary.
//!
//! Mass library re-validation (`validate_and_fix_library`) is
//! **[Mass Validation Pipeline?]** — deferred, no Tauri caller yet.

use serde::{Deserialize, Serialize};
use rusqlite::{params, Connection};

use crate::errors::LyraResult;

// ── Junk patterns (combined artist+title) ────────────────────────────────────

/// Checked against combined artist+title.
static JUNK_PATTERNS: &[&str] = &[
    r"karaoke", r"tribute", r"8-bit", r"8 bit",
    r"remade", r"midi", r"ringtone", r"party tyme", r"prosource",
    r"zzang", r"piano version",
];

/// Checked against title only — words that are band/album names when in artist field.
static TITLE_JUNK_PATTERNS: &[&str] = &[
    r"lullaby", r"music box", r"instrumental version",
];

/// Record labels that are sometimes stored in the artist field.
static RECORD_LABELS: &[&str] = &[
    "epitaph records", "vagrant records", "rise records", "fueled by ramen",
    "hopeless records", "victory records", "fearless records", "dine alone records",
    "equal vision", "tooth & nail", "solid state", "roadrunner records",
    "interscope", "atlantic records", "columbia records", "riserecords",
    "lyrical lemonade", "worldstarhiphop", "colors show", "genius",
];

// ── Types ────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ValidationSource {
    Clean,          // passed text cleaning + junk guard, no network lookup
    MusicBrainz,
    Discogs,
    ITunes,
    PartialMatch,
    AcoustID,
}

impl ValidationSource {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Clean        => "clean",
            Self::MusicBrainz  => "musicbrainz",
            Self::Discogs      => "discogs",
            Self::ITunes       => "itunes",
            Self::PartialMatch => "partial_match",
            Self::AcoustID     => "acoustid",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ValidationResult {
    pub valid:             bool,
    pub confidence:        f64,
    pub canonical_artist:  Option<String>,
    pub canonical_title:   Option<String>,
    pub canonical_album:   Option<String>,
    pub year:              Option<i32>,
    pub genres:            Vec<String>,
    pub isrc:              Option<String>,
    pub rejection_reason:  Option<String>,
    pub source:            ValidationSource,
}

impl ValidationResult {
    fn rejected(reason: impl Into<String>) -> Self {
        Self {
            valid: false,
            confidence: 0.0,
            canonical_artist: None,
            canonical_title: None,
            canonical_album: None,
            year: None,
            genres: vec![],
            isrc: None,
            rejection_reason: Some(reason.into()),
            source: ValidationSource::Clean,
        }
    }

    fn clean(artist: &str, title: &str) -> Self {
        Self {
            valid: true,
            confidence: 0.5,
            canonical_artist: Some(artist.to_string()),
            canonical_title: Some(title.to_string()),
            canonical_album: None,
            year: None,
            genres: vec![],
            isrc: None,
            rejection_reason: None,
            source: ValidationSource::Clean,
        }
    }
}

// ── Text cleaning ─────────────────────────────────────────────────────────────

/// Strip YouTube/video cruft from a track title.
pub fn clean_title(title: &str) -> String {
    if title.is_empty() {
        return String::new();
    }
    // Suffix patterns to strip (case-insensitive keyword scan)
    static STRIP_PARENS: &[&str] = &[
        "official video", "official audio", "official music video",
        "lyric video", "official visualizer", "visualizer",
        "explicit", "hd", "lyrics", "lyric", "audio",
    ];
    static STRIP_DASH_SUFFIX: &[&str] = &[
        "official", "video", "audio", "lyric", "hd", "4k",
    ];

    let mut result = title.to_string();

    // Strip " | Channel Name" suffix
    if let Some(pos) = result.find(" | ") {
        result.truncate(pos);
    }

    // Strip trailing [anything]
    if result.ends_with(']') {
        if let Some(pos) = result.rfind('[') {
            result.truncate(pos);
        }
    }

    // Strip known paren phrases: (Official Video) etc.
    for kw in STRIP_PARENS {
        let lower = result.to_lowercase();
        for delim in [('(', ')'), ('[', ']')] {
            let search = format!("{}{}{}", delim.0, kw, delim.1);
            if let Some(pos) = lower.find(&search) {
                // Strip from space before the paren
                let start = if pos > 0 && result.as_bytes()[pos - 1] == b' ' {
                    pos - 1
                } else {
                    pos
                };
                result = format!("{}{}", &result[..start], &result[pos + search.len()..]);
                break;
            }
        }
    }

    // Strip " - Official..." dash suffix
    let lower = result.to_lowercase();
    if let Some(pos) = lower.rfind(" - ") {
        let after = &lower[pos + 3..];
        if STRIP_DASH_SUFFIX.iter().any(|kw| after.starts_with(kw)) {
            result.truncate(pos);
        }
    }

    result.trim().to_string()
}

/// Strip YouTube channel suffixes from an artist name.
pub fn clean_artist(artist: &str) -> String {
    if artist.is_empty() {
        return String::new();
    }
    let lower = artist.to_lowercase();
    let result = if lower.ends_with("vevo") {
        artist[..artist.len() - 4].trim_end().to_string()
    } else {
        artist.to_string()
    };
    // Remove " - Topic" suffix
    let result = if result.to_lowercase().ends_with(" - topic") {
        result[..result.len() - 8].trim_end().to_string()
    } else {
        result
    };
    result.replace("  ", " ").trim().to_string()
}

/// If artist is empty or a known record label, try to split "Artist - Title".
pub fn extract_artist_from_title(title: &str) -> (Option<String>, String) {
    if let Some((a, t)) = title.split_once(" - ") {
        (Some(a.trim().to_string()), t.trim().to_string())
    } else {
        (None, title.to_string())
    }
}

/// Return `Some(reason)` if the track is junk, `None` if it's clean.
fn word_match(haystack: &str, needle: &str) -> bool {
    if let Some(pos) = haystack.find(needle) {
        let before_ok = pos == 0 || !haystack.as_bytes()[pos - 1].is_ascii_alphanumeric();
        let end = pos + needle.len();
        let after_ok = end >= haystack.len() || !haystack.as_bytes()[end].is_ascii_alphanumeric();
        before_ok && after_ok
    } else {
        false
    }
}

pub fn is_junk_text(artist: &str, title: &str) -> Option<String> {
    let combined = format!("{} {}", artist, title).to_lowercase();
    for pat in JUNK_PATTERNS {
        if word_match(&combined, pat) {
            return Some(format!("matches junk pattern: {}", pat));
        }
    }
    // Title-only patterns (avoid flagging band names like "A Static Lullaby")
    let title_lower = title.to_lowercase();
    for pat in TITLE_JUNK_PATTERNS {
        if word_match(&title_lower, pat) {
            return Some(format!("matches title junk pattern: {}", pat));
        }
    }
    let artist_lower = artist.trim().to_lowercase();
    if RECORD_LABELS.contains(&artist_lower.as_str()) {
        return Some(format!("artist is a record label: {}", artist));
    }
    None
}

// ── Deterministic validate_track ─────────────────────────────────────────────

/// Validate a track from raw metadata strings.
///
/// This is the deterministic pass: clean inputs, check for junk, return a
/// `ValidationResult`. Network lookup (MusicBrainz / Discogs / iTunes) is
/// **[Network Metadata Validation?]** and not performed here.
pub fn validate_track_text(artist: &str, title: &str) -> ValidationResult {
    let mut artist = clean_artist(artist);
    let mut title  = clean_title(title);

    // If artist is missing or is a label, try extracting from "Artist - Title"
    if artist.is_empty() || RECORD_LABELS.contains(&artist.to_lowercase().as_str()) {
        if let (Some(extracted_artist), extracted_title) = extract_artist_from_title(&title) {
            artist = clean_artist(&extracted_artist);
            title  = clean_title(&extracted_title);
        }
    }

    if let Some(reason) = is_junk_text(&artist, &title) {
        return ValidationResult::rejected(reason);
    }

    ValidationResult::clean(&artist, &title)
}

// ── DB writeback ─────────────────────────────────────────────────────────────

/// Ensure the `track_validation` table exists (idempotent).
pub fn ensure_validation_table(conn: &Connection) -> LyraResult<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS track_validation (
            track_id   INTEGER PRIMARY KEY,
            status     TEXT NOT NULL,
            confidence REAL,
            source     TEXT,
            validated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tv_status ON track_validation(status);",
    )?;
    Ok(())
}

/// Record a validation result for a track.
pub fn mark_validated(
    conn: &Connection,
    track_id: i64,
    result: &ValidationResult,
) -> LyraResult<()> {
    let status = if result.valid { "valid" } else { "rejected" };
    let now = chrono::Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO track_validation (track_id, status, confidence, source, validated_at)
         VALUES (?1, ?2, ?3, ?4, ?5)
         ON CONFLICT(track_id) DO UPDATE SET
             status=excluded.status,
             confidence=excluded.confidence,
             source=excluded.source,
             validated_at=excluded.validated_at",
        params![
            track_id,
            status,
            result.confidence,
            result.source.as_str(),
            now
        ],
    )?;
    Ok(())
}

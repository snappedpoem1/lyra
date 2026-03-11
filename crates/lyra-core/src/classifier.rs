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
    "remix", "edit", "rework", "reworked", "bootleg", "vip", "flip", "refix", "mashup", "blend",
];

static LIVE_TOKENS: &[&str] = &[
    "concert",
    "unplugged",
    "soundcheck",
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
    "radio edit",
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
    detect_tokens_in_lower(&lower, list)
}

fn detect_tokens_in_lower(lower: &str, list: &[&str]) -> Vec<String> {
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

fn detect_contextual_tokens(lower: &str, rules: &[(&str, &[&str])]) -> Vec<String> {
    let mut found = Vec::new();
    for (label, phrases) in rules {
        if phrases.iter().any(|phrase| lower.contains(phrase))
            && !found.iter().any(|existing| existing == label)
        {
            found.push((*label).to_string());
        }
    }
    found
}

fn merge_tokens(mut primary: Vec<String>, secondary: Vec<String>) -> Vec<String> {
    for token in secondary {
        if !primary.iter().any(|existing| existing == &token) {
            primary.push(token);
        }
    }
    primary
}

fn classification_from_tokens(
    version_type: VersionType,
    base_confidence: f64,
    found: Vec<String>,
) -> Option<ClassifyResult> {
    if found.is_empty() {
        return None;
    }
    let confidence = (base_confidence + found.len() as f64 * 0.1_f64).min(1.0);
    let reason = format!("Detected tokens: {}", found.join(", "));
    Some(ClassifyResult {
        version_type,
        confidence,
        tokens_found: found,
        reason,
    })
}

/// Classify a track from raw strings (no DB access).
pub fn classify_text(title: &str, album: &str, file_path: &str) -> ClassifyResult {
    let filename = Path::new(file_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("");

    let search = format!("{} {} {}", title, album, filename);
    let lower = search.to_ascii_lowercase();
    let live_contextual_tokens = merge_tokens(
        detect_tokens_in_lower(&lower, LIVE_TOKENS),
        detect_contextual_tokens(
            &lower,
            &[
                (
                    "live",
                    &[
                        "(live)",
                        "[live]",
                        "(live,",
                        "[live,",
                        "(live ",
                        "[live ",
                        " live,",
                        " live at ",
                        " live from ",
                        " live in ",
                        " live on ",
                        " live session",
                        " live performance",
                    ],
                ),
                (
                    "acoustic",
                    &[
                        "(acoustic)",
                        "[acoustic]",
                        " acoustic version",
                        ", acoustic",
                    ],
                ),
            ],
        ),
    );
    let remix_contextual_tokens = merge_tokens(
        detect_tokens_in_lower(&lower, REMIX_TOKENS),
        detect_contextual_tokens(
            &lower,
            &[
                (
                    "mix",
                    &[
                        "(mix)",
                        "[mix]",
                        "(extended mix)",
                        "[extended mix]",
                        " extended mix",
                        " radio mix",
                        " club mix",
                        " dub mix",
                        " mix version",
                    ],
                ),
                (
                    "version",
                    &[
                        " demo version",
                        " karaoke version",
                        " acoustic version",
                        " instrumental version",
                        " clean version",
                        " explicit version",
                    ],
                ),
            ],
        ),
    );
    let special_contextual_tokens = merge_tokens(
        detect_tokens_in_lower(&lower, SPECIAL_TOKENS),
        detect_contextual_tokens(
            &lower,
            &[
                ("demo", &["(demo)", "[demo]", " demo version"]),
                (
                    "lofi",
                    &[
                        "(lofi)",
                        "[lofi]",
                        "(lo-fi)",
                        "[lo-fi]",
                        " lofi version",
                        " lo-fi version",
                        " lofi remix",
                        " lo-fi remix",
                    ],
                ),
                (
                    "instrumental",
                    &[
                        "(instrumental)",
                        "[instrumental]",
                        " instrumental version",
                        " instrumental mix",
                        " instrumental edit",
                    ],
                ),
                ("clean", &["(clean)", "[clean]", " clean version"]),
                (
                    "explicit",
                    &["(explicit)", "[explicit]", " explicit version"],
                ),
            ],
        ),
    );

    // Priority: junk > cover > live > remix > special > original
    macro_rules! check_found {
        ($found:expr, $vtype:expr, $base_conf:expr) => {{
            if let Some(result) = classification_from_tokens($vtype, $base_conf, $found) {
                return result;
            }
        }};
    }

    check_found!(detect_tokens(&search, JUNK_TOKENS), VersionType::Junk, 0.7);
    check_found!(
        detect_tokens(&search, COVER_TOKENS),
        VersionType::Cover,
        0.8
    );
    check_found!(live_contextual_tokens, VersionType::Live, 0.7);
    check_found!(remix_contextual_tokens, VersionType::Remix, 0.7);
    check_found!(special_contextual_tokens, VersionType::Special, 0.6);

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

#[cfg(test)]
mod tests {
    use super::{classify_text, VersionType};

    #[test]
    fn classify_text_keeps_legitimate_mix_title_original() {
        let result = classify_text("Mix Tape", "Your Favorite Weapon", "");
        assert_eq!(result.version_type, VersionType::Original);
    }

    #[test]
    fn classify_text_keeps_legitimate_live_title_original() {
        let result = classify_text("When Skeletons Live", "Year of the Black Rainbow", "");
        assert_eq!(result.version_type, VersionType::Original);
    }

    #[test]
    fn classify_text_flags_contextual_live_and_mix_variants() {
        let live = classify_text("Bought a Bride (Live in Studio)", "Daisy", "");
        assert_eq!(live.version_type, VersionType::Live);

        let remix = classify_text("Song Title (Extended Mix)", "Singles", "");
        assert_eq!(remix.version_type, VersionType::Remix);
    }
}

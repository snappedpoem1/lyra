use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::classifier::{self, VersionType};
use crate::errors::LyraResult;

const REJECT_TOKENS: &[&str] = &[
    "karaoke",
    "tribute",
    "made famous by",
    "made popular by",
    "in the style of",
    "cover version",
    "lo-fi",
    "lofi",
    "lo-fi remix",
    "lofi remix",
    "nightcore",
    "slowed",
    "sped up",
];

const STRIP_SUFFIXES: &[&str] = &[
    " - remastered",
    " - remaster",
    " - deluxe edition",
    " - deluxe",
    " - anniversary edition",
    " - mono remaster",
];

const STRIP_PAREN_PHRASES: &[&str] = &[
    "remastered",
    "deluxe edition",
    "deluxe",
    "anniversary edition",
    "mono remaster",
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CanonicalArtist {
    pub name: String,
    pub normalized_name: String,
    pub mbid: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CanonicalAlbum {
    pub title: String,
    pub normalized_title: String,
    pub release_date: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CanonicalTrack {
    pub provider: String,
    pub provider_track_id: String,
    pub artist: CanonicalArtist,
    pub title: String,
    pub normalized_title: String,
    pub album: Option<CanonicalAlbum>,
    pub isrc: Option<String>,
    pub duration_ms: Option<i64>,
    pub popularity: Option<i64>,
    pub explicit: bool,
    pub version_type: String,
}

#[derive(Clone, Debug)]
pub struct RawTrackCandidate<'a> {
    pub provider: &'a str,
    pub provider_track_id: &'a str,
    pub artist: &'a str,
    pub title: &'a str,
    pub album: Option<&'a str>,
    pub release_date: Option<&'a str>,
    pub isrc: Option<&'a str>,
    pub duration_ms: Option<i64>,
    pub popularity: Option<i64>,
    pub explicit: bool,
}

pub fn normalize_track_candidate(raw: RawTrackCandidate<'_>) -> Result<CanonicalTrack, String> {
    let provider = raw.provider.trim().to_string();
    if provider.is_empty() {
        return Err("provider is required".to_string());
    }

    let artist_name = canonical_display_name(raw.artist);
    let artist_normalized = normalize_catalog_text(raw.artist);
    if artist_name.is_empty() || artist_normalized.is_empty() {
        return Err("artist is required".to_string());
    }

    let title = canonical_display_title(raw.title);
    let normalized_title = normalize_catalog_text(raw.title);
    if title.is_empty() || normalized_title.is_empty() {
        return Err("title is required".to_string());
    }

    let version = classifier::classify_text(&title, raw.album.unwrap_or_default(), "");
    let version_type = version.version_type.as_str().to_string();
    if should_reject_variant(&version.version_type, &title, raw.album) {
        return Err(format!(
            "rejected non-canonical release variant: {}",
            version.reason
        ));
    }

    let album = raw
        .album
        .map(canonical_display_title)
        .filter(|value| !value.is_empty())
        .map(|title| CanonicalAlbum {
            normalized_title: normalize_catalog_text(&title),
            title,
            release_date: sanitize_release_date(raw.release_date),
        });

    let provider_track_id = if raw.provider_track_id.trim().is_empty() {
        provider_track_key(&provider, raw.artist, raw.title, raw.isrc)
    } else {
        raw.provider_track_id.trim().to_string()
    };

    let isrc = sanitize_isrc(raw.isrc);
    let popularity = sanitize_popularity(raw.popularity);
    let duration_ms = raw.duration_ms.filter(|value| *value >= 0);

    Ok(CanonicalTrack {
        provider,
        provider_track_id,
        artist: CanonicalArtist {
            name: artist_name,
            normalized_name: artist_normalized,
            mbid: None,
        },
        title,
        normalized_title,
        album,
        isrc,
        duration_ms,
        popularity,
        explicit: raw.explicit,
        version_type,
    })
}

pub fn provider_track_key(provider: &str, artist: &str, title: &str, isrc: Option<&str>) -> String {
    if let Some(cleaned_isrc) = sanitize_isrc(isrc) {
        return cleaned_isrc;
    }
    format!(
        "{}::{}::{}",
        provider.trim().to_ascii_lowercase(),
        normalize_catalog_text(artist),
        normalize_catalog_text(title)
    )
}

pub fn payload_track_id(provider: &str, payload: &Value, artist: &str, title: &str) -> String {
    match provider {
        "musicbrainz" => payload
            .get("recordingMbid")
            .or_else(|| payload.get("mbid"))
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| provider_track_key(provider, artist, title, None)),
        "spotify" => payload
            .get("spotifyUri")
            .or_else(|| payload.get("spotify_uri"))
            .and_then(Value::as_str)
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| {
                provider_track_key(
                    provider,
                    artist,
                    title,
                    payload.get("isrc").and_then(Value::as_str),
                )
            }),
        _ => provider_track_key(
            provider,
            artist,
            title,
            payload
                .get("isrc")
                .or_else(|| payload.get("ISRC"))
                .and_then(Value::as_str),
        ),
    }
}

pub fn persist_provider_track(
    conn: &Connection,
    track: &CanonicalTrack,
    source_kind: &str,
    payload: &Value,
) -> LyraResult<()> {
    let canonical_payload = json!({
        "track": track,
        "raw": payload,
    });
    let album_title = track.album.as_ref().map(|album| album.title.as_str());
    let album_normalized = track
        .album
        .as_ref()
        .map(|album| album.normalized_title.as_str());
    conn.execute(
        "INSERT INTO provider_catalog_tracks
         (provider, provider_track_id, artist_name, artist_normalized, title, title_normalized,
          album_title, album_normalized, isrc, duration_ms, popularity, explicit, version_type,
          source_kind, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)
         ON CONFLICT(provider, provider_track_id) DO UPDATE SET
           artist_name = excluded.artist_name,
           artist_normalized = excluded.artist_normalized,
           title = excluded.title,
           title_normalized = excluded.title_normalized,
           album_title = excluded.album_title,
           album_normalized = excluded.album_normalized,
           isrc = excluded.isrc,
           duration_ms = excluded.duration_ms,
           popularity = excluded.popularity,
           explicit = excluded.explicit,
           version_type = excluded.version_type,
           source_kind = excluded.source_kind,
           payload_json = excluded.payload_json,
           fetched_at = excluded.fetched_at",
        params![
            track.provider,
            track.provider_track_id,
            track.artist.name,
            track.artist.normalized_name,
            track.title,
            track.normalized_title,
            album_title,
            album_normalized,
            track.isrc,
            track.duration_ms,
            track.popularity,
            i64::from(track.explicit),
            track.version_type,
            sanitize_source_kind(source_kind),
            serde_json::to_string(&canonical_payload)?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

pub fn persist_normalized_payload_track(
    conn: &Connection,
    source_kind: &str,
    raw: RawTrackCandidate<'_>,
    payload: &Value,
) -> LyraResult<bool> {
    let normalized = match normalize_track_candidate(raw) {
        Ok(track) => track,
        Err(_) => return Ok(false),
    };
    persist_provider_track(conn, &normalized, source_kind, payload)?;
    Ok(true)
}

fn is_official_variant_album(album: Option<&str>) -> bool {
    let album_lower = album.unwrap_or("").to_ascii_lowercase();
    !album_lower.is_empty()
        && (album_lower.contains("live at")
            || album_lower.contains("live from")
            || album_lower.contains("live in")
            || album_lower.starts_with("live ")
            || album_lower.ends_with(" live")
            || album_lower.contains("live edition")
            || album_lower.contains("demos, reworked")
            || album_lower.contains("demos reworked")
            || album_lower.contains("deluxe")
            || album_lower.contains("special edition")
            || album_lower.contains("expanded edition")
            || album_lower.contains("remastered")
            || album_lower.contains("unplugged")
            || album_lower.contains("mtv unplugged")
            || album_lower.contains("haarp"))
}

fn should_reject_variant(version_type: &VersionType, title: &str, album: Option<&str>) -> bool {
    // Always reject junk and cover variants
    if matches!(version_type, VersionType::Junk | VersionType::Cover) {
        return true;
    }

    // For Remix, Live, and Special variants, allow if the album context
    // indicates an official variant release (official live album, demo EP,
    // deluxe/special edition).  The classifier combines title+album text, so
    // tokens like "reworked" in album "3 Demos, Reworked" can trigger Remix
    // even though the track itself is an original.
    if matches!(
        version_type,
        VersionType::Remix | VersionType::Live | VersionType::Special
    ) {
        if is_official_variant_album(album) {
            // Double-check: if the variant token is ONLY in the album title
            // and not in the track title, this is album context pollution.
            // Even if the token IS in the track title (e.g. "(Demo)" on a
            // demo EP), the official album context means the user wants it.
            return false;
        }
        return true;
    }

    let combined = format!("{} {}", title, album.unwrap_or_default()).to_ascii_lowercase();
    REJECT_TOKENS.iter().any(|token| combined.contains(token))
}

fn sanitize_source_kind(source_kind: &str) -> String {
    match source_kind.trim().to_ascii_lowercase().as_str() {
        "library" | "history" | "recommendation" | "enrichment" | "acquisition" => {
            source_kind.trim().to_ascii_lowercase()
        }
        _ => "enrichment".to_string(),
    }
}

fn sanitize_release_date(value: Option<&str>) -> Option<String> {
    let trimmed = value.map(str::trim).filter(|value| !value.is_empty())?;
    let valid = match trimmed.len() {
        4 => trimmed.chars().all(|ch| ch.is_ascii_digit()),
        7 => trimmed.chars().enumerate().all(|(idx, ch)| match idx {
            4 => ch == '-',
            _ => ch.is_ascii_digit(),
        }),
        10 => trimmed.chars().enumerate().all(|(idx, ch)| match idx {
            4 | 7 => ch == '-',
            _ => ch.is_ascii_digit(),
        }),
        _ => false,
    };
    valid.then(|| trimmed.to_string())
}

fn sanitize_popularity(value: Option<i64>) -> Option<i64> {
    value.map(|raw| raw.clamp(0, 100))
}

fn sanitize_isrc(value: Option<&str>) -> Option<String> {
    let cleaned = value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| {
            value
                .chars()
                .filter(|ch| ch.is_ascii_alphanumeric())
                .collect::<String>()
                .to_ascii_uppercase()
        })?;
    (cleaned.len() == 12).then_some(cleaned)
}

fn canonical_display_name(value: &str) -> String {
    value
        .split(',')
        .next()
        .unwrap_or(value)
        .split(" feat.")
        .next()
        .unwrap_or(value)
        .split(" ft.")
        .next()
        .unwrap_or(value)
        .trim()
        .to_string()
}

fn canonical_display_title(value: &str) -> String {
    let mut cleaned = value.trim().replace("  ", " ");
    for suffix in STRIP_SUFFIXES {
        if cleaned
            .to_ascii_lowercase()
            .ends_with(&suffix.to_ascii_lowercase())
        {
            let keep = cleaned.len().saturating_sub(suffix.len());
            cleaned.truncate(keep);
            cleaned = cleaned.trim().to_string();
        }
    }
    for phrase in STRIP_PAREN_PHRASES {
        cleaned = strip_parenthetical_phrase(&cleaned, phrase);
    }
    cleaned.trim().to_string()
}

fn strip_parenthetical_phrase(value: &str, phrase: &str) -> String {
    let lower = value.to_ascii_lowercase();
    let paren = format!("({phrase})");
    let bracket = format!("[{phrase}]");
    if let Some(index) = lower.find(&paren) {
        return format!(
            "{}{}",
            &value[..index].trim_end(),
            &value[index + paren.len()..]
        )
        .trim()
        .to_string();
    }
    if let Some(index) = lower.find(&bracket) {
        return format!(
            "{}{}",
            &value[..index].trim_end(),
            &value[index + bracket.len()..]
        )
        .trim()
        .to_string();
    }
    value.to_string()
}

fn normalize_catalog_text(value: &str) -> String {
    canonical_display_title(&canonical_display_name(value))
        .to_ascii_lowercase()
        .chars()
        .filter_map(|ch| {
            if ch.is_ascii_alphanumeric() || ch.is_ascii_whitespace() {
                Some(ch)
            } else if matches!(ch, '-' | '_' | '/' | '&') {
                Some(' ')
            } else {
                None
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;
    use serde_json::json;

    use super::{normalize_track_candidate, persist_provider_track, RawTrackCandidate};
    use crate::db;

    #[test]
    fn rejects_non_canonical_cover_variants() {
        let result = normalize_track_candidate(RawTrackCandidate {
            provider: "spotify",
            provider_track_id: "spotify:track:123",
            artist: "Piano Tribute Players",
            title: "The Quiet Things That No One Ever Knows (Karaoke Version)",
            album: Some("In the Style Of"),
            release_date: Some("2024-01-01"),
            isrc: None,
            duration_ms: Some(180_000),
            popularity: Some(12),
            explicit: false,
        });
        assert!(result.is_err());
    }

    #[test]
    fn rejects_non_canonical_sped_up_variants() {
        let result = normalize_track_candidate(RawTrackCandidate {
            provider: "spotify",
            provider_track_id: "spotify:track:999",
            artist: "EDM Reworks",
            title: "Midnight Rush (Nightcore Sped Up Version)",
            album: Some("Festival Edits"),
            release_date: Some("2025-07-11"),
            isrc: None,
            duration_ms: Some(190_000),
            popularity: Some(44),
            explicit: false,
        });
        assert!(result.is_err());
    }

    #[test]
    fn rejects_non_canonical_lofi_variants() {
        let result = normalize_track_candidate(RawTrackCandidate {
            provider: "spotify",
            provider_track_id: "spotify:track:444",
            artist: "Chill Covers Collective",
            title: "The Quiet Things That No One Ever Knows (Lofi Version)",
            album: Some("Late Night Reworks"),
            release_date: Some("2025-06-21"),
            isrc: None,
            duration_ms: Some(201_000),
            popularity: Some(18),
            explicit: false,
        });
        assert!(result.is_err());
    }

    #[test]
    fn strips_remaster_suffixes_from_canonical_title() {
        let result = normalize_track_candidate(RawTrackCandidate {
            provider: "spotify",
            provider_track_id: "spotify:track:123",
            artist: "Brand New",
            title: "Sic Transit Gloria... Glory Fades - Remastered",
            album: Some("Deja Entendu (Deluxe Edition)"),
            release_date: Some("2003-06-17"),
            isrc: Some("USUM71705395"),
            duration_ms: Some(206_000),
            popularity: Some(72),
            explicit: false,
        })
        .expect("normalized");

        assert_eq!(result.title, "Sic Transit Gloria... Glory Fades");
        assert_eq!(result.normalized_title, "sic transit gloria glory fades");
        assert_eq!(
            result.album.expect("album").normalized_title,
            "deja entendu"
        );
    }

    #[test]
    fn persists_strict_provider_track_rows() {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");

        let track = normalize_track_candidate(RawTrackCandidate {
            provider: "listenbrainz/weather",
            provider_track_id: "weather::artist::title",
            artist: "Midnight Circuit",
            title: "Glass Weather",
            album: Some("Signal Bloom"),
            release_date: Some("2025-02-14"),
            isrc: Some("USABC2401234"),
            duration_ms: Some(214_000),
            popularity: Some(81),
            explicit: false,
        })
        .expect("normalized");

        persist_provider_track(&conn, &track, "recommendation", &json!({"status": "ok"}))
            .expect("persist");

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM provider_catalog_tracks", [], |row| {
                row.get(0)
            })
            .expect("count");
        assert_eq!(count, 1);
    }
}

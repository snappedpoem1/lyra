use std::collections::HashSet;
use std::time::Duration;

use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::provider_runtime::{self, JsonFetchResult};

const MUSICBRAINZ_CACHE_PROVIDER: &str = "musicbrainz_catalog";
const MUSICBRAINZ_BASE_URL: &str = "https://musicbrainz.org/ws/2";
const MUSICBRAINZ_CACHE_TTL_SECONDS: u64 = 60 * 60 * 24 * 30;
const MUSICBRAINZ_USER_AGENT: &str = "Lyra/0.1 (catalog planner)";
const SKIP_SECONDARY_TYPES: &[&str] = &[
    "compilation",
    "dj-mix",
    "mixtape/street",
    "remix",
    "soundtrack",
    "spokenword",
    "audio drama",
];
const NON_CANONICAL_RELEASE_TOKENS: &[&str] = &[
    "karaoke",
    "tribute",
    "cover",
    "nightcore",
    "sped up",
    "slowed",
    "lofi",
    "lo-fi",
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CatalogArtist {
    pub name: String,
    pub mbid: String,
    pub artist_type: Option<String>,
    pub disambiguation: Option<String>,
    pub source_mode: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CatalogTrack {
    pub recording_mbid: Option<String>,
    pub title: String,
    pub position: i64,
    pub disc_number: i64,
    pub duration_ms: Option<i64>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CatalogRelease {
    pub release_group_mbid: String,
    pub release_mbid: String,
    pub title: String,
    pub release_type: String,
    pub year: Option<i32>,
    pub release_date: Option<String>,
    pub tracks: Vec<CatalogTrack>,
    pub source_mode: String,
    pub evidence_summary: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct CatalogDiscography {
    pub artist: CatalogArtist,
    pub releases: Vec<CatalogRelease>,
}

#[derive(Clone, Debug)]
struct CandidateReleaseMetadata {
    id: String,
    title: String,
    date: Option<String>,
    country: Option<String>,
    status: Option<String>,
    track_count: usize,
}

pub(crate) fn artist_search_cache_key(artist_name: &str) -> String {
    format!("artist-search:{}", normalize_key(artist_name))
}

pub(crate) fn release_group_cache_key(artist_mbid: &str, release_type: &str) -> String {
    format!(
        "release-groups:{}:{}",
        artist_mbid.trim().to_ascii_lowercase(),
        release_type.trim().to_ascii_lowercase()
    )
}

pub(crate) fn release_candidates_cache_key(release_group_mbid: &str) -> String {
    format!(
        "release-candidates:{}",
        release_group_mbid.trim().to_ascii_lowercase()
    )
}

pub(crate) fn release_detail_cache_key(release_mbid: &str) -> String {
    format!(
        "release-detail:{}",
        release_mbid.trim().to_ascii_lowercase()
    )
}

pub fn lookup_artist(conn: &Connection, artist_name: &str) -> Result<CatalogArtist, String> {
    let payload = cached_musicbrainz_request(
        conn,
        &artist_search_cache_key(artist_name),
        "artist",
        &[
            ("query", format!("artist:\"{}\"", artist_name.trim())),
            ("limit", "5".to_string()),
            ("fmt", "json".to_string()),
        ],
    )?;
    parse_artist_search_payload(&payload, artist_name)
        .map(|mut artist| {
            artist.source_mode = payload.source_mode;
            artist
        })
        .ok_or_else(|| format!("artist '{}' not found in MusicBrainz", artist_name.trim()))
}

pub fn resolve_album(
    conn: &Connection,
    artist_name: &str,
    album_title: &str,
) -> Result<(CatalogArtist, CatalogRelease), String> {
    let artist = lookup_artist(conn, artist_name)?;
    let requested_variant = explicit_variant_requested(album_title);
    let releases = load_catalog_releases(conn, &artist, requested_variant)?;
    let target = normalize_key(album_title);
    let best = releases
        .into_iter()
        .map(|release| {
            let score = strsim::normalized_levenshtein(&target, &normalize_key(&release.title));
            (release, score)
        })
        .max_by(|left, right| {
            left.1
                .partial_cmp(&right.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .filter(|(_, score)| *score >= 0.72)
        .map(|(release, _)| release)
        .ok_or_else(|| {
            format!(
                "album '{}' was not found in the canonical catalog for {}",
                album_title.trim(),
                artist.name
            )
        })?;
    Ok((artist, best))
}

pub fn resolve_discography(
    conn: &Connection,
    artist_name: &str,
    limit_albums: Option<usize>,
) -> Result<CatalogDiscography, String> {
    let artist = lookup_artist(conn, artist_name)?;
    let mut releases = load_catalog_releases(conn, &artist, false)?;
    if let Some(limit) = limit_albums.filter(|value| *value > 0) {
        releases.truncate(limit);
    }
    if releases.is_empty() {
        return Err(format!(
            "no canonical albums or EPs were found for {}",
            artist.name
        ));
    }
    Ok(CatalogDiscography { artist, releases })
}

fn load_catalog_releases(
    conn: &Connection,
    artist: &CatalogArtist,
    requested_variant: bool,
) -> Result<Vec<CatalogRelease>, String> {
    let mut releases = Vec::new();
    for release_type in ["album", "ep"] {
        let payload = cached_musicbrainz_request(
            conn,
            &release_group_cache_key(&artist.mbid, release_type),
            "release-group",
            &[
                ("artist", artist.mbid.clone()),
                ("type", release_type.to_string()),
                ("limit", "100".to_string()),
                ("fmt", "json".to_string()),
            ],
        )?;
        for group in parse_release_groups_payload(&payload.payload, requested_variant) {
            let (release_mbid, release_date, detail_source_mode) =
                select_best_release_candidate(conn, &group.release_group_mbid)?;
            let detail = load_release_tracks(conn, &release_mbid)?;
            if detail.tracks.is_empty() {
                continue;
            }
            releases.push(CatalogRelease {
                release_group_mbid: group.release_group_mbid,
                release_mbid,
                title: group.title,
                release_type: group.release_type,
                year: group.year,
                release_date,
                tracks: detail.tracks,
                source_mode: combine_source_modes(&payload.source_mode, &detail_source_mode),
                evidence_summary: format!(
                    "MusicBrainz {} release metadata ({})",
                    detail.release_title_source,
                    combine_source_modes(&payload.source_mode, &detail_source_mode)
                ),
            });
        }
    }
    releases.sort_by(|left, right| {
        left.year
            .unwrap_or(9999)
            .cmp(&right.year.unwrap_or(9999))
            .then_with(|| left.title.cmp(&right.title))
    });
    Ok(releases)
}

#[derive(Clone, Debug)]
struct ReleaseGroupCandidate {
    release_group_mbid: String,
    title: String,
    release_type: String,
    year: Option<i32>,
}

fn parse_artist_search_payload(
    payload: &JsonFetchResult,
    artist_name: &str,
) -> Option<CatalogArtist> {
    parse_artist_candidates(&payload.payload, artist_name)
}

fn parse_artist_candidates(payload: &Value, artist_name: &str) -> Option<CatalogArtist> {
    let normalized_target = normalize_key(artist_name);
    let mut candidates = payload
        .get("artists")
        .and_then(Value::as_array)?
        .iter()
        .filter_map(|entry| {
            let name = entry
                .get("name")
                .and_then(Value::as_str)?
                .trim()
                .to_string();
            let mbid = entry.get("id").and_then(Value::as_str)?.trim().to_string();
            let score = entry
                .get("score")
                .and_then(Value::as_i64)
                .or_else(|| {
                    entry
                        .get("score")
                        .and_then(Value::as_str)
                        .and_then(|value| value.parse::<i64>().ok())
                })
                .unwrap_or_default();
            Some((
                CatalogArtist {
                    name,
                    mbid,
                    artist_type: entry
                        .get("type")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    disambiguation: entry
                        .get("disambiguation")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                    source_mode: "live".to_string(),
                },
                score,
            ))
        })
        .collect::<Vec<_>>();
    candidates.sort_by(|left, right| right.1.cmp(&left.1));
    candidates
        .iter()
        .cloned()
        .find_map(|(artist, score)| {
            let exact = normalize_key(&artist.name) == normalized_target;
            if exact && score >= 90 {
                Some(artist)
            } else {
                None
            }
        })
        .or_else(|| {
            candidates
                .into_iter()
                .find(|(_, score)| *score >= 75)
                .map(|(artist, _)| artist)
        })
}

fn parse_release_groups_payload(
    payload: &Value,
    requested_variant: bool,
) -> Vec<ReleaseGroupCandidate> {
    payload
        .get("release-groups")
        .and_then(Value::as_array)
        .map(|groups| {
            groups
                .iter()
                .filter_map(|group| {
                    let title = group
                        .get("title")
                        .and_then(Value::as_str)?
                        .trim()
                        .to_string();
                    let secondary = group
                        .get("secondary-types")
                        .and_then(Value::as_array)
                        .map(|values| {
                            values
                                .iter()
                                .filter_map(Value::as_str)
                                .map(|value| value.to_ascii_lowercase())
                                .collect::<HashSet<_>>()
                        })
                        .unwrap_or_default();
                    if should_skip_release_group(&title, &secondary, requested_variant) {
                        return None;
                    }
                    Some(ReleaseGroupCandidate {
                        release_group_mbid: group.get("id").and_then(Value::as_str)?.to_string(),
                        title,
                        release_type: group
                            .get("primary-type")
                            .and_then(Value::as_str)
                            .unwrap_or("album")
                            .to_ascii_lowercase(),
                        year: group
                            .get("first-release-date")
                            .and_then(Value::as_str)
                            .and_then(parse_release_year),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

fn should_skip_release_group(
    title: &str,
    secondary_types: &HashSet<String>,
    requested_variant: bool,
) -> bool {
    if !requested_variant {
        if secondary_types
            .iter()
            .any(|value| SKIP_SECONDARY_TYPES.contains(&value.as_str()))
        {
            return true;
        }
        let lower = title.to_ascii_lowercase();
        if NON_CANONICAL_RELEASE_TOKENS
            .iter()
            .any(|token| lower.contains(token))
        {
            return true;
        }
        if is_probably_live_title(&lower) {
            return true;
        }
    }
    false
}

fn select_best_release_candidate(
    conn: &Connection,
    release_group_mbid: &str,
) -> Result<(String, Option<String>, String), String> {
    let payload = cached_musicbrainz_request(
        conn,
        &release_candidates_cache_key(release_group_mbid),
        "release",
        &[
            ("release-group", release_group_mbid.to_string()),
            ("limit", "25".to_string()),
            ("fmt", "json".to_string()),
        ],
    )?;
    let best = parse_release_candidates(&payload.payload)
        .into_iter()
        .max_by(|left, right| {
            release_candidate_sort_key(left).cmp(&release_candidate_sort_key(right))
        })
        .ok_or_else(|| {
            format!(
                "release-group '{}' did not expose any concrete releases",
                release_group_mbid
            )
        })?;
    Ok((best.id, best.date, payload.source_mode))
}

fn release_candidate_sort_key(candidate: &CandidateReleaseMetadata) -> (i64, i64, i64, String) {
    let official_bonus = candidate
        .status
        .as_deref()
        .map(|value| i64::from(value.eq_ignore_ascii_case("official")))
        .unwrap_or_default();
    let country_bonus = candidate
        .country
        .as_deref()
        .map(|value| {
            i64::from(matches!(
                value.to_ascii_uppercase().as_str(),
                "US" | "XW" | "GB"
            ))
        })
        .unwrap_or_default();
    (
        official_bonus,
        country_bonus,
        candidate.track_count as i64,
        candidate.title.clone(),
    )
}

fn parse_release_candidates(payload: &Value) -> Vec<CandidateReleaseMetadata> {
    payload
        .get("releases")
        .and_then(Value::as_array)
        .map(|releases| {
            releases
                .iter()
                .filter_map(|release| {
                    Some(CandidateReleaseMetadata {
                        id: release.get("id").and_then(Value::as_str)?.to_string(),
                        title: release.get("title").and_then(Value::as_str)?.to_string(),
                        date: release
                            .get("date")
                            .and_then(Value::as_str)
                            .map(str::to_string),
                        country: release
                            .get("country")
                            .and_then(Value::as_str)
                            .map(str::to_string),
                        status: release
                            .get("status")
                            .and_then(Value::as_str)
                            .map(str::to_string),
                        track_count: release
                            .get("media")
                            .and_then(Value::as_array)
                            .map(|media| {
                                media.iter().fold(0_usize, |total, medium| {
                                    total
                                        + medium
                                            .get("track-count")
                                            .and_then(Value::as_u64)
                                            .unwrap_or_default()
                                            as usize
                                })
                            })
                            .unwrap_or_default(),
                    })
                })
                .collect()
        })
        .unwrap_or_default()
}

#[derive(Clone, Debug)]
struct ReleaseTracksPayload {
    tracks: Vec<CatalogTrack>,
    release_title_source: String,
}

fn load_release_tracks(
    conn: &Connection,
    release_mbid: &str,
) -> Result<ReleaseTracksPayload, String> {
    let payload = cached_musicbrainz_request(
        conn,
        &release_detail_cache_key(release_mbid),
        &format!("release/{}", release_mbid.trim()),
        &[
            ("inc", "recordings".to_string()),
            ("fmt", "json".to_string()),
        ],
    )?;
    Ok(ReleaseTracksPayload {
        tracks: parse_release_tracks(&payload.payload),
        release_title_source: payload.source_mode,
    })
}

fn parse_release_tracks(payload: &Value) -> Vec<CatalogTrack> {
    payload
        .get("media")
        .and_then(Value::as_array)
        .map(|media| {
            media
                .iter()
                .enumerate()
                .flat_map(|(disc_index, medium)| {
                    medium
                        .get("tracks")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                        .filter_map(move |track| {
                            let title = track
                                .get("title")
                                .or_else(|| track.pointer("/recording/title"))
                                .and_then(Value::as_str)?
                                .trim()
                                .to_string();
                            if title.is_empty() {
                                return None;
                            }
                            Some(CatalogTrack {
                                recording_mbid: track
                                    .pointer("/recording/id")
                                    .and_then(Value::as_str)
                                    .map(str::to_string),
                                title,
                                position: track
                                    .get("position")
                                    .and_then(Value::as_i64)
                                    .unwrap_or_else(|| {
                                        track
                                            .get("number")
                                            .and_then(Value::as_str)
                                            .and_then(|value| value.parse::<i64>().ok())
                                            .unwrap_or_default()
                                    }),
                                disc_number: track
                                    .get("disc-number")
                                    .and_then(Value::as_i64)
                                    .unwrap_or(disc_index as i64 + 1),
                                duration_ms: track
                                    .pointer("/recording/length")
                                    .and_then(Value::as_i64)
                                    .or_else(|| track.get("length").and_then(Value::as_i64)),
                            })
                        })
                        .collect::<Vec<_>>()
                })
                .collect()
        })
        .unwrap_or_default()
}

fn cached_musicbrainz_request(
    conn: &Connection,
    cache_key: &str,
    path: &str,
    params: &[(&str, String)],
) -> Result<JsonFetchResult, String> {
    let base_url = musicbrainz_base_url(conn);
    let url = format!(
        "{}/{}",
        base_url.trim_end_matches('/'),
        path.trim_start_matches('/')
    );
    provider_runtime::cached_json_request(
        conn,
        MUSICBRAINZ_CACHE_PROVIDER,
        cache_key,
        Duration::from_secs(MUSICBRAINZ_CACHE_TTL_SECONDS),
        || {
            let mut request = ureq::get(&url).set("User-Agent", MUSICBRAINZ_USER_AGENT);
            for (key, value) in params {
                request = request.query(key, value);
            }
            request.call()
        },
    )
}

fn musicbrainz_base_url(conn: &Connection) -> String {
    conn.query_row(
        "SELECT config_json FROM provider_configs WHERE provider_key = 'musicbrainz'",
        [],
        |row| row.get::<_, String>(0),
    )
    .ok()
    .and_then(|json| serde_json::from_str::<Value>(&json).ok())
    .and_then(|value| {
        value
            .get("musicbrainz_base_url")
            .or_else(|| value.get("MUSICBRAINZ_BASE_URL"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
    })
    .unwrap_or_else(|| MUSICBRAINZ_BASE_URL.to_string())
}

fn parse_release_year(value: &str) -> Option<i32> {
    value.get(0..4).and_then(|slice| slice.parse::<i32>().ok())
}

fn explicit_variant_requested(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();
    NON_CANONICAL_RELEASE_TOKENS
        .iter()
        .any(|token| lower.contains(token))
        || is_probably_live_title(&lower)
}

fn is_probably_live_title(lower: &str) -> bool {
    lower.contains(" live ")
        || lower.starts_with("live ")
        || lower.ends_with(" live")
        || lower.contains(" live at ")
        || lower.contains(" live from ")
        || lower.contains(" live in ")
}

fn normalize_key(value: &str) -> String {
    value
        .to_ascii_lowercase()
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch.is_ascii_whitespace() {
                ch
            } else {
                ' '
            }
        })
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn combine_source_modes(left: &str, right: &str) -> String {
    if left == "live" && right == "live" {
        "live".to_string()
    } else if left.contains("cache_fallback") || right.contains("cache_fallback") {
        "cache_fallback".to_string()
    } else if left.contains("cache") || right.contains("cache") {
        "cache".to_string()
    } else {
        "live".to_string()
    }
}

#[cfg(test)]
mod tests {
    use chrono::Utc;
    use rusqlite::{params, Connection};
    use serde_json::{json, Value};

    use super::{
        artist_search_cache_key, parse_release_groups_payload, release_candidates_cache_key,
        release_detail_cache_key, release_group_cache_key, resolve_album, resolve_discography,
        MUSICBRAINZ_CACHE_PROVIDER,
    };
    use crate::db;

    fn setup_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        conn
    }

    fn seed_cache(conn: &Connection, provider: &str, key: &str, payload: Value) {
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![provider, key, payload.to_string(), Utc::now().to_rfc3339()],
        )
        .expect("cache seed");
    }

    #[test]
    fn release_group_filter_rejects_live_and_tribute_variants() {
        let releases = parse_release_groups_payload(
            &json!({
                "release-groups": [
                    {
                        "id": "rg-live",
                        "title": "Domestica Live in Omaha",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2005-01-01"
                    },
                    {
                        "id": "rg-tribute",
                        "title": "A Tribute to Domestica",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2006-01-01"
                    },
                    {
                        "id": "rg-canonical",
                        "title": "Domestica",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2000-06-13"
                    }
                ]
            }),
            false,
        );

        assert_eq!(releases.len(), 1);
        assert_eq!(releases[0].title, "Domestica");
    }

    #[test]
    fn cached_catalog_discography_prefers_canonical_releases() {
        let conn = setup_conn();
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &artist_search_cache_key("Cursive"),
            json!({
                "artists": [
                    {
                        "id": "artist-cursive",
                        "name": "Cursive",
                        "type": "Group",
                        "score": "100"
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_group_cache_key("artist-cursive", "album"),
            json!({
                "release-groups": [
                    {
                        "id": "rg-domestica",
                        "title": "Domestica",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2000-06-13"
                    },
                    {
                        "id": "rg-live",
                        "title": "Domestica Live",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2005-06-13"
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_group_cache_key("artist-cursive", "ep"),
            json!({
                "release-groups": []
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_candidates_cache_key("rg-domestica"),
            json!({
                "releases": [
                    {
                        "id": "release-domestica",
                        "title": "Domestica",
                        "status": "Official",
                        "country": "US",
                        "date": "2000-06-13",
                        "media": [{"track-count": 2}]
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_detail_cache_key("release-domestica"),
            json!({
                "media": [
                    {
                        "tracks": [
                            {
                                "position": 1,
                                "title": "The Casualty",
                                "recording": {"id": "rec-1", "length": 191000}
                            },
                            {
                                "position": 2,
                                "title": "A Red So Deep",
                                "recording": {"id": "rec-2", "length": 233000}
                            }
                        ]
                    }
                ]
            }),
        );

        let discography = resolve_discography(&conn, "Cursive", None).expect("discography");

        assert_eq!(discography.artist.name, "Cursive");
        assert_eq!(discography.releases.len(), 1);
        assert_eq!(discography.releases[0].title, "Domestica");
        assert_eq!(discography.releases[0].tracks.len(), 2);
        assert_eq!(discography.releases[0].source_mode, "cache");
    }

    #[test]
    fn resolve_album_uses_cached_musicbrainz_metadata() {
        let conn = setup_conn();
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &artist_search_cache_key("Cursive"),
            json!({
                "artists": [
                    {
                        "id": "artist-cursive",
                        "name": "Cursive",
                        "type": "Group",
                        "score": 100
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_group_cache_key("artist-cursive", "album"),
            json!({
                "release-groups": [
                    {
                        "id": "rg-ugly",
                        "title": "The Ugly Organ",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2003-10-07"
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_group_cache_key("artist-cursive", "ep"),
            json!({
                "release-groups": []
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_candidates_cache_key("rg-ugly"),
            json!({
                "releases": [
                    {
                        "id": "release-ugly",
                        "title": "The Ugly Organ",
                        "status": "Official",
                        "country": "US",
                        "date": "2003-10-07",
                        "media": [{"track-count": 1}]
                    }
                ]
            }),
        );
        seed_cache(
            &conn,
            MUSICBRAINZ_CACHE_PROVIDER,
            &release_detail_cache_key("release-ugly"),
            json!({
                "media": [
                    {
                        "tracks": [
                            {
                                "position": 1,
                                "title": "Some Red-Handed Sleight of Hand",
                                "recording": {"id": "rec-ugly-1", "length": 255000}
                            }
                        ]
                    }
                ]
            }),
        );

        let (artist, release) = resolve_album(&conn, "Cursive", "The Ugly Organ").expect("album");

        assert_eq!(artist.name, "Cursive");
        assert_eq!(release.title, "The Ugly Organ");
        assert_eq!(release.tracks.len(), 1);
        assert_eq!(release.source_mode, "cache");
    }
}

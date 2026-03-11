//! Artist intelligence ingestor — pulls MusicBrainz relationship edges into artist_lineage_edges.
//!
//! This is the broad ingestion counterpart to the curated baseline in `lineage.rs`.
//! Where lineage.rs seeds a small hand-curated set, this module:
//!
//! 1. Iterates library artists that don't yet have MB-sourced relationship edges.
//! 2. Resolves each to a MusicBrainz artist MBID via the catalog lookup path.
//! 3. Fetches the artist's relationship list (member-of, subgroup, influence) from MB.
//! 4. Persists verified edges into `artist_lineage_edges` with evidence_level = 'verified'.
//!
//! Rate limiting: MB allows ~1 req/s. We honour that with a 1100ms sleep between calls.
//! Cache: all raw MB payloads are stored in `enrich_cache` to avoid re-fetching.

use std::time::Duration;

use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::errors::LyraResult;

const MB_BASE: &str = "https://musicbrainz.org/ws/2";
const MB_USER_AGENT: &str = "Lyra/0.1 (artist-intelligence; contact@lyramusic.app)";
const MB_CACHE_PROVIDER: &str = "musicbrainz_artist_intelligence";
const MB_CACHE_TTL_SECONDS: u64 = 60 * 60 * 24 * 30; // 30 days
const MB_RATE_SLEEP_MS: u64 = 1100;

// MusicBrainz relationship type strings we care about
const MB_MEMBER_OF: &str = "member of band";
const MB_SUBGROUP: &str = "subgroup";
const MB_FOUNDER: &str = "founder";
const MB_INFLUENCE: &str = "influenced by";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct IngestResult {
    pub artists_processed: usize,
    pub edges_inserted: usize,
    pub artists_skipped: usize,
    pub errors: Vec<String>,
}

/// Summary of the last lineage ingest run plus current pending state.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LineageIngestStatus {
    pub pending_artists: usize,
    pub last_run_at: Option<String>,
    pub last_run_artists_processed: Option<i64>,
    pub last_run_edges_inserted: Option<i64>,
    pub last_run_errors: Option<i64>,
    pub total_verified_edges: i64,
}

#[derive(Debug, Deserialize)]
struct MbArtistSearchResult {
    artists: Option<Vec<MbArtistCandidate>>,
}

#[derive(Debug, Deserialize)]
struct MbArtistCandidate {
    id: String,
    name: String,
    score: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct MbArtistRelations {
    relations: Option<Vec<MbRelation>>,
}

#[derive(Debug, Deserialize)]
struct MbRelation {
    #[serde(rename = "type")]
    relation_type: String,
    direction: String,
    artist: Option<MbRelatedArtist>,
    attributes: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
struct MbRelatedArtist {
    id: String,
    name: String,
}

// ── Cache helpers ─────────────────────────────────────────────────────────────

fn cache_get(conn: &Connection, key: &str) -> Option<Value> {
    let now_ts = Utc::now().timestamp() as u64;
    conn.query_row(
        "SELECT payload_json, fetched_at FROM enrich_cache
         WHERE provider = ?1 AND lookup_key = ?2",
        params![MB_CACHE_PROVIDER, key],
        |row| {
            let payload: String = row.get(0)?;
            let fetched: String = row.get(1)?;
            Ok((payload, fetched))
        },
    )
    .ok()
    .and_then(|(payload, fetched)| {
        let fetched_ts = chrono::DateTime::parse_from_rfc3339(&fetched)
            .map(|dt| dt.timestamp() as u64)
            .unwrap_or(0);
        if now_ts.saturating_sub(fetched_ts) > MB_CACHE_TTL_SECONDS {
            None
        } else {
            serde_json::from_str(&payload).ok()
        }
    })
}

fn cache_put(conn: &Connection, key: &str, payload: &Value) {
    let _ = conn.execute(
        "INSERT OR REPLACE INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
         VALUES (?1, ?2, ?3, ?4)",
        params![
            MB_CACHE_PROVIDER,
            key,
            serde_json::to_string(payload).unwrap_or_default(),
            Utc::now().to_rfc3339(),
        ],
    );
}

// ── MB API fetch helpers ──────────────────────────────────────────────────────

fn mb_get(path: &str, query: &[(&str, &str)]) -> Option<Value> {
    std::thread::sleep(Duration::from_millis(MB_RATE_SLEEP_MS));

    let mut url = format!("{MB_BASE}/{path}?fmt=json");
    for (k, v) in query {
        url.push('&');
        url.push_str(&format!("{}={}", k, urlencoding::encode(v)));
    }

    let resp = ureq::get(&url)
        .set("User-Agent", MB_USER_AGENT)
        .set("Accept", "application/json")
        .call();

    match resp {
        Ok(r) => r.into_json::<Value>().ok(),
        Err(ureq::Error::Status(503, _)) | Err(ureq::Error::Status(429, _)) => {
            // Back off and retry once
            std::thread::sleep(Duration::from_secs(5));
            ureq::get(&url)
                .set("User-Agent", MB_USER_AGENT)
                .set("Accept", "application/json")
                .call()
                .ok()
                .and_then(|r| r.into_json::<Value>().ok())
        }
        Err(_) => None,
    }
}

/// Resolve an artist name to a MB MBID. Returns the best-scoring match ≥ 85%.
fn resolve_mbid(conn: &Connection, artist_name: &str) -> Option<(String, String)> {
    let cache_key = format!("mbid:{}", artist_name.to_ascii_lowercase().trim());
    if let Some(cached) = cache_get(conn, &cache_key) {
        let id = cached
            .get("id")
            .and_then(Value::as_str)
            .map(str::to_string)?;
        let name = cached
            .get("name")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| artist_name.to_string());
        return Some((id, name));
    }

    let payload = mb_get(
        "artist",
        &[
            ("query", &format!("artist:\"{}\"", artist_name.trim())),
            ("limit", "5"),
        ],
    )?;
    let result: MbArtistSearchResult = serde_json::from_value(payload.clone()).ok()?;
    let candidates = result.artists?;

    let best = candidates.into_iter().find(|c| {
        let score = c
            .score
            .as_ref()
            .and_then(|s| match s {
                Value::Number(n) => n.as_f64(),
                Value::String(s) => s.parse::<f64>().ok(),
                _ => None,
            })
            .unwrap_or(0.0);
        score >= 85.0
    })?;

    let entry = json!({"id": best.id, "name": best.name});
    cache_put(conn, &cache_key, &entry);
    Some((best.id, best.name))
}

/// Fetch artist relations from MB for a known MBID.
fn fetch_artist_relations(conn: &Connection, mbid: &str) -> Option<Vec<MbRelation>> {
    let cache_key = format!("relations:{}", mbid);
    if let Some(cached) = cache_get(conn, &cache_key) {
        let relations: Vec<MbRelation> = serde_json::from_value(
            cached
                .get("relations")
                .cloned()
                .unwrap_or(Value::Array(vec![])),
        )
        .ok()?;
        return Some(relations);
    }

    let payload = mb_get(&format!("artist/{mbid}"), &[("inc", "artist-rels")])?;
    cache_put(conn, &cache_key, &payload);
    let parsed: MbArtistRelations = serde_json::from_value(payload).ok()?;
    Some(parsed.relations.unwrap_or_default())
}

// ── Relationship mapper ───────────────────────────────────────────────────────

/// Map a MB relation type + direction to our internal relationship_type + weight.
fn map_mb_relation(rel: &MbRelation) -> Option<(&'static str, f64)> {
    let rt = rel.relation_type.to_ascii_lowercase();
    let dir = rel.direction.as_str();

    match (rt.as_str(), dir) {
        (MB_MEMBER_OF, "backward") => Some(("member_of", 0.90)),
        (MB_MEMBER_OF, "forward") => Some(("shared_member", 0.85)),
        (MB_SUBGROUP, _) => Some(("offshoot", 0.88)),
        (MB_FOUNDER, _) => Some(("member_of", 0.82)),
        (MB_INFLUENCE, "forward") => Some(("influence", 0.70)),
        (MB_INFLUENCE, "backward") => Some(("influence", 0.70)),
        _ => None,
    }
}

// ── Edge persistence ──────────────────────────────────────────────────────────

fn upsert_edge(
    conn: &Connection,
    source: &str,
    target: &str,
    rel_type: &str,
    weight: f64,
    note: &str,
    facts: &[String],
    source_mbid: &str,
    target_mbid: &str,
) -> bool {
    let evidence = json!({
        "note": note,
        "facts": facts,
        "source": "musicbrainz",
        "source_mbid": source_mbid,
        "target_mbid": target_mbid,
    });
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO artist_lineage_edges
         (source_artist, target_artist, relationship_type, evidence_level, weight, evidence_json, updated_at)
         VALUES (?1, ?2, ?3, 'verified', ?4, ?5, ?6)
         ON CONFLICT(source_artist, target_artist, relationship_type)
         DO UPDATE SET
           evidence_level = 'verified',
           weight = MAX(weight, excluded.weight),
           evidence_json = excluded.evidence_json,
           updated_at = excluded.updated_at",
        params![
            source,
            target,
            rel_type,
            weight,
            evidence.to_string(),
            now,
        ],
    )
    .is_ok()
}

// ── Artists to process ────────────────────────────────────────────────────────

/// Returns library artists that have no verified MB lineage edges yet.
fn artists_needing_ingestion(conn: &Connection, limit: usize) -> LyraResult<Vec<String>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT ar.name
         FROM artists ar
         JOIN tracks t ON t.artist_id = ar.id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND trim(COALESCE(ar.name, '')) != ''
           AND ar.name NOT IN (
             SELECT DISTINCT source_artist
             FROM artist_lineage_edges
             WHERE evidence_level = 'verified'
           )
         ORDER BY ar.name
         LIMIT ?1",
    )?;
    let results: Vec<String> = stmt
        .query_map(params![limit as i64], |row| row.get(0))?
        .filter_map(Result::ok)
        .collect();
    Ok(results)
}

// ── Public entry point ────────────────────────────────────────────────────────

/// Persist a summary record after a lineage ingest run.
pub fn log_ingest_run(conn: &Connection, result: &IngestResult) {
    let _ = conn.execute(
        "INSERT INTO lineage_ingest_log
         (run_at, artists_processed, edges_inserted, artists_skipped, error_count)
         VALUES (?1, ?2, ?3, ?4, ?5)",
        rusqlite::params![
            Utc::now().to_rfc3339(),
            result.artists_processed as i64,
            result.edges_inserted as i64,
            result.artists_skipped as i64,
            result.errors.len() as i64,
        ],
    );
}

/// Return the current ingest status: pending count + last run summary.
pub fn ingest_status(conn: &Connection) -> LineageIngestStatus {
    let pending = pending_ingestion_count(conn);
    let total_edges: i64 = conn
        .query_row(
            "SELECT COUNT(*) FROM artist_lineage_edges WHERE evidence_level = 'verified'",
            [],
            |row| row.get(0),
        )
        .unwrap_or(0);

    let last_run = conn
        .query_row(
            "SELECT run_at, artists_processed, edges_inserted, error_count
             FROM lineage_ingest_log
             ORDER BY run_at DESC
             LIMIT 1",
            [],
            |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, i64>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, i64>(3)?,
                ))
            },
        )
        .ok();

    LineageIngestStatus {
        pending_artists: pending,
        last_run_at: last_run.as_ref().map(|r| r.0.clone()),
        last_run_artists_processed: last_run.as_ref().map(|r| r.1),
        last_run_edges_inserted: last_run.as_ref().map(|r| r.2),
        last_run_errors: last_run.as_ref().map(|r| r.3),
        total_verified_edges: total_edges,
    }
}

/// Ingest MusicBrainz artist relationship edges for up to `limit` library artists
/// that do not yet have any verified lineage edges.
///
/// This is designed to be called from a background job or a Tauri command.
/// It is intentionally blocking (synchronous) so callers can choose whether to
/// spawn it on a thread pool.
pub fn ingest_artist_relationships(conn: &Connection, limit: usize) -> LyraResult<IngestResult> {
    let artists = artists_needing_ingestion(conn, limit.clamp(1, 200))?;
    let total = artists.len();
    let mut edges_inserted = 0_usize;
    let mut artists_skipped = 0_usize;
    let mut errors: Vec<String> = Vec::new();

    for artist_name in &artists {
        // Step 1: resolve to MBID
        let (mbid, canonical_name) = match resolve_mbid(conn, artist_name) {
            Some(v) => v,
            None => {
                artists_skipped += 1;
                tracing::debug!("artist_intelligence: no MB match for '{}'", artist_name);
                continue;
            }
        };

        // Step 2: fetch relations
        let relations = match fetch_artist_relations(conn, &mbid) {
            Some(v) => v,
            None => {
                errors.push(format!(
                    "failed to fetch relations for '{artist_name}' ({mbid})"
                ));
                continue;
            }
        };

        // Step 3: map and persist edges
        for rel in &relations {
            let related = match rel.artist.as_ref() {
                Some(a) => a,
                None => continue,
            };
            if related.name.is_empty() {
                continue;
            }
            let (rel_type, weight) = match map_mb_relation(rel) {
                Some(v) => v,
                None => continue,
            };

            let attrs = rel.attributes.as_deref().unwrap_or(&[]);
            let facts: Vec<String> = attrs.iter().map(|a| format!("mb_attribute: {a}")).collect();

            let note = format!(
                "MusicBrainz verified relationship: {} {} {} (direction: {})",
                canonical_name, rel.relation_type, related.name, rel.direction
            );

            // Insert forward edge
            if upsert_edge(
                conn,
                &canonical_name,
                &related.name,
                rel_type,
                weight,
                &note,
                &facts,
                &mbid,
                &related.id,
            ) {
                edges_inserted += 1;
            }

            // Insert reverse edge (bidirectional — discovery works both ways)
            if upsert_edge(
                conn,
                &related.name,
                &canonical_name,
                rel_type,
                weight,
                &note,
                &facts,
                &related.id,
                &mbid,
            ) {
                edges_inserted += 1;
            }
        }

        tracing::info!(
            "artist_intelligence: processed '{}' ({}) — {} relations",
            artist_name,
            mbid,
            relations.len()
        );
    }

    let result = IngestResult {
        artists_processed: total - artists_skipped,
        edges_inserted,
        artists_skipped,
        errors,
    };
    log_ingest_run(conn, &result);
    Ok(result)
}

/// Returns the count of artists in the library that still need MB ingestion.
pub fn pending_ingestion_count(conn: &Connection) -> usize {
    conn.query_row(
        "SELECT COUNT(DISTINCT ar.name)
         FROM artists ar
         JOIN tracks t ON t.artist_id = ar.id
         WHERE (t.quarantined IS NULL OR t.quarantined = 0)
           AND trim(COALESCE(ar.name, '')) != ''
           AND ar.name NOT IN (
             SELECT DISTINCT source_artist
             FROM artist_lineage_edges
             WHERE evidence_level = 'verified'
           )",
        [],
        |row| row.get::<_, i64>(0),
    )
    .unwrap_or(0) as usize
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    use super::{map_mb_relation, pending_ingestion_count, MbRelation};
    use crate::db;

    fn make_relation(rel_type: &str, direction: &str) -> MbRelation {
        MbRelation {
            relation_type: rel_type.to_string(),
            direction: direction.to_string(),
            artist: None,
            attributes: None,
        }
    }

    #[test]
    fn maps_member_of_backward_to_member_of() {
        let rel = make_relation("member of band", "backward");
        let (rt, w) = map_mb_relation(&rel).expect("mapped");
        assert_eq!(rt, "member_of");
        assert!(w > 0.8);
    }

    #[test]
    fn maps_subgroup_to_offshoot() {
        let rel = make_relation("subgroup", "forward");
        let (rt, _) = map_mb_relation(&rel).expect("mapped");
        assert_eq!(rt, "offshoot");
    }

    #[test]
    fn ignores_unknown_relation_types() {
        let rel = make_relation("tribute", "forward");
        assert!(map_mb_relation(&rel).is_none());
    }

    #[test]
    fn pending_count_is_zero_for_empty_db() {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        assert_eq!(pending_ingestion_count(&conn), 0);
    }
}

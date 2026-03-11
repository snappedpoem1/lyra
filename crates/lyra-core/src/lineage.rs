use chrono::Utc;
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::commands::RelatedArtist;
use crate::errors::LyraResult;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct LineageEdge {
    pub source_artist: String,
    pub target_artist: String,
    pub relationship_type: String,
    pub evidence_level: String,
    pub weight: f64,
    pub note: String,
    pub facts: Vec<String>,
}

#[derive(Clone, Debug)]
struct CuratedLineageSeed {
    source_artist: &'static str,
    target_artist: &'static str,
    relationship_type: &'static str,
    weight: f64,
    note: &'static str,
    facts: &'static [&'static str],
}

fn curated_baseline() -> Vec<CuratedLineageSeed> {
    vec![
        CuratedLineageSeed {
            source_artist: "Cursive",
            target_artist: "The Good Life",
            relationship_type: "side_project",
            weight: 0.96,
            note: "Tim Kasher fronts both projects, so this is a direct side-project lineage.",
            facts: &["shared member: Tim Kasher"],
        },
        CuratedLineageSeed {
            source_artist: "The Good Life",
            target_artist: "Cursive",
            relationship_type: "side_project",
            weight: 0.96,
            note: "Tim Kasher fronts both projects, so this is a direct side-project lineage.",
            facts: &["shared member: Tim Kasher"],
        },
        CuratedLineageSeed {
            source_artist: "At The Drive-In",
            target_artist: "Sparta",
            relationship_type: "offshoot",
            weight: 0.95,
            note: "Sparta is a direct offshoot after the At The Drive-In split.",
            facts: &[
                "shared members: Jim Ward",
                "shared members: Tony Hajjar",
                "shared members: Paul Hinojos",
            ],
        },
        CuratedLineageSeed {
            source_artist: "Sparta",
            target_artist: "At The Drive-In",
            relationship_type: "offshoot",
            weight: 0.95,
            note: "Sparta is a direct offshoot after the At The Drive-In split.",
            facts: &[
                "shared members: Jim Ward",
                "shared members: Tony Hajjar",
                "shared members: Paul Hinojos",
            ],
        },
        CuratedLineageSeed {
            source_artist: "At The Drive-In",
            target_artist: "The Mars Volta",
            relationship_type: "offshoot",
            weight: 0.95,
            note: "The Mars Volta is a direct offshoot after the At The Drive-In split.",
            facts: &[
                "shared members: Cedric Bixler-Zavala",
                "shared members: Omar Rodriguez-Lopez",
            ],
        },
        CuratedLineageSeed {
            source_artist: "The Mars Volta",
            target_artist: "At The Drive-In",
            relationship_type: "offshoot",
            weight: 0.95,
            note: "The Mars Volta is a direct offshoot after the At The Drive-In split.",
            facts: &[
                "shared members: Cedric Bixler-Zavala",
                "shared members: Omar Rodriguez-Lopez",
            ],
        },
    ]
}

pub fn seed_curated_baseline(conn: &Connection) -> LyraResult<usize> {
    let now = Utc::now().to_rfc3339();
    let mut inserted = 0_usize;
    for seed in curated_baseline() {
        let evidence_json = json!({
            "note": seed.note,
            "facts": seed.facts,
            "source": "curated_baseline",
        });
        let affected = conn.execute(
            "INSERT OR IGNORE INTO artist_lineage_edges
             (source_artist, target_artist, relationship_type, evidence_level, weight, evidence_json, updated_at)
             VALUES (?1, ?2, ?3, 'curated', ?4, ?5, ?6)",
            params![
                seed.source_artist,
                seed.target_artist,
                seed.relationship_type,
                seed.weight,
                evidence_json.to_string(),
                now,
            ],
        )?;
        inserted += affected;
    }
    Ok(inserted)
}

pub fn lineage_edges_for_artist(
    conn: &Connection,
    artist_name: &str,
    limit: usize,
) -> LyraResult<Vec<LineageEdge>> {
    let mut stmt = conn.prepare(
        "SELECT source_artist, target_artist, relationship_type, evidence_level, weight, evidence_json
         FROM artist_lineage_edges
         WHERE lower(trim(source_artist)) = lower(trim(?1))
         ORDER BY weight DESC, target_artist ASC
         LIMIT ?2",
    )?;
    let rows = stmt.query_map(params![artist_name, limit.max(1) as i64], |row| {
        let evidence_json: String = row.get(5)?;
        let payload =
            serde_json::from_str::<serde_json::Value>(&evidence_json).unwrap_or_else(|_| json!({}));
        Ok(LineageEdge {
            source_artist: row.get(0)?,
            target_artist: row.get(1)?,
            relationship_type: row.get(2)?,
            evidence_level: row.get(3)?,
            weight: row.get(4)?,
            note: payload
                .get("note")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("No lineage note recorded.")
                .to_string(),
            facts: payload
                .get("facts")
                .and_then(serde_json::Value::as_array)
                .map(|values| {
                    values
                        .iter()
                        .filter_map(serde_json::Value::as_str)
                        .map(str::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default(),
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn lineage_related_artists(
    conn: &Connection,
    artist_name: &str,
    limit: usize,
) -> LyraResult<Vec<RelatedArtist>> {
    let edges = lineage_edges_for_artist(conn, artist_name, limit)?;
    Ok(edges
        .into_iter()
        .map(|edge| related_artist_from_edge(conn, edge))
        .collect())
}

fn related_artist_from_edge(conn: &Connection, edge: LineageEdge) -> RelatedArtist {
    let local_track_count = conn
        .query_row(
            "SELECT COUNT(*)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
            params![edge.target_artist.as_str()],
            |row| row.get::<_, i64>(0),
        )
        .unwrap_or_default() as usize;
    let evidence_summary = if edge.facts.is_empty() {
        edge.note.clone()
    } else {
        edge.facts.join("; ")
    };
    let (why, preserves, changes, risk_note) = match edge.relationship_type.as_str() {
        "side_project" => (
            "This is a true side-project link, so the emotional handwriting tends to survive the jump.".to_string(),
            vec!["core songwriter DNA".to_string(), "emotional handwriting".to_string()],
            vec!["scene framing".to_string()],
            "Lower risk: the relationship is direct, not guessed from loose adjacency.".to_string(),
        ),
        "offshoot" => (
            "This is a direct offshoot line from the same breakup tree, so the bridge is structural, not decorative.".to_string(),
            vec!["member chemistry".to_string(), "scene lineage".to_string()],
            vec!["surface style".to_string()],
            "Measured risk: the personnel link is real, but the sound can still diverge sharply."
                .to_string(),
        ),
        "shared_member" | "member_of" => (
            "Shared-member evidence connects these artists through actual personnel overlap.".to_string(),
            vec!["member overlap".to_string()],
            vec!["catalog context".to_string()],
            "Lower risk: this relationship is anchored to real membership evidence.".to_string(),
        ),
        "influence" => (
            "This is an influence edge, so the likeness is more historical than literal.".to_string(),
            vec!["historical lineage".to_string()],
            vec!["surface sound".to_string()],
            "Higher risk: influence claims are looser than direct member lineage.".to_string(),
        ),
        _ => (
            "This adjacency is anchored in artist-lineage evidence rather than loose metadata.".to_string(),
            vec!["artist lineage".to_string()],
            vec!["obviousness".to_string()],
            "Measured risk: the link is real, but the sonic distance can still matter.".to_string(),
        ),
    };
    RelatedArtist {
        name: edge.target_artist,
        connection_strength: edge.weight as f32,
        connection_type: edge.relationship_type,
        local_track_count,
        evidence_level: edge.evidence_level,
        evidence_summary,
        why,
        preserves,
        changes,
        risk_note,
    }
}

#[cfg(test)]
mod tests {
    use rusqlite::Connection;

    use super::{lineage_edges_for_artist, lineage_related_artists, seed_curated_baseline};
    use crate::db;

    fn setup_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        seed_curated_baseline(&conn).expect("baseline");
        conn
    }

    #[test]
    fn curated_lineage_baseline_supports_cursive_and_the_good_life() {
        let conn = setup_conn();

        let edges = lineage_edges_for_artist(&conn, "Cursive", 4).expect("edges");

        assert!(edges
            .iter()
            .any(|edge| edge.target_artist == "The Good Life"));
        assert!(edges
            .iter()
            .any(|edge| edge.facts.iter().any(|fact| fact.contains("Tim Kasher"))));
    }

    #[test]
    fn lineage_related_artists_expose_evidence_level() {
        let conn = setup_conn();

        let related = lineage_related_artists(&conn, "At The Drive-In", 4).expect("related");

        assert!(related.iter().any(|artist| {
            artist.name == "Sparta"
                && artist.evidence_level == "curated"
                && artist.evidence_summary.contains("Jim Ward")
        }));
        assert!(related.iter().any(|artist| artist.name == "The Mars Volta"));
    }
}

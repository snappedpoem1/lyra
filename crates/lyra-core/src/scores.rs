use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::TrackScores;
use crate::errors::LyraResult;

pub fn get_track_scores(conn: &Connection, track_id: i64) -> LyraResult<Option<TrackScores>> {
    let row = conn
        .query_row(
            "SELECT track_id, energy, valence, tension, density, warmth, movement,
                    space, rawness, complexity, nostalgia, bpm, key_signature,
                    scored_at, score_version
             FROM track_scores WHERE track_id = ?1",
            params![track_id],
            |row| {
                Ok(TrackScores {
                    track_id: row.get(0)?,
                    energy: row.get::<_, f64>(1).unwrap_or(0.5),
                    valence: row.get::<_, f64>(2).unwrap_or(0.5),
                    tension: row.get::<_, f64>(3).unwrap_or(0.5),
                    density: row.get::<_, f64>(4).unwrap_or(0.5),
                    warmth: row.get::<_, f64>(5).unwrap_or(0.5),
                    movement: row.get::<_, f64>(6).unwrap_or(0.5),
                    space: row.get::<_, f64>(7).unwrap_or(0.5),
                    rawness: row.get::<_, f64>(8).unwrap_or(0.5),
                    complexity: row.get::<_, f64>(9).unwrap_or(0.5),
                    nostalgia: row.get::<_, f64>(10).unwrap_or(0.5),
                    bpm: row.get(11)?,
                    key_signature: row.get(12)?,
                    scored_at: row.get(13)?,
                    score_version: row.get(14)?,
                })
            },
        )
        .optional()?;
    Ok(row)
}

pub fn upsert_track_scores(conn: &Connection, scores: &TrackScores) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO track_scores
            (track_id, energy, valence, tension, density, warmth, movement,
             space, rawness, complexity, nostalgia, bpm, key_signature, scored_at, score_version)
         VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15)
         ON CONFLICT(track_id) DO UPDATE SET
            energy=excluded.energy, valence=excluded.valence, tension=excluded.tension,
            density=excluded.density, warmth=excluded.warmth, movement=excluded.movement,
            space=excluded.space, rawness=excluded.rawness, complexity=excluded.complexity,
            nostalgia=excluded.nostalgia, bpm=excluded.bpm, key_signature=excluded.key_signature,
            scored_at=excluded.scored_at, score_version=excluded.score_version",
        params![
            scores.track_id,
            scores.energy,
            scores.valence,
            scores.tension,
            scores.density,
            scores.warmth,
            scores.movement,
            scores.space,
            scores.rawness,
            scores.complexity,
            scores.nostalgia,
            scores.bpm,
            scores.key_signature,
            scores.scored_at,
            scores.score_version,
        ],
    )?;
    Ok(())
}

pub fn import_scores_from_legacy(conn: &Connection, legacy: &Connection) -> LyraResult<usize> {
    // Legacy uses filepath as join key; our DB uses integer id
    let mut stmt = legacy.prepare(
        "SELECT t.filepath, s.energy, s.valence, s.tension, s.density, s.warmth,
                s.movement, s.space, s.rawness, s.complexity, s.nostalgia,
                s.scored_at, s.score_version
         FROM track_scores s
         JOIN tracks t ON t.track_id = s.track_id
         WHERE t.filepath IS NOT NULL",
    )?;

    let rows: Vec<_> = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, Option<f64>>(1)?,
                row.get::<_, Option<f64>>(2)?,
                row.get::<_, Option<f64>>(3)?,
                row.get::<_, Option<f64>>(4)?,
                row.get::<_, Option<f64>>(5)?,
                row.get::<_, Option<f64>>(6)?,
                row.get::<_, Option<f64>>(7)?,
                row.get::<_, Option<f64>>(8)?,
                row.get::<_, Option<f64>>(9)?,
                row.get::<_, Option<f64>>(10)?,
                row.get::<_, Option<String>>(11)?,
                row.get::<_, Option<i64>>(12)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();

    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;

    for (
        filepath,
        energy,
        valence,
        tension,
        density,
        warmth,
        movement,
        space,
        rawness,
        complexity,
        nostalgia,
        scored_at,
        score_version,
    ) in rows
    {
        let new_id: Option<i64> = conn
            .query_row(
                "SELECT id FROM tracks WHERE path = ?1",
                params![filepath],
                |row| row.get(0),
            )
            .optional()?;

        let Some(track_id) = new_id else { continue };

        // Also pull bpm/key from legacy track_structure if available
        let structure = legacy
            .query_row(
                "SELECT bpm, key_signature FROM track_structure ts
                 JOIN tracks t ON t.track_id = ts.track_id
                 WHERE t.filepath = ?1",
                params![filepath],
                |row| {
                    Ok((
                        row.get::<_, Option<f64>>(0)?,
                        row.get::<_, Option<String>>(1)?,
                    ))
                },
            )
            .optional()?
            .unwrap_or((None, None));

        let scores = TrackScores {
            track_id,
            energy: energy.unwrap_or(0.5),
            valence: valence.unwrap_or(0.5),
            tension: tension.unwrap_or(0.5),
            density: density.unwrap_or(0.5),
            warmth: warmth.unwrap_or(0.5),
            movement: movement.unwrap_or(0.5),
            space: space.unwrap_or(0.5),
            rawness: rawness.unwrap_or(0.5),
            complexity: complexity.unwrap_or(0.5),
            nostalgia: nostalgia.unwrap_or(0.5),
            bpm: structure.0,
            key_signature: structure.1,
            scored_at: scored_at.unwrap_or_else(|| now.clone()),
            score_version: score_version.unwrap_or(2),
        };

        if upsert_track_scores(conn, &scores).is_ok() {
            // Also write bpm/key_signature back to tracks row
            if scores.bpm.is_some() || scores.key_signature.is_some() {
                let _ = conn.execute(
                    "UPDATE tracks SET bpm = COALESCE(bpm, ?1), key_signature = COALESCE(key_signature, ?2) WHERE id = ?3",
                    params![scores.bpm, scores.key_signature, track_id],
                );
            }
            count += 1;
        }
    }
    Ok(count)
}

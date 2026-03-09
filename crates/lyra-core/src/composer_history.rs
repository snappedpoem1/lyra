use chrono::Utc;
use rusqlite::{params, Connection};

use crate::commands::{ComposerResponse, ComposerRunDetail, ComposerRunRecord};
use crate::errors::{LyraError, LyraResult};

pub fn save_run(conn: &Connection, prompt: &str, response: &ComposerResponse) -> LyraResult<i64> {
    let action = format!("{:?}", response.action).to_ascii_lowercase();
    let summary = response
        .framing
        .route_comparison
        .as_ref()
        .map(|comparison| comparison.headline.clone())
        .unwrap_or_else(|| response.framing.lead.clone());
    conn.execute(
        "INSERT INTO composer_runs (
            prompt, action, active_role, summary, provider, mode, response_json, created_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            prompt,
            action,
            response.active_role,
            summary,
            response.provider_status.selected_provider,
            response.provider_status.mode,
            serde_json::to_string(response)?,
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(conn.last_insert_rowid())
}

pub fn recent(conn: &Connection, limit: usize) -> LyraResult<Vec<ComposerRunRecord>> {
    let mut stmt = conn.prepare(
        "SELECT id, prompt, action, active_role, summary, provider, mode, created_at
         FROM composer_runs
         ORDER BY created_at DESC
         LIMIT ?1",
    )?;
    let rows = stmt.query_map(params![limit as i64], |row| {
        Ok(ComposerRunRecord {
            id: row.get(0)?,
            prompt: row.get(1)?,
            action: row.get(2)?,
            active_role: row.get(3)?,
            summary: row.get(4)?,
            provider: row.get(5)?,
            mode: row.get(6)?,
            created_at: row.get(7)?,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn detail(conn: &Connection, run_id: i64) -> LyraResult<ComposerRunDetail> {
    let mut stmt = conn.prepare(
        "SELECT id, prompt, action, active_role, summary, provider, mode, response_json, created_at
         FROM composer_runs
         WHERE id = ?1",
    )?;
    stmt.query_row(params![run_id], |row| {
        let response_json: String = row.get(7)?;
        let response =
            serde_json::from_str::<ComposerResponse>(&response_json).map_err(|error| {
                rusqlite::Error::FromSqlConversionFailure(
                    7,
                    rusqlite::types::Type::Text,
                    Box::new(error),
                )
            })?;
        Ok(ComposerRunDetail {
            record: ComposerRunRecord {
                id: row.get(0)?,
                prompt: row.get(1)?,
                action: row.get(2)?,
                active_role: row.get(3)?,
                summary: row.get(4)?,
                provider: row.get(5)?,
                mode: row.get(6)?,
                created_at: row.get(8)?,
            },
            response,
        })
    })
    .map_err(|error| match error {
        rusqlite::Error::QueryReturnedNoRows => LyraError::NotFound("composer run"),
        other => other.into(),
    })
}

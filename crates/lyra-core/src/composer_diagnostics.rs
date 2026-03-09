use chrono::Utc;
use rusqlite::{params, Connection};
use serde_json::Value;

use crate::commands::ComposerDiagnosticEntry;
use crate::errors::LyraResult;

pub struct ComposerDiagnosticWrite {
    pub level: String,
    pub event_type: String,
    pub prompt: String,
    pub action: Option<String>,
    pub provider: String,
    pub mode: String,
    pub message: String,
    pub payload: Option<Value>,
}

pub fn record_event(conn: &Connection, entry: ComposerDiagnosticWrite) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO composer_diagnostics (
            level, event_type, prompt, action, provider, mode, message, payload_json, created_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
        params![
            entry.level,
            entry.event_type,
            entry.prompt,
            entry.action,
            entry.provider,
            entry.mode,
            entry.message,
            entry.payload.map(|value| value.to_string()),
            Utc::now().to_rfc3339(),
        ],
    )?;
    Ok(())
}

pub fn recent(conn: &Connection, limit: usize) -> LyraResult<Vec<ComposerDiagnosticEntry>> {
    let mut stmt = conn.prepare(
        "SELECT id, level, event_type, prompt, action, provider, mode, message, payload_json, created_at
         FROM composer_diagnostics
         ORDER BY created_at DESC
         LIMIT ?1",
    )?;
    let rows = stmt.query_map(params![limit as i64], |row| {
        Ok(ComposerDiagnosticEntry {
            id: row.get(0)?,
            level: row.get(1)?,
            event_type: row.get(2)?,
            prompt: row.get(3)?,
            action: row.get(4)?,
            provider: row.get(5)?,
            mode: row.get(6)?,
            message: row.get(7)?,
            payload_json: row.get(8)?,
            created_at: row.get(9)?,
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

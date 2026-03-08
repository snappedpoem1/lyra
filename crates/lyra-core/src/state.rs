use rusqlite::{params, Connection, OptionalExtension};

use crate::commands::{PlaybackState, SettingsPayload};
use crate::errors::LyraResult;

#[derive(Clone, Debug)]
pub struct SessionSnapshot {
    pub playback: PlaybackState,
}

pub fn load_settings(conn: &Connection) -> LyraResult<SettingsPayload> {
    let payload = conn
        .query_row(
            "SELECT value_json FROM settings WHERE key = 'app'",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    match payload {
        Some(value) => Ok(serde_json::from_str(&value)?),
        None => {
            let defaults = SettingsPayload::default();
            save_settings(conn, &defaults)?;
            Ok(defaults)
        }
    }
}

pub fn save_settings(conn: &Connection, settings: &SettingsPayload) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO settings (key, value_json) VALUES ('app', ?1)
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
        params![serde_json::to_string(settings)?],
    )?;
    Ok(())
}

pub fn load_playback_state(conn: &Connection) -> LyraResult<PlaybackState> {
    let payload = conn
        .query_row(
            "SELECT value_json FROM session_state WHERE key = 'playback'",
            [],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    match payload {
        Some(value) => Ok(serde_json::from_str(&value)?),
        None => {
            let defaults = PlaybackState {
                status: "idle".to_string(),
                current_track_id: None,
                current_track: None,
                queue_index: 0,
                position_seconds: 0.0,
                duration_seconds: 0.0,
                volume: 0.82,
                shuffle: false,
                repeat_mode: "off".to_string(),
                seek_supported: false,
            };
            save_playback_state(conn, &defaults)?;
            Ok(defaults)
        }
    }
}

pub fn save_playback_state(conn: &Connection, playback: &PlaybackState) -> LyraResult<()> {
    conn.execute(
        "INSERT INTO session_state (key, value_json) VALUES ('playback', ?1)
         ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
        params![serde_json::to_string(playback)?],
    )?;
    Ok(())
}

pub fn load_session_state(conn: &Connection) -> LyraResult<SessionSnapshot> {
    Ok(SessionSnapshot {
        playback: load_playback_state(conn)?,
    })
}

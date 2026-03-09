use thiserror::Error;

pub type LyraResult<T> = Result<T, LyraError>;

#[derive(Debug, Error)]
pub enum LyraError {
    #[error("database error: {0}")]
    Db(#[from] rusqlite::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("dotenv parse error: {0}")]
    DotEnv(#[from] dotenvy::Error),
    #[error("{0} not found")]
    NotFound(&'static str),
    #[error("{0}")]
    InvalidInput(&'static str),
    #[error("{0}")]
    Message(String),
    #[error("playback backend unavailable")]
    PlaybackUnavailable,
    #[error("seek is not supported in the current playback engine")]
    SeekUnsupported,
    #[error("shared state lock poisoned")]
    LockPoisoned,
}

/// Automatic acquisition queue execution on app boot.
///
/// This module provides status checking for the automatic acquisition process:
/// - Detects if acquisition queue has pending items on app startup
/// - Enables signaling to the UI about auto-execution status
/// - The actual queue processing is delegated to the existing acquisition_worker
///   which is spawned by LyraCore and runs in a background thread

use rusqlite::Connection;

use crate::errors::LyraResult;

/// Queue for automatic execution on boot
pub struct AcquisitionAutoExecutor {
    pub enabled: bool,
}

impl AcquisitionAutoExecutor {
    /// Creates a new executor with default settings
    pub fn new() -> Self {
        AcquisitionAutoExecutor { enabled: true }
    }

    /// Checks if acquisition queue has pending items
    pub fn queue_has_items(conn: &Connection) -> LyraResult<bool> {
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM acquisition_queue WHERE status NOT IN ('completed', 'failed')",
            [],
            |row| row.get(0),
        )?;
        Ok(count > 0)
    }
}

impl Default for AcquisitionAutoExecutor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_executor_creation() {
        let executor = AcquisitionAutoExecutor::new();
        assert!(executor.enabled);
    }

    #[test]
    fn test_default_executor() {
        let executor: AcquisitionAutoExecutor = Default::default();
        assert!(executor.enabled);
    }
}

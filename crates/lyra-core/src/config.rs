use std::fs;
use std::path::PathBuf;

use crate::errors::LyraResult;

#[derive(Clone, Debug)]
pub struct AppPaths {
    pub app_data_dir: PathBuf,
    pub db_path: PathBuf,
    pub logs_dir: PathBuf,
}

impl AppPaths {
    pub fn new(app_data_dir: PathBuf) -> LyraResult<Self> {
        let db_dir = app_data_dir.join("db");
        let logs_dir = app_data_dir.join("logs");
        fs::create_dir_all(&db_dir)?;
        fs::create_dir_all(&logs_dir)?;
        Ok(Self {
            app_data_dir,
            db_path: db_dir.join("lyra.db"),
            logs_dir,
        })
    }
}

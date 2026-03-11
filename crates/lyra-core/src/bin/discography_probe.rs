use std::env;
use std::path::{Path, PathBuf};

use rusqlite::Connection;

use lyra_core::LyraCore;

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProbeArgs {
    app_data_dir: PathBuf,
    library_root: PathBuf,
    artists: Vec<String>,
    limit_albums: Option<usize>,
    reset_acquisition_state: bool,
    show_help: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct AcquisitionResetSummary {
    queue_items: i64,
    plans: i64,
    plan_items: i64,
    cached_tracks: i64,
}

fn default_app_data_dir() -> Result<PathBuf, String> {
    env::var("APPDATA")
        .map(|value| PathBuf::from(value).join("com.lyra.player"))
        .map_err(|_| "APPDATA is not set; pass --app-data-dir explicitly.".to_string())
}

fn default_library_root() -> PathBuf {
    PathBuf::from(r"A:\Music")
}

fn normalize_path(path: &PathBuf) -> String {
    path.to_string_lossy()
        .replace('/', "\\")
        .to_ascii_lowercase()
}

fn usage() -> &'static str {
    "usage: cargo run -p lyra-core --bin discography_probe -- [--app-data-dir PATH] [--root PATH] [--limit-albums N] [--reset-acquisition-state] \"Artist One\" \"Artist Two\""
}

fn parse_args_from<I, T>(args: I) -> Result<ProbeArgs, String>
where
    I: IntoIterator<Item = T>,
    T: Into<String>,
{
    let mut app_data_dir: Option<PathBuf> = None;
    let mut library_root = default_library_root();
    let mut artists: Vec<String> = Vec::new();
    let mut limit_albums = None;
    let mut reset_acquisition_state = false;
    let mut show_help = false;

    let mut args = args.into_iter().map(Into::into);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--help" | "-h" => {
                show_help = true;
            }
            "--app-data-dir" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--app-data-dir requires a path".to_string())?;
                app_data_dir = Some(PathBuf::from(value));
            }
            "--root" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--root requires a path".to_string())?;
                library_root = PathBuf::from(value);
            }
            "--limit-albums" => {
                let value = args
                    .next()
                    .ok_or_else(|| "--limit-albums requires a positive integer".to_string())?;
                let parsed = value
                    .parse::<usize>()
                    .map_err(|_| "--limit-albums requires a positive integer".to_string())?;
                if parsed == 0 {
                    return Err("--limit-albums must be greater than zero".to_string());
                }
                limit_albums = Some(parsed);
            }
            "--reset-acquisition-state" => {
                reset_acquisition_state = true;
            }
            _ if arg.starts_with('-') => {
                return Err(format!("unknown option: {arg}\n{}", usage()));
            }
            _ => artists.push(arg),
        }
    }

    if !show_help && artists.is_empty() {
        return Err(usage().to_string());
    }

    let app_data_dir = if let Some(app_data_dir) = app_data_dir {
        app_data_dir
    } else if show_help {
        PathBuf::new()
    } else {
        default_app_data_dir()?
    };

    Ok(ProbeArgs {
        app_data_dir,
        library_root,
        artists,
        limit_albums,
        reset_acquisition_state,
        show_help,
    })
}

fn parse_args() -> Result<ProbeArgs, String> {
    parse_args_from(env::args().skip(1))
}

fn app_db_path(app_data_dir: &Path) -> PathBuf {
    app_data_dir.join("db").join("lyra.db")
}

fn count_rows(conn: &Connection, table: &str, where_clause: Option<&str>) -> Result<i64, String> {
    let sql = match where_clause {
        Some(where_clause) => format!("SELECT COUNT(*) FROM {table} WHERE {where_clause}"),
        None => format!("SELECT COUNT(*) FROM {table}"),
    };
    conn.query_row(&sql, [], |row| row.get(0))
        .map_err(|error| format!("failed to count {table}: {error}"))
}

fn reset_acquisition_state(app_data_dir: &Path) -> Result<AcquisitionResetSummary, String> {
    let db_path = app_db_path(app_data_dir);
    let mut conn = Connection::open(&db_path)
        .map_err(|error| format!("failed to open {}: {error}", db_path.display()))?;
    let summary = AcquisitionResetSummary {
        queue_items: count_rows(&conn, "acquisition_queue", None)?,
        plans: count_rows(&conn, "acquisition_plans", None)?,
        plan_items: count_rows(&conn, "acquisition_plan_items", None)?,
        cached_tracks: count_rows(
            &conn,
            "provider_catalog_tracks",
            Some("source_kind = 'acquisition'"),
        )?,
    };
    let tx = conn
        .transaction()
        .map_err(|error| format!("failed to begin acquisition reset transaction: {error}"))?;
    tx.execute("DELETE FROM acquisition_plan_items", [])
        .map_err(|error| format!("failed to clear acquisition_plan_items: {error}"))?;
    tx.execute("DELETE FROM acquisition_plans", [])
        .map_err(|error| format!("failed to clear acquisition_plans: {error}"))?;
    tx.execute("DELETE FROM acquisition_queue", [])
        .map_err(|error| format!("failed to clear acquisition_queue: {error}"))?;
    tx.execute(
        "DELETE FROM provider_catalog_tracks WHERE source_kind = 'acquisition'",
        [],
    )
    .map_err(|error| {
        format!("failed to clear provider_catalog_tracks acquisition cache: {error}")
    })?;
    tx.commit()
        .map_err(|error| format!("failed to commit acquisition reset transaction: {error}"))?;
    Ok(summary)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = parse_args()?;
    if args.show_help {
        println!("Cassette discography probe");
        println!("{}", usage());
        println!(
            "options: --reset-acquisition-state clears acquisition queue/plans and acquisition-only provider catalog cache before probing"
        );
        return Ok(());
    }
    if args.reset_acquisition_state {
        let cleared = reset_acquisition_state(&args.app_data_dir)?;
        println!(
            "reset_acquisition_state queue_items={} plans={} plan_items={} cached_tracks={}",
            cleared.queue_items, cleared.plans, cleared.plan_items, cleared.cached_tracks
        );
    }

    let app_data_dir = args.app_data_dir;
    let library_root = args.library_root;
    let limit_albums = args.limit_albums;
    let artists = args.artists;
    let core = LyraCore::new(app_data_dir.clone())?;

    if !library_root.exists() {
        std::fs::create_dir_all(&library_root)?;
    }

    let existing_roots = core.list_library_roots()?;
    let wanted_root = normalize_path(&library_root);
    if !existing_roots
        .iter()
        .map(|root| normalize_path(&PathBuf::from(&root.path)))
        .any(|root| root == wanted_root)
    {
        let _ = core.add_library_root(library_root.display().to_string())?;
    }

    let overview = core.get_library_overview()?;
    let preflight = core.acquisition_preflight()?;

    println!("Cassette discography probe");
    println!("app_data_dir={}", app_data_dir.display());
    println!("library_root={}", library_root.display());
    println!(
        "library_overview tracks={} artists={} albums={} roots={}",
        overview.track_count, overview.artist_count, overview.album_count, overview.root_count
    );
    println!(
        "acquisition_preflight ready={} downloader_available={} disk_ok={} library_root_ok={} output_path_ok={}",
        preflight.ready,
        preflight.downloader_available,
        preflight.disk_ok,
        preflight.library_root_ok,
        preflight.output_path_ok
    );
    for check in &preflight.checks {
        println!("check {} [{}] {}", check.key, check.status, check.detail);
    }

    for artist in artists {
        let plan = core.plan_discography_acquisition(
            artist.clone(),
            Some("discography_probe".to_string()),
            None,
            limit_albums,
        )?;
        println!(
            "artist={} plan_status={} total_items={} queued_items={} blocked_items={}",
            artist,
            plan.plan.status,
            plan.plan.total_items,
            plan.plan.queued_items,
            plan.plan.blocked_items
        );
        for item in plan.items.iter().take(8) {
            println!(
                "  item status={} artist={} title={} album={}",
                item.status,
                item.artist,
                item.title,
                item.album.as_deref().unwrap_or("")
            );
        }
        for item in plan
            .items
            .iter()
            .filter(|item| item.status != "queued")
            .take(5)
        {
            println!(
                "  blocked status={} artist={} title={} album={} reason={}",
                item.status,
                item.artist,
                item.title,
                item.album.as_deref().unwrap_or(""),
                item.evidence_summary
            );
        }
    }

    let queue = core.get_acquisition_queue(None)?;
    println!("queue_count={}", queue.len());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{parse_args_from, AcquisitionResetSummary};

    #[test]
    fn parse_args_supports_help_without_artist_names() {
        let args = parse_args_from(["--help"]).expect("args");
        assert!(args.show_help);
        assert!(args.artists.is_empty());
    }

    #[test]
    fn parse_args_rejects_unknown_flags() {
        let error = parse_args_from(["--wat"]).expect_err("unknown flag should fail");
        assert!(error.contains("unknown option"));
    }

    #[test]
    fn parse_args_accepts_reset_and_limit() {
        let args = parse_args_from([
            "--reset-acquisition-state",
            "--limit-albums",
            "3",
            "Coheed and Cambria",
        ])
        .expect("args");
        assert!(args.reset_acquisition_state);
        assert_eq!(args.limit_albums, Some(3));
        assert_eq!(args.artists, vec!["Coheed and Cambria"]);
    }

    #[test]
    fn reset_summary_is_copyable_for_logging() {
        let summary = AcquisitionResetSummary {
            queue_items: 1,
            plans: 2,
            plan_items: 3,
            cached_tracks: 4,
        };
        assert_eq!(summary.cached_tracks, 4);
    }
}

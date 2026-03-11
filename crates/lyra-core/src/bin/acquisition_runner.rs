/// Acquisition queue runner — processes queued items through the native waterfall.
///
/// Usage: cargo run -p lyra-core --bin acquisition_runner -- [--limit N] [--dry-run]
use std::env;
use std::path::PathBuf;

use lyra_core::LyraCore;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut limit: usize = 5;
    let mut dry_run = false;

    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--limit" => {
                if let Some(value) = iter.next() {
                    limit = value.parse().unwrap_or(5);
                }
            }
            "--dry-run" => dry_run = true,
            "--help" | "-h" => {
                println!("usage: acquisition_runner [--limit N] [--dry-run]");
                println!("  --limit N   Process at most N items (default: 5)");
                println!("  --dry-run   Show what would be processed without downloading");
                return Ok(());
            }
            _ => {}
        }
    }

    let app_data_dir = env::var("APPDATA")
        .map(|value| PathBuf::from(value).join("com.lyra.player"))
        .map_err(|_| "APPDATA not set")?;

    let core = LyraCore::new(app_data_dir)?;
    let preflight = core.acquisition_preflight()?;
    println!(
        "preflight ready={} downloader_available={} disk_ok={} library_root_ok={}",
        preflight.ready, preflight.downloader_available, preflight.disk_ok, preflight.library_root_ok
    );
    for check in &preflight.checks {
        println!("  check {} [{}] {}", check.key, check.status, check.detail);
    }
    if !preflight.ready {
        println!("preflight not ready, aborting");
        return Ok(());
    }

    let queue = core.get_acquisition_queue(None)?;
    let queued_count = queue.iter().filter(|item| item.status == "queued").count();
    println!("queue total={} queued={} limit={}", queue.len(), queued_count, limit);

    if dry_run {
        println!("dry-run mode: showing first {} queued items", limit);
        for item in queue.iter().filter(|item| item.status == "queued").take(limit) {
            println!(
                "  id={} artist={} title={} album={}",
                item.id,
                item.artist,
                item.title,
                item.album.as_deref().unwrap_or("")
            );
        }
        return Ok(());
    }

    let mut processed = 0;
    let mut success = 0;
    let mut failed = 0;
    for i in 0..limit {
        println!("--- processing item {}/{} ---", i + 1, limit);
        let current_queue = core.get_acquisition_queue(None)?;
        let current_item_id = current_queue
            .iter()
            .find(|item| item.status == "queued")
            .map(|item| item.id);
        match core.process_acquisition_queue_with_callback(move |queue_id| {
            eprintln!("[lifecycle] queue_id={queue_id} updated");
        }) {
            Ok(true) => {
                processed += 1;
                if let Some(item_id) = current_item_id {
                    let updated_queue = core.get_acquisition_queue(None).ok();
                    if let Some(items) = updated_queue {
                        if let Some(item) = items.iter().find(|item| item.id == item_id) {
                            if item.status == "completed" {
                                success += 1;
                                println!(
                                    "  COMPLETED id={} artist={} title={} provider={} tier={} path={}",
                                    item.id,
                                    item.artist,
                                    item.title,
                                    item.selected_provider.as_deref().unwrap_or("?"),
                                    item.selected_tier.as_deref().unwrap_or("?"),
                                    item.output_path.as_deref().unwrap_or("?")
                                );
                            } else if item.status == "failed" {
                                failed += 1;
                                println!(
                                    "  FAILED id={} artist={} title={} provider={} tier={} reason={}",
                                    item.id,
                                    item.artist,
                                    item.title,
                                    item.selected_provider.as_deref().unwrap_or("?"),
                                    item.selected_tier.as_deref().unwrap_or("?"),
                                    item.failure_reason.as_deref().unwrap_or("unknown")
                                );
                            } else {
                                println!(
                                    "  UPDATED id={} artist={} title={} status={}",
                                    item.id,
                                    item.artist,
                                    item.title,
                                    item.status
                                );
                            }
                        }
                    }
                }
            }
            Ok(false) => {
                println!("  queue empty, stopping");
                break;
            }
            Err(error) => {
                failed += 1;
                println!("  ERROR: {error}");
            }
        }
    }

    println!(
        "\nacquisition_runner done: processed={} success={} failed={}",
        processed, success, failed
    );
    Ok(())
}

// Test the diagnostics module
use lyra_core::LyraCore;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app_data_dir = PathBuf::from("C:\\MusicOracle");
    let lyra = LyraCore::new(app_data_dir)?;

    println!("Running system diagnostics...\n");

    let report = lyra.run_diagnostics()?;

    println!("Overall Status: {:?}", report.status);
    println!("\nStatistics:");
    println!("  Total Tracks: {}", report.stats.total_tracks);
    println!("  Total Playlists: {}", report.stats.total_playlists);
    println!("  Library Roots: {}", report.stats.library_roots);
    println!(
        "  Pending Acquisitions: {}",
        report.stats.pending_acquisitions
    );
    println!("  Enriched Tracks: {}", report.stats.enriched_tracks);
    println!("  Liked Tracks: {}", report.stats.liked_tracks);

    println!("\nComponent Health:");
    for (component, check) in &report.checks {
        let status_str = match check.status.as_str() {
            "ok" => "✅ OK",
            "warning" => "⚠️  WARNING",
            "error" => "❌ ERROR",
            "not_configured" => "⚙️  NOT CONFIGURED",
            _ => "❓ UNKNOWN",
        };
        println!("  {} - {}: {}", status_str, component, check.message);
        if let Some(ref error) = check.error {
            println!("      Error: {}", error);
        }
    }

    Ok(())
}

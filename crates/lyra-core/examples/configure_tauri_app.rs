// Configure library root in Tauri app database
use lyra_core::LyraCore;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Use the Tauri app data directory
    let app_data_dir = PathBuf::from("C:\\Users\\Admin\\AppData\\Roaming\\com.lyra.player");
    let lyra = LyraCore::new(app_data_dir)?;
    
    println!("Configuring Tauri app library...\n");
    
    // Check current roots
    let roots = lyra.list_library_roots()?;
    
    if roots.is_empty() {
        println!("No library roots found. Adding A:\\Music...");
        lyra.add_library_root("A:\\Music".to_string())?;
        println!("✅ Added library root: A:\\Music");
    } else {
        println!("Found {} existing library root(s):", roots.len());
        for root in &roots {
            println!("  - {}", root.path);
        }
    }
    
    // Run diagnostics
    println!("\nRunning diagnostics...");
    let report = lyra.run_diagnostics()?;
    
    println!("\n📊 System Status: {}", report.status);
    println!("   Total Tracks: {}", report.stats.total_tracks);
    println!("   Total Playlists: {}", report.stats.total_playlists);
    println!("   Library Roots: {}", report.stats.library_roots);
    
    // Show sample tracks
    println!("\n🎵 Sample Tracks:");
    let tracks = lyra.list_tracks(None)?;
    for (i, track) in tracks.iter().take(10).enumerate() {
        println!("   {}. {} - {} ({})", 
            i + 1, 
            track.artist, 
            track.title,
            track.album
        );
    }
    
    println!("\n✅ Tauri app database configured!");
    println!("➡️  Now restart the Tauri app to see your library");
    
    Ok(())
}

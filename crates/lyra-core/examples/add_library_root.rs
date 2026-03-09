// Add A:\Music as library root
use lyra_core::LyraCore;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app_data_dir = PathBuf::from("C:\\MusicOracle");
    let lyra = LyraCore::new(app_data_dir)?;

    println!("Adding library root...\n");

    let music_root = "A:\\Music";

    // Check if path exists
    if !std::path::Path::new(music_root).exists() {
        eprintln!("❌ Path does not exist: {}", music_root);
        return Ok(());
    }

    // Add library root
    lyra.add_library_root(music_root.to_string())?;
    println!("✅ Added library root: {}", music_root);

    // List all roots
    println!("\nConfigured library roots:");
    let roots = lyra.list_library_roots()?;
    for root in &roots {
        let exists = std::path::Path::new(&root.path).exists();
        let status = if exists { "✅" } else { "❌" };
        println!("  {} {} (added: {})", status, root.path, root.added_at);
    }

    println!("\n✅ Library configured successfully!");

    Ok(())
}

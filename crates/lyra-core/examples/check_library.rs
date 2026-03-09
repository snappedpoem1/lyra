// Check and display library roots
use lyra_core::LyraCore;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let app_data_dir = PathBuf::from("C:\\MusicOracle");
    let lyra = LyraCore::new(app_data_dir)?;

    println!("Library Configuration:\n");

    let roots = lyra.list_library_roots()?;

    if roots.is_empty() {
        println!("❌ No library roots configured!");
        println!("\nExpected library root: C:\\MusicOracle\\downloads");
    } else {
        println!("Found {} library root(s):", roots.len());
        for root in &roots {
            let exists = std::path::Path::new(&root.path).exists();
            let status = if exists { "✅ EXISTS" } else { "❌ MISSING" };
            println!("  {} - {} (added: {})", status, root.path, root.added_at);
        }
    }

    Ok(())
}

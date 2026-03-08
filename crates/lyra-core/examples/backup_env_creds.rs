/// One-shot CLI: reads .env and saves all credential values to OS keychain.
/// Usage: cargo run --example backup_env_creds -- [path/to/.env]
fn main() {
    let env_path = std::env::args().nth(1).unwrap_or_else(|| "C:\\MusicOracle\\.env".to_string());
    println!("Scanning: {env_path}");
    match lyra_core::providers::backup_env_to_keychain(&env_path) {
        Ok((saved, skipped)) => {
            println!("Done. Saved: {saved} credentials, skipped: {skipped} non-credential entries.");
        }
        Err(e) => {
            eprintln!("Error: {e}");
            std::process::exit(1);
        }
    }
}

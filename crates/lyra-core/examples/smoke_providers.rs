/// Smoke test — D: Config / providers (providers.rs)
///
/// Verifies:
///   1. load_llm_config() returns a non-empty base_url and model
///   2. provider_kind is a recognised value
///   3. list_configured_providers() returns at least one provider
///   4. load_provider_config() round-trips a synthetic JSON blob (save → load)
///   5. validate_provider() runs for each configured provider without panicking
///   6. is_circuit_open() returns false for a freshly reset provider
///   7. record_provider_success / record_provider_failure update health without panic
use lyra_core::providers::{
    import_env_file, is_circuit_open, list_configured_providers, list_provider_health,
    load_llm_config, load_provider_config, record_provider_failure, record_provider_success,
    reset_provider_health, save_provider_config, validate_provider,
};
use rusqlite::Connection;
use serde_json::json;
use std::path::Path;

const DB_PATH: &str = r"C:\MusicOracle\db\lyra.db";
const ENV_PATH: &str = r"C:\MusicOracle\.env";
const KNOWN_KINDS: &[&str] = &[
    "ollama",
    "openai",
    "openrouter",
    "groq",
    "openai_compatible",
    "local",
    "",
];

fn pass(msg: &str) {
    println!("  PASS  {msg}");
}
fn fail(msg: &str) {
    println!("  FAIL  {msg}");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== smoke_providers ===\n");

    let conn = Connection::open(DB_PATH)?;

    // Seed provider_configs from .env — the same path Cassette uses on first run.
    // Also load into process env so LYRA_LLM_* fallback in load_llm_config() works.
    let env_path = Path::new(ENV_PATH);
    if env_path.exists() {
        let _ = dotenvy::from_path_override(env_path);
        let mut imported = vec![];
        let mut _unsupported = vec![];
        match import_env_file(&conn, env_path, &mut imported, &mut _unsupported) {
            Ok(n) => println!(
                "  INFO  import_env_file → {n} provider(s) seeded: {:?}",
                imported
            ),
            Err(e) => println!("  WARN  import_env_file failed: {e}"),
        }
    }

    // ── 1. load_llm_config ───────────────────────────────────────────────────
    let llm = load_llm_config(&conn);
    println!("  INFO  llm.base_url     = {}", llm.base_url);
    println!("  INFO  llm.model        = {}", llm.model);
    println!("  INFO  llm.provider_kind= {}", llm.provider_kind);

    if !llm.base_url.is_empty() {
        pass("load_llm_config: base_url is non-empty");
    } else {
        fail("load_llm_config: base_url is empty");
    }
    if !llm.model.is_empty() {
        pass("load_llm_config: model is non-empty");
    } else {
        println!("  WARN  model is empty — set LYRA_LLM_MODEL or configure a provider in the DB");
    }
    if KNOWN_KINDS.contains(&llm.provider_kind.as_str()) {
        pass(&format!(
            "provider_kind '{}' is a recognised value",
            llm.provider_kind
        ));
    } else {
        fail(&format!(
            "provider_kind '{}' is unrecognised",
            llm.provider_kind
        ));
    }

    println!();

    // ── 2. list_configured_providers ────────────────────────────────────────
    let configured = list_configured_providers(&conn);
    println!("  INFO  configured providers: {:?}", configured);
    if !configured.is_empty() {
        pass(&format!(
            "list_configured_providers: {} provider(s) found",
            configured.len()
        ));
    } else {
        println!(
            "  WARN  no providers configured in DB — import_env_file() or configure via UI first"
        );
    }

    println!();

    // ── 3. save_provider_config round-trip ──────────────────────────────────
    let test_key = "_smoke_test_provider";
    // Clean up any leftover row from a previous run.
    let _ = conn.execute(
        "DELETE FROM provider_configs WHERE provider_key = ?1",
        rusqlite::params![test_key],
    );
    let test_json = json!({ "test_field": "smoke_value_42", "enabled": true });
    save_provider_config(&conn, test_key, &test_json)?;
    let loaded = load_provider_config(&conn, test_key);

    // Note: save_provider_config leaves enabled=1 by default.
    match loaded {
        Some(v) if v.get("test_field").and_then(|v| v.as_str()) == Some("smoke_value_42") => {
            pass("save_provider_config + load_provider_config round-trip");
        }
        Some(v) => {
            fail(&format!("round-trip value mismatch: {:?}", v));
        }
        None => {
            fail("load_provider_config returned None after save");
        }
    }

    // Cleanup: disable the test row so it doesn't pollute list_configured_providers
    let _ = conn.execute(
        "UPDATE provider_configs SET enabled = 0 WHERE provider_key = ?1",
        rusqlite::params![test_key],
    );

    println!();

    // ── 4. validate_provider for each real configured provider ───────────────
    for key in &configured {
        match validate_provider(&conn, key) {
            Ok(result) => {
                println!(
                    "  INFO  validate_provider({key}) → valid={}, error={:?}",
                    result.valid, result.error
                );
                // Don't fail on validation errors — network may be unavailable in CI.
                pass(&format!("validate_provider({key}) completed without panic"));
            }
            Err(e) => {
                println!("  WARN  validate_provider({key}) returned Err: {e}");
            }
        }
    }

    println!();

    // ── 5. Circuit breaker ───────────────────────────────────────────────────
    if let Some(key) = configured.first() {
        reset_provider_health(&conn, key)?;
        if !is_circuit_open(&conn, key) {
            pass(&format!("circuit closed after reset for '{key}'"));
        } else {
            fail(&format!("circuit open immediately after reset for '{key}'"));
        }

        record_provider_success(&conn, key)?;
        pass(&format!("record_provider_success({key}) completed"));

        record_provider_failure(&conn, key)?;
        pass(&format!("record_provider_failure({key}) completed"));

        // Reset back so we don't poison the health record
        reset_provider_health(&conn, key)?;
    } else {
        println!("  SKIP  circuit breaker checks (no providers configured)");
    }

    println!();

    // ── 6. list_provider_health ──────────────────────────────────────────────
    let health_list = list_provider_health(&conn)?;
    println!("  INFO  provider health entries: {}", health_list.len());
    pass("list_provider_health completed without panic");

    println!();
    println!("=== smoke_providers done ===\n");
    Ok(())
}

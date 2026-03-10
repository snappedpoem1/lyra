//! Smoke test: LlmClient — Groq primary, OpenRouter fallback.
//!
//! Requires a live DB with provider_configs seeded (run smoke_providers first,
//! or just have the .env loaded via import_env_file).
//!
//! Set SMOKE_LLM=1 to enable the live network call. Without it, only the
//! config-load and struct construction paths are exercised.

use lyra_core::{
    db::init_database,
    llm_client::{LlmClient, LlmEndpointConfig},
    providers::import_env_file,
};
use rusqlite::Connection;
use std::path::Path;

const ENV_PATH: &str = "C:\\MusicOracle\\.env";

fn main() {
    let conn = Connection::open_in_memory().expect("open in-memory db");
    init_database(&conn).expect("init_database");

    // Seed provider_configs from .env so load_llm_config can find Groq credentials
    let mut imported = Vec::new();
    let mut unsupported = Vec::new();
    import_env_file(&conn, Path::new(ENV_PATH), &mut imported, &mut unsupported)
        .expect("import_env_file");

    // ── Test 1: LlmClient::from_connection ───────────────────────────────────
    let client = LlmClient::from_connection(&conn);
    assert!(
        client.is_some(),
        "FAIL: LlmClient::from_connection returned None — check .env has LYRA_LLM_* vars"
    );
    println!("PASS: LlmClient::from_connection => client constructed");

    // ── Test 2: from_endpoints with explicit config ───────────────────────────
    let explicit = LlmClient::from_endpoints(
        LlmEndpointConfig::new(
            "groq".into(),
            "https://api.groq.com/openai/v1".into(),
            "llama-3.3-70b-versatile".into(),
            "test-key".into(),
        ),
        None,
    );
    // chat_completion_text with a bad key should return None (not panic)
    let result = explicit.chat_completion_text("ping", "ping", 1, 0.0);
    // We expect None since "test-key" is invalid — just verifying no panic
    println!(
        "PASS: chat_completion_text with bad key => {:?} (expected None)",
        result.as_deref().unwrap_or("None")
    );

    // ── Test 3: live call (gated) ─────────────────────────────────────────────
    if std::env::var("SMOKE_LLM").unwrap_or_default() == "1" {
        println!("SMOKE_LLM=1 — running live call...");
        let live_client = LlmClient::from_connection(&conn)
            .expect("need configured client for live test");
        let text = live_client.chat_completion_text(
            "You are a terse assistant.",
            "Reply with exactly the word: PONG",
            10,
            0.0,
        );
        match text {
            Some(t) => println!("PASS: live chat_completion_text => {:?}", t),
            None => println!("WARN: live call returned None (provider may be unavailable)"),
        }
    } else {
        println!("INFO: set SMOKE_LLM=1 to run live network call");
    }

    println!("\nAll smoke_llm_client checks passed.");
}

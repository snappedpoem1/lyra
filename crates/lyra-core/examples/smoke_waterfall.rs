/// Smoke test — B: Acquisition waterfall (waterfall.rs)
///
/// Verifies:
///   1. is_junk() correctly identifies karaoke / tribute / lullaby junk
///   2. is_junk() does NOT false-positive on real artists/tracks
///   3. "A Static Lullaby" is NOT junk (artist named after the word, not junk pattern)
///   4. YtdlpTier::name() / tier_tag() return expected values
///   5. run_waterfall() with no tiers returns outcome.path = None
///   6. (Optional) Live yt-dlp test if SMOKE_YTDLP=1 is set
use lyra_core::commands::AcquisitionQueueItem;
use lyra_core::waterfall::{is_junk, run_waterfall, AcquisitionTier, YtdlpTier};

fn pass(msg: &str) {
    println!("  PASS  {msg}");
}
fn fail(msg: &str) {
    println!("  FAIL  {msg}");
}

fn fake_item(artist: &str, title: &str) -> AcquisitionQueueItem {
    AcquisitionQueueItem {
        id: 0,
        artist: artist.to_string(),
        title: title.to_string(),
        album: None,
        status: "pending".to_string(),
        queue_position: 0,
        priority_score: 1.0,
        source: None,
        added_at: "2026-01-01T00:00:00Z".to_string(),
        started_at: None,
        completed_at: None,
        failed_at: None,
        cancelled_at: None,
        error: None,
        status_message: None,
        failure_stage: None,
        failure_reason: None,
        failure_detail: None,
        retry_count: 0,
        selected_provider: None,
        selected_tier: None,
        worker_label: None,
        validation_confidence: None,
        validation_summary: None,
        target_root_id: None,
        target_root_path: None,
        output_path: None,
        downstream_track_id: None,
        scan_completed: false,
        organize_completed: false,
        index_completed: false,
        cancel_requested: false,
        lifecycle_stage: None,
        lifecycle_progress: None,
        lifecycle_note: None,
        updated_at: None,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== smoke_waterfall ===\n");

    // ── is_junk — must catch ────────────────────────────────────────────────
    let junk_cases = vec![
        (
            "Karaoke Hits",
            "Smells Like Teen Spirit",
            "karaoke in artist",
        ),
        (
            "Various Artists",
            "Smells Like Teen Spirit (Karaoke Version)",
            "karaoke in title",
        ),
        ("Tribute Band", "Enter Sandman", "tribute in artist"),
        (
            "Nursery Rhymes",
            "Twinkle Twinkle Lullaby Version",
            "lullaby version in title",
        ),
        ("SoundAlike", "Bohemian Rhapsody 8-bit", "8-bit in title"),
        (
            "Someone",
            "Happy Birthday (Music Box)",
            "music box in title",
        ),
        (
            "Studio All Stars",
            "Blinding Lights (Ringtone)",
            "ringtone in title",
        ),
    ];

    for (artist, title, label) in &junk_cases {
        if is_junk(artist, title) {
            pass(&format!(
                "caught junk [{label}]: \"{artist}\" - \"{title}\""
            ));
        } else {
            fail(&format!(
                "missed junk [{label}]: \"{artist}\" - \"{title}\""
            ));
        }
    }

    println!();

    // ── is_junk — must NOT catch ────────────────────────────────────────────
    let real_cases = vec![
        ("A Static Lullaby", "Toxic", "band named after lullaby"),
        ("Beck", "Loser", "normal track"),
        ("Kendrick Lamar", "HUMBLE.", "normal track"),
        ("Coheed and Cambria", "Welcome Home", "normal track"),
        ("Run The Jewels", "Legend Has It", "normal track"),
        (
            "Brand New",
            "Sic Transit Gloria...Glory Fades",
            "normal track",
        ),
        ("Massive Attack", "Teardrop", "normal track"),
    ];

    for (artist, title, label) in &real_cases {
        if !is_junk(artist, title) {
            pass(&format!(
                "no false-positive [{label}]: \"{artist}\" - \"{title}\""
            ));
        } else {
            fail(&format!(
                "false-positive! [{label}]: \"{artist}\" - \"{title}\""
            ));
        }
    }

    println!();

    // ── YtdlpTier metadata ──────────────────────────────────────────────────
    let tier = YtdlpTier::default();
    if tier.name() == "yt-dlp" {
        pass(&format!("YtdlpTier::name() = \"{}\"", tier.name()));
    } else {
        fail(&format!(
            "YtdlpTier::name() = \"{}\" (expected \"yt-dlp\")",
            tier.name()
        ));
    }
    if tier.tier_tag().starts_with('T') {
        pass(&format!("YtdlpTier::tier_tag() = \"{}\"", tier.tier_tag()));
    } else {
        fail(&format!(
            "YtdlpTier::tier_tag() = \"{}\" (expected T*)",
            tier.tier_tag()
        ));
    }

    println!();

    // ── run_waterfall with empty tier list → path is None, no provider ─────
    let tmp = std::env::temp_dir().join("smoke_waterfall_staging");
    std::fs::create_dir_all(&tmp)?;
    let item = fake_item("Beck", "E-Pro");
    let tiers: Vec<Box<dyn AcquisitionTier>> = vec![];
    let outcome = run_waterfall(&item, &tiers, &tmp);
    if outcome.path.is_none() && outcome.provider.is_none() {
        pass("empty tier list → no path, no provider (all skipped)");
    } else {
        fail(&format!(
            "expected empty outcome, got path={:?} provider={:?}",
            outcome.path, outcome.provider
        ));
    }

    println!();

    // ── Optional live yt-dlp test ───────────────────────────────────────────
    if std::env::var("SMOKE_YTDLP").as_deref() == Ok("1") {
        println!("  INFO  SMOKE_YTDLP=1 — running live yt-dlp acquisition test...");
        let live_tiers: Vec<Box<dyn AcquisitionTier>> = vec![Box::new(YtdlpTier::default())];
        let live_item = fake_item("Beck", "Loser");
        let live_staging = std::env::temp_dir().join("smoke_waterfall_live");
        std::fs::create_dir_all(&live_staging)?;
        let live_outcome = run_waterfall(&live_item, &live_tiers, &live_staging);
        if let Some(path) = live_outcome.path {
            pass(&format!(
                "yt-dlp acquired via tier {:?}: {}",
                live_outcome.tier,
                path.display()
            ));
            let _ = std::fs::remove_file(&path);
        } else if let Some(reason) = live_outcome.failure_reason {
            fail(&format!("yt-dlp failed: {reason}"));
        } else {
            println!("  WARN  yt-dlp skipped (binary not found or no result)");
        }
    } else {
        println!("  SKIP  live yt-dlp test (set SMOKE_YTDLP=1 to enable)");
    }

    println!();
    println!("=== smoke_waterfall done ===\n");
    Ok(())
}

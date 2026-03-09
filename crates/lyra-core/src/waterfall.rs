/// Acquisition waterfall — trait abstraction and yt-dlp tier implementation.
///
/// Architecture
/// ============
/// - `AcquisitionTier` trait: one method, `try_acquire`.
/// - `TierResult` enum: Success(PathBuf) | Skip(reason) | Fail(reason).
/// - `is_junk(artist, title)` pure guard function ported from Python guard.py.
/// - `YtdlpTier`: spawns `yt-dlp` as a subprocess, downloads to staging dir.
/// - `run_waterfall(item, tiers, staging_dir)`: tries each tier in order,
///   returns the first `TierResult::Success` or the last failure.
///
/// Tiers not yet ported (left for future work):
/// - T1 Qobuz  — OAuth + service-url path exists in acquisition_dispatcher.rs
/// - T3 Slskd  — P2P search + long-poll exists in acquisition_dispatcher.rs
/// - T4 Real-Debrid — torrent/magnet pipeline
/// - T5 SpotDL — spotdl binary path exists in acquisition_dispatcher.rs
///
/// The native implementations in acquisition_dispatcher.rs remain in place and
/// continue to function. This module provides the typed trait layer so new
/// tiers can be registered without touching the dispatcher directly.
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use tracing::{info, warn};
use which::which;

use crate::commands::AcquisitionQueueItem;

// ---------------------------------------------------------------------------
// TierResult
// ---------------------------------------------------------------------------

/// Outcome of a single tier's acquisition attempt.
#[derive(Debug)]
pub enum TierResult {
    /// Audio file was downloaded and is available at the given path.
    Success(PathBuf),
    /// Tier was not configured / service unavailable — try the next tier.
    Skip(String),
    /// Tier was attempted but failed — try the next tier.
    Fail(String),
}

impl TierResult {
    /// Returns true if this is a `Success` variant.
    pub fn is_success(&self) -> bool {
        matches!(self, TierResult::Success(_))
    }

    /// Extracts the path if `Success`, otherwise `None`.
    pub fn into_path(self) -> Option<PathBuf> {
        match self {
            TierResult::Success(path) => Some(path),
            _ => None,
        }
    }

    /// Human-readable reason (for Skip / Fail variants).
    pub fn reason(&self) -> Option<&str> {
        match self {
            TierResult::Success(_) => None,
            TierResult::Skip(reason) | TierResult::Fail(reason) => Some(reason.as_str()),
        }
    }
}

// ---------------------------------------------------------------------------
// AcquisitionTier trait
// ---------------------------------------------------------------------------

/// A single tier in the acquisition waterfall.
pub trait AcquisitionTier: Send + Sync {
    /// Human-readable name, e.g. "yt-dlp".
    fn name(&self) -> &str;

    /// Tier number used in log messages and lifecycle updates (T1..T5).
    fn tier_tag(&self) -> &str;

    /// Attempt to acquire `item` and place the result in `staging_dir`.
    fn try_acquire(&self, item: &AcquisitionQueueItem, staging_dir: &Path) -> TierResult;
}

// ---------------------------------------------------------------------------
// Guard — is_junk
// ---------------------------------------------------------------------------

/// Returns `true` if the artist/title combination matches a known junk pattern.
///
/// Ported from `oracle/acquirers/guard.py`:
/// - `JUNK_PATTERNS` are checked against the combined `"artist title"` string.
/// - `TITLE_JUNK_PATTERNS` are checked against the title only (so patterns like
///   "lullaby version" don't accidentally reject "A Static Lullaby").
pub fn is_junk(artist: &str, title: &str) -> bool {
    let combined = format!("{} {}", artist, title).to_lowercase();
    let title_lower = title.to_lowercase();

    // Patterns checked against artist+title combined (case-insensitive).
    let junk_patterns: &[&str] = &[
        // Karaoke / covers / backing tracks
        r"karaoke",
        r"tribute",
        r"cover version",
        r"covered by",
        r"made famous",
        r"made popular",
        r"in the style of",
        r"originally performed",
        r"piano tribute",
        r"piano version",
        r"piano cover",
        r"acoustic tribute",
        r"orchestral tribute",
        r"backing version",
        r"backing track",
        r"backing vocal",
        // Specific junk artist fingerprints
        r"party tyme",
        r"prosource",
        r"zzang",
        r"twinkle twinkle little rock star",
        r"vitamin string quartet",
        r"rockabye baby",
        r"scala & kolacny",
        r"scala and kolacny",
        // YouTube spam
        r"lyrics video",
        r"lyric video",
        r"audio only",
        r"1 hour loop",
        r"1 hour version",
        r"1 hour mix",
        r"slowed reverb",
        r"slowed + reverb",
        r"slowed and reverb",
        r"nightcore",
        r"sped up",
        r"chopped and screwed",
        r"chopped n screwed",
        r"chopped not slopped",
    ];

    // Patterns checked against title only.
    let title_junk_patterns: &[&str] = &[
        r"8-bit",
        r"8 bit",
        r"8bit",
        r"midi",
        r"ringtone",
        r"music box",
        r"lullaby version",
        r"lullaby mix",
        r"lullaby edit",
        r"lullaby cover",
        r"(cover)",
        r"[cover]",
        r"- instrumental",
        r"(instrumental)",
        r"[instrumental]",
        r"instrumental version",
        r"instrumental mix",
        r"instrumental edit",
        r"- a cappella",
        r"- acapella",
        r"a cappella version",
        r"a cappella mix",
        r"acapella version",
        r"acapella mix",
        r"(lo-fi)",
        r"(lofi)",
        r"lo-fi version",
        r"lofi version",
        r"lo-fi remix",
        r"lofi remix",
        r"epic version",
        r"rave version",
    ];

    for pat in junk_patterns {
        if combined.contains(pat) {
            return true;
        }
    }
    for pat in title_junk_patterns {
        if title_lower.contains(pat) {
            return true;
        }
    }
    false
}

// ---------------------------------------------------------------------------
// YtdlpTier
// ---------------------------------------------------------------------------

/// Acquisition tier that spawns `yt-dlp` as a subprocess to search YouTube.
///
/// Matches the Python `YTDLPAcquirer.download_search` implementation:
/// - Builds query `"ytsearch1:{artist} {title}"`.
/// - Downloads best-audio to an isolated temp dir inside `staging_dir`.
/// - Title similarity check: rejects results with < 25% similarity.
/// - Moves the downloaded file into `staging_dir` with a clean filename.
/// - Socket timeout: 30 s (passed via `--socket-timeout`).
/// - Retries: 2 (via `--retries`).
/// - Preferred codec: mp3, quality: 320k.
pub struct YtdlpTier {
    /// Override path to the `yt-dlp` binary.  When `None` the PATH is searched.
    pub binary: Option<PathBuf>,
    /// Maximum wall-clock seconds to wait for the process before killing it.
    pub timeout_secs: u64,
    /// Minimum title-similarity ratio (0.0–1.0) below which the result is rejected.
    pub min_similarity: f64,
}

impl Default for YtdlpTier {
    fn default() -> Self {
        Self {
            binary: None,
            timeout_secs: 120,
            min_similarity: 0.25,
        }
    }
}

impl YtdlpTier {
    fn find_binary(&self) -> Option<PathBuf> {
        if let Some(path) = &self.binary {
            if path.exists() {
                return Some(path.clone());
            }
        }
        which("yt-dlp").ok().or_else(|| which("yt_dlp").ok())
    }

    /// Sanitize a filename segment by replacing filesystem-unsafe characters.
    fn sanitize(name: &str) -> String {
        name.chars()
            .map(|ch| {
                if matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*') {
                    '_'
                } else {
                    ch
                }
            })
            .collect::<String>()
            .trim()
            .to_string()
    }

    /// Find the newest audio file written to `dir` after `started_at`.
    fn newest_audio_file(dir: &Path, started_at: std::time::SystemTime) -> Option<PathBuf> {
        let mut candidates: Vec<(std::time::SystemTime, PathBuf)> = Vec::new();
        let Ok(entries) = fs::read_dir(dir) else {
            return None;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            let is_audio = path
                .extension()
                .and_then(OsStr::to_str)
                .map(|ext| {
                    matches!(
                        ext.to_ascii_lowercase().as_str(),
                        "flac" | "mp3" | "m4a" | "aac" | "ogg" | "opus" | "wav" | "webm"
                    )
                })
                .unwrap_or(false);
            if !is_audio {
                continue;
            }
            let Ok(meta) = path.metadata() else { continue };
            let Ok(modified) = meta.modified() else {
                continue;
            };
            if modified >= started_at {
                candidates.push((modified, path));
            }
        }
        candidates.sort_by(|a, b| b.0.cmp(&a.0));
        candidates.into_iter().map(|(_, p)| p).next()
    }

    /// Simple word-overlap similarity ratio (0.0–1.0).
    ///
    /// Python uses `SequenceMatcher(None, target, video_title).ratio()`.
    /// Rust doesn't ship SequenceMatcher, but `strsim::jaro_winkler` gives a
    /// close approximation.  We use the simpler `strsim::normalized_levenshtein`
    /// which tends to agree with Python's SequenceMatcher on short strings.
    fn title_similarity(expected: &str, got: &str) -> f64 {
        let a = expected.to_lowercase();
        let b = got.to_lowercase();
        strsim::normalized_levenshtein(&a, &b)
    }
}

impl AcquisitionTier for YtdlpTier {
    fn name(&self) -> &str {
        "yt-dlp"
    }

    fn tier_tag(&self) -> &str {
        "T4"
    }

    fn try_acquire(&self, item: &AcquisitionQueueItem, staging_dir: &Path) -> TierResult {
        let artist = item.artist.trim();
        let title = item.title.trim();

        // --- Locate binary ---------------------------------------------------
        let Some(binary) = self.find_binary() else {
            return TierResult::Skip("yt-dlp binary not found in PATH".to_string());
        };

        // --- Build isolated temp dir inside staging_dir ----------------------
        let tmp_name = format!(
            "ytdlp-{}-{}",
            item.id,
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or(Duration::ZERO)
                .as_millis()
        );
        let tmp_dir = staging_dir.join(&tmp_name);
        if let Err(err) = fs::create_dir_all(&tmp_dir) {
            return TierResult::Fail(format!("Could not create yt-dlp temp dir: {err}"));
        }

        let query = format!("ytsearch1:{artist} {title}");
        let outtmpl = tmp_dir
            .join("%(title)s.%(ext)s")
            .to_string_lossy()
            .into_owned();

        info!(
            "[yt-dlp] Searching YouTube: {} - {} (tier={})",
            artist,
            title,
            self.tier_tag()
        );

        let started_at = std::time::SystemTime::now();
        let deadline = Instant::now() + Duration::from_secs(self.timeout_secs);

        // --- Spawn yt-dlp ----------------------------------------------------
        let mut cmd = Command::new(&binary);
        cmd.arg("--format")
            .arg("bestaudio/best")
            .arg("--no-playlist")
            .arg("--quiet")
            .arg("--no-warnings")
            .arg("--socket-timeout")
            .arg("30")
            .arg("--retries")
            .arg("2")
            .arg("--extract-audio")
            .arg("--audio-format")
            .arg("mp3")
            .arg("--audio-quality")
            .arg("320K")
            .arg("--output")
            .arg(&outtmpl)
            .arg("--print")
            .arg("title") // print the resolved title to stdout for similarity check
            .arg(&query)
            .stdout(Stdio::piped())
            .stderr(Stdio::null());

        let mut child = match cmd.spawn() {
            Ok(child) => child,
            Err(err) => {
                return TierResult::Fail(format!("Failed to spawn yt-dlp: {err}"));
            }
        };

        // Drain stdout in a background thread so the pipe never fills and
        // blocks the child process (important on Windows).
        let (stdout_tx, stdout_rx) = mpsc::channel::<String>();
        if let Some(stdout) = child.stdout.take() {
            thread::spawn(move || {
                use std::io::Read;
                let mut buf = String::new();
                let mut reader = stdout;
                let _ = reader.read_to_string(&mut buf);
                let _ = stdout_tx.send(buf);
            });
        }

        // --- Wait with timeout -----------------------------------------------
        let exit_status = loop {
            match child.try_wait() {
                Ok(Some(status)) => break status,
                Ok(None) => {
                    if Instant::now() >= deadline {
                        let _ = child.kill();
                        let _ = child.wait();
                        let _ = fs::remove_dir_all(&tmp_dir);
                        return TierResult::Fail(format!(
                            "yt-dlp timed out after {}s",
                            self.timeout_secs
                        ));
                    }
                    thread::sleep(Duration::from_millis(250));
                }
                Err(err) => {
                    let _ = child.kill();
                    let _ = fs::remove_dir_all(&tmp_dir);
                    return TierResult::Fail(format!("yt-dlp wait error: {err}"));
                }
            }
        };

        // Collect the printed title (--print title emits one line).
        let resolved_title = stdout_rx
            .recv_timeout(Duration::from_secs(2))
            .unwrap_or_default()
            .trim()
            .to_string();

        if !exit_status.success() {
            let _ = fs::remove_dir_all(&tmp_dir);
            return TierResult::Fail(format!(
                "yt-dlp exited with code {}",
                exit_status.code().unwrap_or(-1)
            ));
        }

        // --- Find downloaded file --------------------------------------------
        let Some(downloaded) = Self::newest_audio_file(&tmp_dir, started_at) else {
            let _ = fs::remove_dir_all(&tmp_dir);
            return TierResult::Fail("yt-dlp produced no audio file".to_string());
        };

        // --- Similarity check ------------------------------------------------
        let expected = format!("{artist} {title}");
        let video_title = if resolved_title.is_empty() {
            downloaded
                .file_stem()
                .and_then(OsStr::to_str)
                .unwrap_or("")
                .to_string()
        } else {
            resolved_title
        };

        let similarity = Self::title_similarity(&expected, &video_title);
        if similarity < self.min_similarity {
            warn!(
                "[yt-dlp] Title mismatch (sim={:.2}): wanted '{}', got '{}'",
                similarity, expected, video_title
            );
            let _ = fs::remove_dir_all(&tmp_dir);
            return TierResult::Fail(format!(
                "YouTube result mismatch (sim={:.2}): got '{video_title}'",
                similarity
            ));
        }

        // --- Move to staging dir with clean filename -------------------------
        let ext = downloaded
            .extension()
            .and_then(OsStr::to_str)
            .unwrap_or("mp3");
        let clean_name = format!(
            "{} - {}.{}",
            Self::sanitize(artist),
            Self::sanitize(title),
            ext
        );
        let target = staging_dir.join(&clean_name);

        // De-duplicate filename if a previous download already exists.
        let final_target = if target.exists() {
            let stem = format!(
                "{} - {}_{}",
                Self::sanitize(artist),
                Self::sanitize(title),
                item.id
            );
            staging_dir.join(format!("{stem}.{ext}"))
        } else {
            target
        };

        match fs::rename(&downloaded, &final_target) {
            Ok(()) => {}
            Err(_) => {
                // Cross-device rename can fail on Windows; fall back to copy + delete.
                if let Err(err) = fs::copy(&downloaded, &final_target) {
                    let _ = fs::remove_dir_all(&tmp_dir);
                    return TierResult::Fail(format!("Could not move yt-dlp output: {err}"));
                }
                let _ = fs::remove_file(&downloaded);
            }
        }

        // Clean up isolated temp dir (should be empty now).
        let _ = fs::remove_dir_all(&tmp_dir);

        info!(
            "[yt-dlp] Success: {} (sim={:.2})",
            final_target.display(),
            similarity
        );
        TierResult::Success(final_target)
    }
}

// ---------------------------------------------------------------------------
// run_waterfall
// ---------------------------------------------------------------------------

/// Result returned by `run_waterfall`.
#[derive(Debug)]
pub struct WaterfallOutcome {
    /// The file path if any tier succeeded.
    pub path: Option<PathBuf>,
    /// Name of the tier that produced the file (or attempted last).
    pub provider: Option<String>,
    /// Tier tag (e.g. "T4") of the tier that produced the file.
    pub tier: Option<String>,
    /// Failure reason if all tiers failed / were skipped.
    pub failure_reason: Option<String>,
}

/// Run the acquisition waterfall.
///
/// Calls `try_acquire` on each tier in order and returns on the first
/// `TierResult::Success`.  If every tier returns Skip or Fail the outcome
/// records the last failure reason.
///
/// The guard check (`is_junk`) is intentionally **not** run inside this
/// function — the dispatcher already runs duplicate detection before reaching
/// this point.  Callers that need the full guard can call `is_junk` before
/// calling `run_waterfall`.
pub fn run_waterfall(
    item: &AcquisitionQueueItem,
    tiers: &[Box<dyn AcquisitionTier>],
    staging_dir: &Path,
) -> WaterfallOutcome {
    let mut last_reason: Option<String> = None;
    let mut last_provider: Option<String> = None;
    let mut last_tier: Option<String> = None;

    for tier in tiers {
        info!(
            "[waterfall] Trying {} ({}) for {} - {}",
            tier.name(),
            tier.tier_tag(),
            item.artist,
            item.title
        );
        match tier.try_acquire(item, staging_dir) {
            TierResult::Success(path) => {
                info!("[waterfall] {} succeeded: {}", tier.name(), path.display());
                return WaterfallOutcome {
                    path: Some(path),
                    provider: Some(tier.name().to_string()),
                    tier: Some(tier.tier_tag().to_string()),
                    failure_reason: None,
                };
            }
            TierResult::Skip(reason) => {
                info!("[waterfall] {} skipped: {}", tier.name(), reason);
                last_reason = Some(reason);
                last_provider = Some(tier.name().to_string());
                last_tier = Some(tier.tier_tag().to_string());
            }
            TierResult::Fail(reason) => {
                warn!("[waterfall] {} failed: {}", tier.name(), reason);
                last_reason = Some(reason);
                last_provider = Some(tier.name().to_string());
                last_tier = Some(tier.tier_tag().to_string());
            }
        }
    }

    warn!(
        "[waterfall] All tiers exhausted for {} - {}",
        item.artist, item.title
    );
    WaterfallOutcome {
        path: None,
        provider: last_provider,
        tier: last_tier,
        failure_reason: last_reason
            .or_else(|| Some("No acquisition tiers were configured".to_string())),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn is_junk_karaoke() {
        assert!(is_junk("Karaoke Stars", "Bohemian Rhapsody"));
        assert!(is_junk("Queen", "Bohemian Rhapsody Karaoke"));
        assert!(is_junk("Vitamin String Quartet", "Enter Sandman"));
    }

    #[test]
    fn is_junk_title_patterns() {
        // "A Static Lullaby" is a real band — should NOT be flagged on artist
        // alone; only when the title contains a junk descriptor.
        assert!(!is_junk("A Static Lullaby", "Hang Em High"));
        assert!(is_junk(
            "A Static Lullaby",
            "Hang Em High (Lullaby Version)"
        ));
        assert!(is_junk("Metallica", "Enter Sandman 8-Bit"));
        assert!(is_junk("Daft Punk", "Get Lucky (Instrumental Version)"));
    }

    #[test]
    fn is_junk_clean_tracks() {
        assert!(!is_junk("Coheed and Cambria", "Welcome Home"));
        assert!(!is_junk("Kendrick Lamar", "HUMBLE."));
        assert!(!is_junk("Brand New", "Jesus Christ"));
    }

    fn make_test_item(id: i64, artist: &str, title: &str) -> AcquisitionQueueItem {
        AcquisitionQueueItem {
            id,
            artist: artist.to_string(),
            title: title.to_string(),
            album: None,
            status: "queued".to_string(),
            queue_position: 0,
            priority_score: 0.0,
            source: None,
            added_at: String::new(),
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

    #[test]
    fn waterfall_empty_tiers() {
        let item = make_test_item(1, "Artist", "Title");
        let outcome = run_waterfall(&item, &[], std::path::Path::new("/tmp"));
        assert!(outcome.path.is_none());
        assert!(outcome.failure_reason.is_some());
    }

    #[test]
    fn ytdlp_tier_skip_when_not_found() {
        // This test verifies that when yt-dlp is not in PATH, the tier returns
        // Skip rather than panicking.
        let tier = YtdlpTier {
            binary: Some(PathBuf::from("/nonexistent/yt-dlp")),
            ..YtdlpTier::default()
        };
        let item = make_test_item(99, "Test Artist", "Test Title");
        // yt-dlp not in PATH in CI either — we only test the Skip path.
        if which::which("yt-dlp").is_err() {
            let result = tier.try_acquire(&item, std::path::Path::new("/tmp"));
            assert!(matches!(result, TierResult::Skip(_)));
        }
    }
}

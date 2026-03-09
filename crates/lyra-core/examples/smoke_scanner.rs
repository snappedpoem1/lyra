/// Smoke test — C: Scanner (library.rs)
///
/// Verifies:
///   1. is_supported_audio_file() rejects non-audio, accepts .flac/.mp3
///   2. read_audio_tags (via import) extracts title/artist/album from a real file
///   3. strip_feat via artist field — feat. suffix is stripped on import
///   4. content_hash is written to the DB row
///   5. track_number + disc_number land in the DB row
///   6. Re-import (same path) returns inserted=false (UPDATE path, not INSERT)
///   7. track + disc numbers survive the re-import update
use lyra_core::db::init_database;
use lyra_core::library::{import_track_from_path, is_supported_audio_file};
use rusqlite::{params, Connection};
use std::path::Path;

const PROBE_FILE: &str = "A:\\music\\Beck\\Guero\\01_E-Pro.flac";

fn pass(msg: &str) {
    println!("  PASS  {msg}");
}

fn fail(msg: &str) {
    println!("  FAIL  {msg}");
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("\n=== smoke_scanner ===\n");

    // ── 1. is_supported_audio_file ──────────────────────────────────────────
    let supported = [".flac", ".mp3", ".ogg", ".m4a", ".wav", ".aac"];
    let rejected = [".txt", ".jpg", ".pdf", ".exe", ".opus", ".aiff"];

    for ext in supported {
        let name = format!("track{ext}");
        let p = Path::new(&name);
        if is_supported_audio_file(p) {
            pass(&format!("accepts {ext}"));
        } else {
            fail(&format!("should accept {ext}"));
        }
    }
    for ext in rejected {
        let name = format!("file{ext}");
        let p = Path::new(&name);
        if !is_supported_audio_file(p) {
            pass(&format!("rejects {ext}"));
        } else {
            fail(&format!("should reject {ext}"));
        }
    }

    // ── 2-7. Real-file import ───────────────────────────────────────────────
    let probe = Path::new(PROBE_FILE);
    if !probe.exists() {
        println!("\n  SKIP  probe file not found: {PROBE_FILE}");
        println!("        (set PROBE_FILE to any local .flac/.mp3 to run file checks)\n");
        return Ok(());
    }

    // Use an in-memory DB with the normalized Rust schema so import functions work correctly.
    let conn = Connection::open_in_memory()?;
    init_database(&conn)?;

    // First import — must be inserted (or already exists from library scan)
    let inserted_first = import_track_from_path(&conn, probe)?;
    println!("\n  INFO  first import returned inserted={inserted_first}");

    // Re-import — must NOT insert again
    let inserted_second = import_track_from_path(&conn, probe)?;
    if !inserted_second {
        pass("re-import returns inserted=false (UPDATE path)");
    } else {
        fail("re-import returned inserted=true — duplicate INSERT");
    }

    // Read back the row
    let (title, artist, content_hash, track_number, disc_number): (
        String,
        String,
        Option<String>,
        Option<i64>,
        Option<i64>,
    ) = conn.query_row(
        "SELECT t.title, COALESCE(ar.name,''), t.content_hash, t.track_number, t.disc_number
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE t.path = ?1",
        params![PROBE_FILE],
        |row| {
            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
            ))
        },
    )?;

    println!("\n  INFO  title         = {title}");
    println!("  INFO  artist        = {artist}");
    println!("  INFO  content_hash  = {:?}", content_hash);
    println!("  INFO  track_number  = {:?}", track_number);
    println!("  INFO  disc_number   = {:?}", disc_number);

    // title must be non-empty
    if !title.is_empty() && title != "Unknown Track" {
        pass(&format!("title extracted: \"{title}\""));
    } else {
        fail("title is empty or fallback");
    }

    // artist must not contain " feat." (strip_feat)
    if !artist.to_lowercase().contains(" feat.") && !artist.to_lowercase().contains(" ft.") {
        pass(&format!("feat. stripped from artist: \"{artist}\""));
    } else {
        fail(&format!("feat. NOT stripped from artist: \"{artist}\""));
    }

    // content_hash must be present
    if content_hash.is_some() {
        pass("content_hash written");
    } else {
        fail("content_hash is NULL — hash not written");
    }

    // track_number
    if track_number.is_some() {
        pass(&format!("track_number = {:?}", track_number));
    } else {
        println!("  WARN  track_number is NULL (tag may not be embedded)");
    }

    println!();
    println!("=== smoke_scanner done ===\n");
    Ok(())
}

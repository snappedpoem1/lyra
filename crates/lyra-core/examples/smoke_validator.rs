//! Smoke test: validator module — text cleaning, junk guard, validate_track_text.

use lyra_core::{
    db::init_database,
    validator::{
        clean_artist, clean_title, extract_artist_from_title,
        is_junk_text, validate_track_text,
        ensure_validation_table, mark_validated,
    },
};
use rusqlite::Connection;

fn main() {
    let mut fail = false;

    // ── clean_title ──────────────────────────────────────────────────────────
    let cases: &[(&str, &str)] = &[
        ("E-Pro (Official Video)", "E-Pro"),
        ("E-Pro [Official Audio]", "E-Pro"),
        ("E-Pro (Explicit)",       "E-Pro"),
        ("E-Pro (Lyrics)",         "E-Pro"),
        ("E-Pro | Beck VEVO",      "E-Pro"),
        ("E-Pro - Official",       "E-Pro"),
        ("E-Pro",                  "E-Pro"),   // no change
    ];
    for (input, want) in cases {
        let got = clean_title(input);
        if got != *want {
            eprintln!("FAIL clean_title({:?}) => {:?}, want {:?}", input, got, want);
            fail = true;
        } else {
            println!("PASS clean_title({:?}) => {:?}", input, got);
        }
    }

    // ── clean_artist ─────────────────────────────────────────────────────────
    let artist_cases: &[(&str, &str)] = &[
        ("BeckVEVO",     "Beck"),
        ("Beck - Topic", "Beck"),
        ("Beck",         "Beck"),
    ];
    for (input, want) in artist_cases {
        let got = clean_artist(input);
        if got != *want {
            eprintln!("FAIL clean_artist({:?}) => {:?}, want {:?}", input, got, want);
            fail = true;
        } else {
            println!("PASS clean_artist({:?}) => {:?}", input, got);
        }
    }

    // ── extract_artist_from_title ─────────────────────────────────────────────
    let (artist, title) = extract_artist_from_title("Beck - E-Pro");
    assert_eq!(artist.as_deref(), Some("Beck"), "FAIL extract artist");
    assert_eq!(title, "E-Pro", "FAIL extract title");
    println!("PASS extract_artist_from_title('Beck - E-Pro') => ({:?}, {:?})", artist, title);

    let (artist2, title2) = extract_artist_from_title("E-Pro");
    assert!(artist2.is_none(), "FAIL: should have no extracted artist");
    assert_eq!(title2, "E-Pro");
    println!("PASS extract_artist_from_title('E-Pro') => (None, 'E-Pro')");

    // ── is_junk_text ─────────────────────────────────────────────────────────
    let junk_cases: &[(&str, &str, bool)] = &[
        ("Various Artists", "E-Pro (Karaoke Version)", true),
        ("Tribute Band",    "E-Pro Tribute",           true),
        ("Beck",            "E-Pro (Piano Version)",   true),
        ("Beck",            "E-Pro",                   false),
        ("A Static Lullaby","Hey Girl",                 false), // band name not junk
        ("Epitaph Records", "E-Pro",                   true),  // record label as artist
    ];
    for (artist, title, want_junk) in junk_cases {
        let got = is_junk_text(artist, title);
        let is_junk = got.is_some();
        if is_junk != *want_junk {
            eprintln!(
                "FAIL is_junk_text({:?}, {:?}) => {:?}, want junk={}",
                artist, title, got, want_junk
            );
            fail = true;
        } else {
            println!(
                "PASS is_junk_text({:?}) => {}",
                title,
                got.as_deref().unwrap_or("clean")
            );
        }
    }

    // ── validate_track_text ───────────────────────────────────────────────────
    let r = validate_track_text("Beck", "E-Pro");
    assert!(r.valid, "FAIL: Beck/E-Pro should be valid");
    assert_eq!(r.canonical_artist.as_deref(), Some("Beck"));
    assert_eq!(r.canonical_title.as_deref(), Some("E-Pro"));
    println!("PASS: validate_track_text(Beck, E-Pro) => valid");

    let r2 = validate_track_text("", "Beck - E-Pro (Official Video)");
    assert!(r2.valid, "FAIL: should extract and clean");
    assert_eq!(r2.canonical_artist.as_deref(), Some("Beck"));
    assert_eq!(r2.canonical_title.as_deref(), Some("E-Pro"));
    println!("PASS: validate_track_text(empty, 'Beck - E-Pro (Official Video)') => extracted+cleaned");

    let r3 = validate_track_text("Karaoke Stars", "E-Pro Karaoke");
    assert!(!r3.valid, "FAIL: karaoke should be rejected");
    println!("PASS: validate_track_text karaoke => rejected: {:?}", r3.rejection_reason);

    // ── DB writeback ──────────────────────────────────────────────────────────
    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();
    ensure_validation_table(&conn).unwrap();

    conn.execute(
        "INSERT INTO artists (id, name) VALUES (1, 'Beck')",
        [],
    ).unwrap();
    conn.execute(
        "INSERT INTO tracks (id, title, artist_id, path, imported_at) VALUES (1, 'E-Pro', 1, 'A:/epro.flac', '2026-01-01')",
        [],
    ).unwrap();

    let result = validate_track_text("Beck", "E-Pro");
    mark_validated(&conn, 1, &result).unwrap();

    let status: String = conn
        .query_row(
            "SELECT status FROM track_validation WHERE track_id = 1",
            [],
            |row| row.get(0),
        )
        .unwrap();
    assert_eq!(status, "valid");
    println!("PASS: mark_validated => status='valid' in DB");

    if fail {
        eprintln!("\nSome validator tests FAILED");
        std::process::exit(1);
    }
    println!("\nAll smoke_validator checks passed.");
}

//! Smoke test: classifier + duplicates modules.

use lyra_core::{
    classifier::{classify_text, VersionType},
    db::init_database,
    duplicates::{find_exact_duplicates, find_metadata_duplicates, find_path_duplicates},
};
use rusqlite::Connection;

fn main() {
    // ── classifier::classify_text ─────────────────────────────────────────────

    struct Case {
        title: &'static str,
        album: &'static str,
        path:  &'static str,
        want:  VersionType,
    }

    let cases = vec![
        Case { title: "E-Pro",                       album: "Guero",       path: "E-Pro.flac",         want: VersionType::Original },
        Case { title: "E-Pro (Live at Coachella)",   album: "",            path: "",                   want: VersionType::Live    },
        Case { title: "E-Pro (Remix)",               album: "",            path: "",                   want: VersionType::Remix   },
        Case { title: "E-Pro (Cover Version)",       album: "",            path: "",                   want: VersionType::Cover   },
        Case { title: "E-Pro (Official Video)",      album: "",            path: "",                   want: VersionType::Junk    },
        Case { title: "E-Pro (Nightcore)",           album: "",            path: "",                   want: VersionType::Special },
        Case { title: "E-Pro (Slowed + Reverb)",     album: "",            path: "",                   want: VersionType::Special },
        // "A Static Lullaby" — band name should NOT trigger special via album/path
        Case { title: "Hey Girl",                    album: "A Static Lullaby", path: "hey_girl.mp3", want: VersionType::Original },
    ];

    let mut fail = false;
    for c in &cases {
        let r = classify_text(c.title, c.album, c.path);
        if r.version_type != c.want {
            eprintln!(
                "FAIL: classify_text({:?}, {:?}) => {:?}, want {:?}",
                c.title, c.album, r.version_type, c.want
            );
            fail = true;
        } else {
            println!("PASS: {:?} => {} ({:.2})", c.title, r.version_type, r.confidence);
        }
    }

    // ── confidence bounds ─────────────────────────────────────────────────────

    let r = classify_text("Remix Bootleg Edit VIP", "", "");
    assert!(r.confidence <= 1.0 && r.confidence > 0.0, "FAIL: confidence out of bounds");
    println!("PASS: confidence bounds ({:.2})", r.confidence);

    // ── duplicates (in-memory DB) ─────────────────────────────────────────────

    let conn = Connection::open_in_memory().unwrap();
    init_database(&conn).unwrap();

    // Insert artists/albums
    conn.execute("INSERT INTO artists (id, name) VALUES (1, 'Beck')", []).unwrap();
    conn.execute("INSERT INTO albums  (id, title, artist_id) VALUES (1, 'Guero', 1)", []).unwrap();

    // Track A — original
    conn.execute(
        "INSERT INTO tracks (id, title, artist_id, album_id, path, content_hash, imported_at) VALUES (1, 'E-Pro', 1, 1, 'A:/music/epro.flac', 'abc123', '2026-01-01')",
        [],
    ).unwrap();
    // Track B — exact hash duplicate
    conn.execute(
        "INSERT INTO tracks (id, title, artist_id, album_id, path, content_hash, imported_at) VALUES (2, 'E-Pro', 1, 1, 'A:/music/epro_copy.flac', 'abc123', '2026-01-01')",
        [],
    ).unwrap();
    // Track C — metadata duplicate (slight title variation)
    conn.execute(
        "INSERT INTO tracks (id, title, artist_id, album_id, path, content_hash, imported_at) VALUES (3, 'E-Pro ', 1, 1, 'A:/music/epro2.flac', 'def456', '2026-01-01')",
        [],
    ).unwrap();
    // Exact duplicates: tracks 1+2 share 'abc123'
    let exact = find_exact_duplicates(&conn).unwrap();
    assert_eq!(exact.len(), 1, "FAIL: expected 1 exact group, got {}", exact.len());
    assert_eq!(exact[0].len(), 2, "FAIL: expected 2 members in group");
    println!("PASS: find_exact_duplicates => 1 group, 2 tracks");

    // Metadata duplicates: tracks 1+3 (title "E-Pro" vs "E-Pro ")
    let meta = find_metadata_duplicates(&conn, 0.85).unwrap();
    assert!(meta.len() >= 1, "FAIL: expected ≥1 metadata group, got {}", meta.len());
    println!("PASS: find_metadata_duplicates => {} group(s)", meta.len());

    // Path duplicates: Rust schema enforces UNIQUE on path so this is always empty
    // on a clean DB — find_path_duplicates is a safety net for legacy/migrated data.
    let paths = find_path_duplicates(&conn).unwrap();
    println!("PASS: find_path_duplicates => {} group(s) (0 expected on clean schema)", paths.len());

    if fail {
        eprintln!("\nSome classifier tests FAILED");
        std::process::exit(1);
    }

    println!("\nAll smoke_classifier checks passed.");
}

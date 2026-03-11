use crate::acquisition;
use crate::audio_data::{self, RawTrackCandidate};
use crate::catalog::{self, CatalogRelease};
use crate::commands::{AcquisitionPlanResult, AcquisitionQueueItem};
use crate::errors::{LyraError, LyraResult};
use crate::library;
use rusqlite::{params, Connection, OptionalExtension};
use serde_json::json;

#[derive(Clone, Debug)]
struct ValidationAssessment {
    artist: String,
    title: String,
    album: Option<String>,
    confidence: f64,
    summary: String,
    detail: Option<String>,
    duplicate_path: Option<String>,
}

#[derive(Clone, Debug)]
struct PlanTrackCandidate {
    item_kind: String,
    artist: String,
    title: String,
    album: Option<String>,
    release_group_mbid: Option<String>,
    release_date: Option<String>,
    disc_number: Option<i64>,
    track_number: Option<i64>,
    evidence_level: String,
    evidence_summary: String,
    payload: serde_json::Value,
    duration_ms: Option<i64>,
}

#[derive(Clone, Debug)]
struct QueuePlanOutcome {
    item_status: String,
    queue_item: Option<AcquisitionQueueItem>,
    evidence_level: String,
    evidence_summary: String,
}

pub fn plan_single_track(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
    source: Option<&str>,
    target_root_id: Option<i64>,
) -> LyraResult<AcquisitionPlanResult> {
    let validation = validate_acquisition_request(conn, artist, title, album)?;
    let (resolved_target_root_id, target_root_path) = resolve_target_root(conn, target_root_id)?;
    let plan = acquisition::create_acquisition_plan(
        conn,
        "single_track",
        source,
        Some(artist),
        Some(title),
        album,
        Some(&validation.artist),
        validation.album.as_deref(),
        "Rust planner created a canonical single-track acquisition request",
    )?;
    let outcome = queue_track_candidate(
        conn,
        source,
        resolved_target_root_id,
        target_root_path.as_deref(),
        PlanTrackCandidate {
            item_kind: "single_track".to_string(),
            artist: validation.artist.clone(),
            title: validation.title.clone(),
            album: validation.album.clone(),
            release_group_mbid: None,
            release_date: None,
            disc_number: None,
            track_number: None,
            evidence_level: "provider_metadata".to_string(),
            evidence_summary: validation.summary.clone(),
            payload: json!({
                "kind": "single_track",
                "requestedArtist": artist,
                "requestedTitle": title,
                "requestedAlbum": album,
            }),
            duration_ms: None,
        },
        Some(validation),
        true,
    )?;
    acquisition::add_plan_item(
        conn,
        plan.id,
        "single_track",
        &outcome.item_status,
        artist,
        title,
        album,
        None,
        None,
        None,
        None,
        outcome.queue_item.as_ref().map(|item| item.id),
        &outcome.evidence_level,
        &outcome.evidence_summary,
    )?;
    acquisition::finalize_acquisition_plan(conn, plan.id, None)?;
    acquisition::get_acquisition_plan_result(conn, plan.id)
}

pub fn plan_album(
    conn: &Connection,
    artist: &str,
    album_title: &str,
    source: Option<&str>,
    target_root_id: Option<i64>,
) -> LyraResult<AcquisitionPlanResult> {
    let (catalog_artist, release) =
        catalog::resolve_album(conn, artist, album_title).map_err(LyraError::Message)?;
    let (resolved_target_root_id, target_root_path) = resolve_target_root(conn, target_root_id)?;
    let plan = acquisition::create_acquisition_plan(
        conn,
        "album",
        source,
        Some(artist),
        None,
        Some(album_title),
        Some(&catalog_artist.name),
        Some(&release.title),
        &format!(
            "Rust planner resolved the canonical album '{}' for {}",
            release.title, catalog_artist.name
        ),
    )?;
    queue_catalog_release(
        conn,
        plan.id,
        "album_track",
        source,
        resolved_target_root_id,
        target_root_path.as_deref(),
        &catalog_artist.name,
        &release,
    )?;
    acquisition::finalize_acquisition_plan(conn, plan.id, None)?;
    acquisition::get_acquisition_plan_result(conn, plan.id)
}

pub fn plan_discography(
    conn: &Connection,
    artist: &str,
    source: Option<&str>,
    target_root_id: Option<i64>,
    limit_albums: Option<usize>,
) -> LyraResult<AcquisitionPlanResult> {
    let discography =
        catalog::resolve_discography(conn, artist, limit_albums).map_err(LyraError::Message)?;
    let (resolved_target_root_id, target_root_path) = resolve_target_root(conn, target_root_id)?;
    let plan = acquisition::create_acquisition_plan(
        conn,
        "discography",
        source,
        Some(artist),
        None,
        None,
        Some(&discography.artist.name),
        None,
        &format!(
            "Rust planner resolved {} canonical album/EP releases for {}",
            discography.releases.len(),
            discography.artist.name
        ),
    )?;
    for release in &discography.releases {
        queue_catalog_release(
            conn,
            plan.id,
            "discography_track",
            source,
            resolved_target_root_id,
            target_root_path.as_deref(),
            &discography.artist.name,
            release,
        )?;
    }
    acquisition::finalize_acquisition_plan(conn, plan.id, None)?;
    acquisition::get_acquisition_plan_result(conn, plan.id)
}

fn queue_catalog_release(
    conn: &Connection,
    plan_id: i64,
    item_kind: &str,
    source: Option<&str>,
    target_root_id: Option<i64>,
    target_root_path: Option<&str>,
    canonical_artist: &str,
    release: &CatalogRelease,
) -> LyraResult<()> {
    for track in &release.tracks {
        let candidate = PlanTrackCandidate {
            item_kind: item_kind.to_string(),
            artist: canonical_artist.to_string(),
            title: track.title.clone(),
            album: Some(release.title.clone()),
            release_group_mbid: Some(release.release_group_mbid.clone()),
            release_date: release.release_date.clone(),
            disc_number: Some(track.disc_number),
            track_number: Some(track.position),
            evidence_level: "provider_metadata".to_string(),
            evidence_summary: release.evidence_summary.clone(),
            payload: json!({
                "provider": "musicbrainz_catalog",
                "artist": canonical_artist,
                "album": release.title,
                "releaseGroupMbid": release.release_group_mbid,
                "releaseMbid": release.release_mbid,
                "recordingMbid": track.recording_mbid,
                "position": track.position,
                "discNumber": track.disc_number,
                "releaseDate": release.release_date,
                "sourceMode": release.source_mode,
            }),
            duration_ms: track.duration_ms,
        };
        let outcome = queue_track_candidate(
            conn,
            source,
            target_root_id,
            target_root_path,
            candidate.clone(),
            None,
            false,
        )?;
        acquisition::add_plan_item(
            conn,
            plan_id,
            &candidate.item_kind,
            &outcome.item_status,
            &candidate.artist,
            &candidate.title,
            candidate.album.as_deref(),
            candidate.release_group_mbid.as_deref(),
            candidate.release_date.as_deref(),
            candidate.disc_number,
            candidate.track_number,
            outcome.queue_item.as_ref().map(|item| item.id),
            &outcome.evidence_level,
            &outcome.evidence_summary,
        )?;
    }
    Ok(())
}

fn queue_track_candidate(
    conn: &Connection,
    source: Option<&str>,
    target_root_id: Option<i64>,
    target_root_path: Option<&str>,
    candidate: PlanTrackCandidate,
    existing_validation: Option<ValidationAssessment>,
    create_failed_queue_entry_on_block: bool,
) -> LyraResult<QueuePlanOutcome> {
    let normalized = audio_data::normalize_track_candidate(RawTrackCandidate {
        provider: "musicbrainz_catalog",
        provider_track_id: candidate
            .payload
            .get("recordingMbid")
            .and_then(serde_json::Value::as_str)
            .unwrap_or(""),
        artist: &candidate.artist,
        title: &candidate.title,
        album: candidate.album.as_deref(),
        release_date: candidate.release_date.as_deref(),
        isrc: None,
        duration_ms: candidate.duration_ms,
        popularity: None,
        explicit: false,
    });
    let normalized = match normalized {
        Ok(track) => {
            audio_data::persist_provider_track(conn, &track, "acquisition", &candidate.payload)?;
            Some(track)
        }
        Err(error) => {
            if create_failed_queue_entry_on_block {
                let queue_item = create_blocked_queue_item(
                    conn,
                    source,
                    target_root_id,
                    target_root_path,
                    &candidate.artist,
                    &candidate.title,
                    candidate.album.as_deref(),
                    &format!("Rejected by Rust guard: {error}"),
                    Some("Catalog track failed canonical normalization"),
                )?;
                return Ok(QueuePlanOutcome {
                    item_status: "rejected".to_string(),
                    queue_item: Some(queue_item),
                    evidence_level: "provider_metadata".to_string(),
                    evidence_summary: format!(
                        "Catalog track was rejected by canonical normalization: {error}"
                    ),
                });
            }
            return Ok(QueuePlanOutcome {
                item_status: "rejected".to_string(),
                queue_item: None,
                evidence_level: "provider_metadata".to_string(),
                evidence_summary: format!(
                    "Catalog track was rejected by canonical normalization: {error}"
                ),
            });
        }
    };

    let validation = existing_validation.unwrap_or(validate_acquisition_request(
        conn,
        normalized
            .as_ref()
            .map(|track| track.artist.name.as_str())
            .unwrap_or(candidate.artist.as_str()),
        normalized
            .as_ref()
            .map(|track| track.title.as_str())
            .unwrap_or(candidate.title.as_str()),
        normalized
            .as_ref()
            .and_then(|track| track.album.as_ref().map(|album| album.title.as_str()))
            .or(candidate.album.as_deref()),
    )?);

    if let Some(path) = validation.duplicate_path.as_deref() {
        if create_failed_queue_entry_on_block {
            let queue_item = create_blocked_queue_item(
                conn,
                source,
                target_root_id,
                target_root_path,
                &validation.artist,
                &validation.title,
                validation.album.as_deref(),
                "Track already exists in the library",
                Some(path),
            )?;
            return Ok(QueuePlanOutcome {
                item_status: "duplicate_owned".to_string(),
                queue_item: Some(queue_item),
                evidence_level: "provider_metadata".to_string(),
                evidence_summary: format!("Track already exists in the library at {path}"),
            });
        }
        return Ok(QueuePlanOutcome {
            item_status: "duplicate_owned".to_string(),
            queue_item: None,
            evidence_level: "provider_metadata".to_string(),
            evidence_summary: format!("Track already exists in the library at {path}"),
        });
    }

    if active_queue_item_exists(
        conn,
        &validation.artist,
        &validation.title,
        validation.album.as_deref(),
    )? {
        return Ok(QueuePlanOutcome {
            item_status: "already_queued".to_string(),
            queue_item: None,
            evidence_level: candidate.evidence_level,
            evidence_summary: "Track is already queued in the canonical acquisition lane"
                .to_string(),
        });
    }

    if validation.summary.starts_with("Rejected by Rust guard:") {
        if create_failed_queue_entry_on_block {
            let queue_item = create_blocked_queue_item(
                conn,
                source,
                target_root_id,
                target_root_path,
                &validation.artist,
                &validation.title,
                validation.album.as_deref(),
                &validation.summary,
                validation.detail.as_deref(),
            )?;
            return Ok(QueuePlanOutcome {
                item_status: "rejected".to_string(),
                queue_item: Some(queue_item),
                evidence_level: candidate.evidence_level,
                evidence_summary: validation.summary,
            });
        }
        return Ok(QueuePlanOutcome {
            item_status: "rejected".to_string(),
            queue_item: None,
            evidence_level: candidate.evidence_level,
            evidence_summary: validation.summary,
        });
    }

    let priority = acquisition::compute_initial_priority(
        conn,
        &validation.artist,
        &validation.title,
        validation.album.as_deref(),
        source,
    )?;
    let queue_item = acquisition::add_acquisition_item(
        conn,
        &validation.artist,
        &validation.title,
        validation.album.as_deref(),
        source,
        priority,
        Some(validation.confidence),
        Some(&candidate.evidence_summary),
        target_root_id,
        target_root_path,
    )?;
    Ok(QueuePlanOutcome {
        item_status: "queued".to_string(),
        queue_item: Some(queue_item),
        evidence_level: candidate.evidence_level,
        evidence_summary: candidate.evidence_summary,
    })
}

fn create_blocked_queue_item(
    conn: &Connection,
    source: Option<&str>,
    target_root_id: Option<i64>,
    target_root_path: Option<&str>,
    artist: &str,
    title: &str,
    album: Option<&str>,
    reason: &str,
    detail: Option<&str>,
) -> LyraResult<AcquisitionQueueItem> {
    let priority = acquisition::compute_initial_priority(conn, artist, title, album, source)?;
    let queue_item = acquisition::add_acquisition_item(
        conn,
        artist,
        title,
        album,
        source,
        priority,
        None,
        Some(reason),
        target_root_id,
        target_root_path,
    )?;
    acquisition::mark_failed(conn, queue_item.id, "validating", reason, detail)?;
    acquisition::get_acquisition_item(conn, queue_item.id)?
        .ok_or_else(|| LyraError::Message("blocked queue item was not persisted".to_string()))
}

fn active_queue_item_exists(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
) -> LyraResult<bool> {
    let count: i64 = conn.query_row(
        "SELECT COUNT(*)
         FROM acquisition_queue
         WHERE lower(trim(artist)) = lower(trim(?1))
           AND lower(trim(title)) = lower(trim(?2))
           AND lower(trim(COALESCE(album, ''))) = lower(trim(COALESCE(?3, '')))
           AND status IN ('queued', 'validating', 'acquiring', 'staging', 'organizing', 'scanning', 'indexing')",
        params![artist, title, album],
        |row| row.get(0),
    )?;
    Ok(count > 0)
}

fn clean_artist_name(value: &str) -> String {
    let mut cleaned = value.trim().to_string();
    for suffix in [" - Topic", " VEVO", " Official"] {
        if cleaned
            .to_ascii_lowercase()
            .ends_with(&suffix.to_ascii_lowercase())
        {
            cleaned.truncate(cleaned.len().saturating_sub(suffix.len()));
            cleaned = cleaned.trim().to_string();
        }
    }
    cleaned
}

fn clean_track_title(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_string()
}

fn validation_confidence(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
) -> LyraResult<f64> {
    let known_artist: i64 = conn.query_row(
        "SELECT COUNT(*)
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))",
        params![artist],
        |row| row.get(0),
    )?;
    let exact_track: i64 = conn.query_row(
        "SELECT COUNT(*)
         FROM tracks t
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
           AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))",
        params![artist, title],
        |row| row.get(0),
    )?;
    let mut confidence = 0.42_f64;
    if known_artist > 0 {
        confidence += 0.26;
    }
    if album.is_some() {
        confidence += 0.08;
    }
    if exact_track > 0 {
        confidence += 0.12;
    }
    Ok(confidence.clamp(0.0, 0.97))
}

fn validate_acquisition_request(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
) -> LyraResult<ValidationAssessment> {
    let cleaned_artist = clean_artist_name(artist);
    let cleaned_title = clean_track_title(title);
    let cleaned_album = album.map(clean_track_title);
    let combined = format!("{} {}", cleaned_artist, cleaned_title).to_ascii_lowercase();
    let junk_needles = [
        "karaoke",
        "tribute",
        "cover version",
        "made famous",
        "made popular",
        "in the style of",
        "backing track",
        "lyrics video",
        "audio only",
        "nightcore",
        "slowed",
        "sped up",
        "chopped and screwed",
        "ringtone",
        "music box",
        "8-bit",
        "8 bit",
        "instrumental version",
        "a cappella",
        "acapella",
        "lo-fi",
        "lofi",
        "epic version",
    ];
    if junk_needles.iter().any(|needle| combined.contains(needle)) {
        let confidence = validation_confidence(
            conn,
            &cleaned_artist,
            &cleaned_title,
            cleaned_album.as_deref(),
        )?;
        return Ok(ValidationAssessment {
            artist: cleaned_artist,
            title: cleaned_title,
            album: cleaned_album,
            confidence,
            summary: "Rejected by Rust guard: likely junk, cover, or altered-version metadata"
                .to_string(),
            detail: Some("Queue item matched local junk-pattern checks".to_string()),
            duplicate_path: None,
        });
    }

    let artist_lower = cleaned_artist.to_ascii_lowercase();
    let record_labels = [
        "atlantic records",
        "columbia records",
        "interscope",
        "def jam",
        "universal music",
        "sony music",
        "warner records",
        "vevo",
        "topic",
        "official video",
        "official audio",
        "lyrical lemonade",
        "worldstarhiphop",
        "monstercat",
        "nocopyrightsounds",
    ];
    if record_labels
        .iter()
        .any(|label| artist_lower == *label || artist_lower.contains(label))
        || artist_lower.ends_with("- topic")
        || artist_lower.ends_with("vevo")
        || artist_lower.contains("official channel")
    {
        let confidence = validation_confidence(
            conn,
            &cleaned_artist,
            &cleaned_title,
            cleaned_album.as_deref(),
        )?;
        return Ok(ValidationAssessment {
            artist: cleaned_artist,
            title: cleaned_title,
            album: cleaned_album,
            confidence,
            summary:
                "Rejected by Rust guard: artist metadata looks like a label or YouTube channel"
                    .to_string(),
            detail: Some("Queue item matched local artist/label guard checks".to_string()),
            duplicate_path: None,
        });
    }

    let duplicate = conn
        .query_row(
            "SELECT t.path
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
               AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))
             LIMIT 1",
            params![cleaned_artist, cleaned_title],
            |row| row.get(0),
        )
        .optional()?;
    let confidence = validation_confidence(
        conn,
        &cleaned_artist,
        &cleaned_title,
        cleaned_album.as_deref(),
    )?;
    let summary = if duplicate.is_some() {
        "Canonical match already exists in the library".to_string()
    } else if let Some(album_title) = cleaned_album.as_deref() {
        format!("Canonical request accepted with album hint '{album_title}'")
    } else {
        "Canonical request accepted for native acquisition planning".to_string()
    };
    Ok(ValidationAssessment {
        artist: cleaned_artist,
        title: cleaned_title,
        album: cleaned_album,
        confidence,
        summary,
        detail: None,
        duplicate_path: duplicate,
    })
}

fn resolve_target_root(
    conn: &Connection,
    target_root_id: Option<i64>,
) -> LyraResult<(Option<i64>, Option<String>)> {
    let Some(root_id) = target_root_id else {
        return Ok((None, None));
    };
    let root = library::list_library_roots(conn)?
        .into_iter()
        .find(|root| root.id == root_id);
    Ok(match root {
        Some(root) => (Some(root.id), Some(root.path)),
        None => (None, None),
    })
}

#[cfg(test)]
mod tests {
    use super::{plan_album, plan_discography, plan_single_track};
    use crate::catalog::{
        artist_search_cache_key, release_candidates_cache_key, release_detail_cache_key,
        release_group_cache_key,
    };
    use crate::db;
    use chrono::Utc;
    use rusqlite::{params, Connection};
    use serde_json::json;

    fn setup_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("memory db");
        db::init_database(&conn).expect("schema");
        conn.execute(
            "INSERT INTO library_roots (path, added_at) VALUES (?1, ?2)",
            params!["C:\\Library", Utc::now().to_rfc3339()],
        )
        .expect("library root");
        conn
    }

    fn seed_cache(conn: &Connection, key: &str, payload: serde_json::Value) {
        conn.execute(
            "INSERT INTO enrich_cache (provider, lookup_key, payload_json, fetched_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![
                "musicbrainz_catalog",
                key,
                payload.to_string(),
                Utc::now().to_rfc3339()
            ],
        )
        .expect("cache");
    }

    fn seed_cursive_catalog(conn: &Connection) {
        seed_cache(
            conn,
            &artist_search_cache_key("Cursive"),
            json!({
                "artists": [{"id": "artist-cursive", "name": "Cursive", "score": 100, "type": "Group"}]
            }),
        );
        seed_cache(
            conn,
            &release_group_cache_key("artist-cursive", "album"),
            json!({
                "release-groups": [
                    {
                        "id": "rg-domestica",
                        "title": "Domestica",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2000-06-13"
                    },
                    {
                        "id": "rg-ugly",
                        "title": "The Ugly Organ",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2003-10-07"
                    },
                    {
                        "id": "rg-tribute",
                        "title": "A Tribute to Cursive",
                        "primary-type": "Album",
                        "secondary-types": [],
                        "first-release-date": "2006-01-01"
                    }
                ]
            }),
        );
        seed_cache(
            conn,
            &release_group_cache_key("artist-cursive", "ep"),
            json!({ "release-groups": [] }),
        );
        for (rgid, release_id, album_title, tracks) in [
            (
                "rg-domestica",
                "release-domestica",
                "Domestica",
                vec![
                    json!({"position": 1, "title": "The Casualty", "recording": {"id": "rec-dom-1", "length": 191000}}),
                    json!({"position": 2, "title": "A Red So Deep", "recording": {"id": "rec-dom-2", "length": 233000}}),
                ],
            ),
            (
                "rg-ugly",
                "release-ugly",
                "The Ugly Organ",
                vec![
                    json!({"position": 1, "title": "Some Red-Handed Sleight of Hand", "recording": {"id": "rec-ugly-1", "length": 255000}}),
                    json!({"position": 2, "title": "Art Is Hard", "recording": {"id": "rec-ugly-2", "length": 160000}}),
                ],
            ),
        ] {
            seed_cache(
                conn,
                &release_candidates_cache_key(rgid),
                json!({
                    "releases": [{
                        "id": release_id,
                        "title": album_title,
                        "status": "Official",
                        "country": "US",
                        "date": "2000-06-13",
                        "media": [{"track-count": tracks.len()}]
                    }]
                }),
            );
            seed_cache(
                conn,
                &release_detail_cache_key(release_id),
                json!({"media": [{"tracks": tracks}]}),
            );
        }
    }

    #[test]
    fn canonical_single_track_acquisition_plan_creates_backend_plan_state() {
        let conn = setup_conn();

        let result = plan_single_track(
            &conn,
            "The Postal Service",
            "Such Great Heights",
            None,
            Some("manual"),
            None,
        )
        .expect("plan");

        assert_eq!(result.plan.kind, "single_track");
        assert_eq!(result.plan.status, "queued");
        assert_eq!(result.items.len(), 1);
        assert_eq!(result.items[0].status, "queued");
        assert_eq!(result.queue_items.len(), 1);
    }

    #[test]
    fn canonical_album_acquisition_plan_queues_filtered_tracks() {
        let conn = setup_conn();
        seed_cursive_catalog(&conn);

        let result = plan_album(&conn, "Cursive", "The Ugly Organ", Some("manual"), None)
            .expect("album plan");

        assert_eq!(result.plan.kind, "album");
        assert_eq!(
            result.plan.canonical_album.as_deref(),
            Some("The Ugly Organ")
        );
        assert_eq!(result.items.len(), 2);
        assert!(result.items.iter().all(|item| item.status == "queued"));
        assert_eq!(result.queue_items.len(), 2);
    }

    #[test]
    fn canonical_discography_acquisition_plan_handles_cursive_without_tribute_junk() {
        let conn = setup_conn();
        seed_cursive_catalog(&conn);

        let result = plan_discography(&conn, "Cursive", Some("manual"), None, None)
            .expect("discography plan");

        assert_eq!(result.plan.kind, "discography");
        assert_eq!(result.plan.canonical_artist.as_deref(), Some("Cursive"));
        assert_eq!(result.items.len(), 4);
        assert_eq!(result.queue_items.len(), 4);
        let album_titles = result
            .items
            .iter()
            .filter_map(|item| item.album.clone())
            .collect::<Vec<_>>();
        assert!(album_titles
            .iter()
            .all(|title| title != "A Tribute to Cursive"));
    }
}

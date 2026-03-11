use chrono::Utc;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};

use crate::audio_data;
use crate::commands::{
    AcquisitionPlanItemRecord, AcquisitionPlanRecord, AcquisitionPlanResult, AcquisitionQueueItem,
};
use crate::errors::LyraResult;
use crate::taste;

const ACTIVE_STATUSES: &[&str] = &[
    "queued",
    "validating",
    "acquiring",
    "staging",
    "scanning",
    "organizing",
    "indexing",
];

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionQueueSummary {
    pub total_count: i64,
    pub pending_count: i64,
    pub completed_count: i64,
    pub failed_count: i64,
    pub skipped_count: i64,
    pub retrying_count: i64,
    pub average_priority: f64,
    pub oldest_pending_added_at: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct AcquisitionSourceSummary {
    pub source: String,
    pub total_count: i64,
    pub pending_count: i64,
    pub completed_count: i64,
    pub failed_count: i64,
    pub average_priority: f64,
}

fn map_plan_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<AcquisitionPlanRecord> {
    Ok(AcquisitionPlanRecord {
        id: row.get(0)?,
        kind: row.get(1)?,
        status: row.get(2)?,
        source: row.get(3)?,
        requested_artist: row.get(4)?,
        requested_title: row.get(5)?,
        requested_album: row.get(6)?,
        canonical_artist: row.get(7)?,
        canonical_album: row.get(8)?,
        summary: row.get(9)?,
        total_items: row.get(10)?,
        queued_items: row.get(11)?,
        blocked_items: row.get(12)?,
        created_at: row.get(13)?,
        updated_at: row.get(14)?,
    })
}

fn map_plan_item_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<AcquisitionPlanItemRecord> {
    Ok(AcquisitionPlanItemRecord {
        id: row.get(0)?,
        plan_id: row.get(1)?,
        item_kind: row.get(2)?,
        status: row.get(3)?,
        artist: row.get(4)?,
        title: row.get(5)?,
        album: row.get(6)?,
        release_group_mbid: row.get(7)?,
        release_date: row.get(8)?,
        disc_number: row.get(9)?,
        track_number: row.get(10)?,
        queue_item_id: row.get(11)?,
        evidence_level: row.get(12)?,
        evidence_summary: row.get(13)?,
        created_at: row.get(14)?,
    })
}

fn map_acquisition_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<AcquisitionQueueItem> {
    Ok(AcquisitionQueueItem {
        id: row.get(0)?,
        artist: row.get(1)?,
        title: row.get(2)?,
        album: row.get(3)?,
        status: row.get(4)?,
        queue_position: row.get(5)?,
        priority_score: row.get(6)?,
        source: row.get(7)?,
        added_at: row.get(8)?,
        started_at: row.get(9)?,
        completed_at: row.get(10)?,
        failed_at: row.get(11)?,
        cancelled_at: row.get(12)?,
        error: row.get(13)?,
        status_message: row.get(14)?,
        failure_stage: row.get(15)?,
        failure_reason: row.get(16)?,
        failure_detail: row.get(17)?,
        retry_count: row.get(18)?,
        selected_provider: row.get(19)?,
        selected_tier: row.get(20)?,
        worker_label: row.get(21)?,
        validation_confidence: row.get(22)?,
        validation_summary: row.get(23)?,
        target_root_id: row.get(24)?,
        target_root_path: row.get(25)?,
        output_path: row.get(26)?,
        downstream_track_id: row.get(27)?,
        scan_completed: row.get::<_, i64>(28)? != 0,
        organize_completed: row.get::<_, i64>(29)? != 0,
        index_completed: row.get::<_, i64>(30)? != 0,
        cancel_requested: row.get::<_, i64>(31)? != 0,
        lifecycle_stage: row.get(32)?,
        lifecycle_progress: row.get(33)?,
        lifecycle_note: row.get(34)?,
        updated_at: row.get(35)?,
    })
}

fn queue_select_sql(where_clause: &str) -> String {
    format!(
        "SELECT id, artist, title, album, status, queue_position, priority_score, source, added_at,
                started_at, completed_at, failed_at, cancelled_at, error, status_message,
                failure_stage, failure_reason, failure_detail, retry_count, selected_provider,
                selected_tier, worker_label, validation_confidence, validation_summary,
                target_root_id, target_root_path, output_path, downstream_track_id,
                scan_completed, organize_completed, index_completed, cancel_requested,
                lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at
         FROM acquisition_queue {where_clause}
         ORDER BY
             CASE WHEN status IN ('completed', 'failed', 'cancelled') THEN 1 ELSE 0 END ASC,
             priority_score DESC,
             queue_position ASC,
             id ASC"
    )
}

fn next_queue_position(conn: &Connection) -> LyraResult<i64> {
    Ok(conn
        .query_row(
            "SELECT COALESCE(MAX(queue_position), 0) + 1 FROM acquisition_queue",
            [],
            |row| row.get(0),
        )
        .unwrap_or(1))
}

pub fn get_acquisition_item(
    conn: &Connection,
    id: i64,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    conn.query_row(
        &queue_select_sql("WHERE id = ?1"),
        params![id],
        map_acquisition_row,
    )
    .optional()
    .map_err(Into::into)
}

pub fn list_acquisition_queue(
    conn: &Connection,
    status_filter: Option<&str>,
) -> LyraResult<Vec<AcquisitionQueueItem>> {
    let sql = if status_filter.is_some() {
        queue_select_sql("WHERE status = ?1")
    } else {
        queue_select_sql("")
    };
    let mut stmt = conn.prepare(&sql)?;
    let rows = if let Some(status) = status_filter {
        stmt.query_map(params![status], map_acquisition_row)?
    } else {
        stmt.query_map([], map_acquisition_row)?
    };
    Ok(rows.filter_map(Result::ok).collect())
}

#[allow(clippy::too_many_arguments)]
pub fn add_acquisition_item(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
    source: Option<&str>,
    priority: f64,
    validation_confidence: Option<f64>,
    validation_summary: Option<&str>,
    target_root_id: Option<i64>,
    target_root_path: Option<&str>,
) -> LyraResult<AcquisitionQueueItem> {
    let now = Utc::now().to_rfc3339();
    let queue_position = next_queue_position(conn)?;
    conn.execute(
        "INSERT INTO acquisition_queue
         (artist, title, album, status, queue_position, priority_score, source, added_at,
          status_message, validation_confidence, validation_summary, target_root_id, target_root_path,
          lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at)
         VALUES (?1, ?2, ?3, 'queued', ?4, ?5, ?6, ?7, 'Queued for validation',
                 ?8, ?9, ?10, ?11, 'queued', 0.0, COALESCE(?9, 'Queued for validation'), ?7)",
        params![
            artist,
            title,
            album,
            queue_position,
            priority,
            source,
            now,
            validation_confidence,
            validation_summary,
            target_root_id,
            target_root_path
        ],
    )?;
    get_acquisition_item(conn, conn.last_insert_rowid()).map(|item| item.expect("inserted item"))
}

#[allow(clippy::too_many_arguments)]
pub fn create_acquisition_plan(
    conn: &Connection,
    kind: &str,
    source: Option<&str>,
    requested_artist: Option<&str>,
    requested_title: Option<&str>,
    requested_album: Option<&str>,
    canonical_artist: Option<&str>,
    canonical_album: Option<&str>,
    summary: &str,
) -> LyraResult<AcquisitionPlanRecord> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO acquisition_plans
         (kind, status, source, requested_artist, requested_title, requested_album,
          canonical_artist, canonical_album, summary, total_items, queued_items, blocked_items,
          created_at, updated_at)
         VALUES (?1, 'queued', ?2, ?3, ?4, ?5, ?6, ?7, ?8, 0, 0, 0, ?9, ?9)",
        params![
            kind,
            source,
            requested_artist,
            requested_title,
            requested_album,
            canonical_artist,
            canonical_album,
            summary,
            now,
        ],
    )?;
    get_acquisition_plan(conn, conn.last_insert_rowid()).map(|plan| plan.expect("inserted plan"))
}

#[allow(clippy::too_many_arguments)]
pub fn add_plan_item(
    conn: &Connection,
    plan_id: i64,
    item_kind: &str,
    status: &str,
    artist: &str,
    title: &str,
    album: Option<&str>,
    release_group_mbid: Option<&str>,
    release_date: Option<&str>,
    disc_number: Option<i64>,
    track_number: Option<i64>,
    queue_item_id: Option<i64>,
    evidence_level: &str,
    evidence_summary: &str,
) -> LyraResult<AcquisitionPlanItemRecord> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "INSERT INTO acquisition_plan_items
         (plan_id, item_kind, status, artist, title, album, release_group_mbid, release_date,
          disc_number, track_number, queue_item_id, evidence_level, evidence_summary, created_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
        params![
            plan_id,
            item_kind,
            status,
            artist,
            title,
            album,
            release_group_mbid,
            release_date,
            disc_number,
            track_number,
            queue_item_id,
            evidence_level,
            evidence_summary,
            now,
        ],
    )?;
    conn.query_row(
        "SELECT id, plan_id, item_kind, status, artist, title, album, release_group_mbid,
                release_date, disc_number, track_number, queue_item_id, evidence_level,
                evidence_summary, created_at
         FROM acquisition_plan_items
         WHERE id = ?1",
        params![conn.last_insert_rowid()],
        map_plan_item_row,
    )
    .map_err(Into::into)
}

pub fn get_acquisition_plan(
    conn: &Connection,
    id: i64,
) -> LyraResult<Option<AcquisitionPlanRecord>> {
    conn.query_row(
        "SELECT id, kind, status, source, requested_artist, requested_title, requested_album,
                canonical_artist, canonical_album, summary, total_items, queued_items,
                blocked_items, created_at, updated_at
         FROM acquisition_plans
         WHERE id = ?1",
        params![id],
        map_plan_row,
    )
    .optional()
    .map_err(Into::into)
}

pub fn finalize_acquisition_plan(
    conn: &Connection,
    plan_id: i64,
    summary: Option<&str>,
) -> LyraResult<AcquisitionPlanRecord> {
    let (total_items, queued_items, blocked_items): (i64, i64, i64) = conn.query_row(
        "SELECT COUNT(*),
                SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status != 'queued' THEN 1 ELSE 0 END)
         FROM acquisition_plan_items
         WHERE plan_id = ?1",
        params![plan_id],
        |row| {
            Ok((
                row.get(0)?,
                row.get::<_, Option<i64>>(1)?.unwrap_or_default(),
                row.get::<_, Option<i64>>(2)?.unwrap_or_default(),
            ))
        },
    )?;
    let status = if queued_items == 0 {
        "blocked"
    } else if blocked_items > 0 {
        "partial"
    } else {
        "queued"
    };
    let now = Utc::now().to_rfc3339();
    let summary = summary.map(str::to_string).unwrap_or_else(|| {
        format!("Planned {total_items} items: {queued_items} queued, {blocked_items} blocked.")
    });
    conn.execute(
        "UPDATE acquisition_plans
         SET status = ?2,
             summary = ?3,
             total_items = ?4,
             queued_items = ?5,
             blocked_items = ?6,
             updated_at = ?7
         WHERE id = ?1",
        params![
            plan_id,
            status,
            summary,
            total_items,
            queued_items,
            blocked_items,
            now
        ],
    )?;
    get_acquisition_plan(conn, plan_id)?.ok_or_else(|| {
        crate::errors::LyraError::Message("finalized acquisition plan missing".to_string())
    })
}

pub fn get_acquisition_plan_result(
    conn: &Connection,
    plan_id: i64,
) -> LyraResult<AcquisitionPlanResult> {
    let plan = get_acquisition_plan(conn, plan_id)?.ok_or_else(|| {
        crate::errors::LyraError::Message("acquisition plan not found".to_string())
    })?;
    let mut stmt = conn.prepare(
        "SELECT id, plan_id, item_kind, status, artist, title, album, release_group_mbid,
                release_date, disc_number, track_number, queue_item_id, evidence_level,
                evidence_summary, created_at
         FROM acquisition_plan_items
         WHERE plan_id = ?1
         ORDER BY COALESCE(album, ''), COALESCE(disc_number, 0), COALESCE(track_number, 0), title ASC",
    )?;
    let rows = stmt.query_map(params![plan_id], map_plan_item_row)?;
    let items = rows.filter_map(Result::ok).collect::<Vec<_>>();
    let queue_items = items
        .iter()
        .filter_map(|item| item.queue_item_id)
        .filter_map(|queue_id| get_acquisition_item(conn, queue_id).ok().flatten())
        .collect::<Vec<_>>();
    Ok(AcquisitionPlanResult {
        plan,
        items,
        queue_items,
    })
}

pub fn requeue_item(
    conn: &Connection,
    id: i64,
    note: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let queue_position = next_queue_position(conn)?;
    let message = note.unwrap_or("Retry queued");
    conn.execute(
        "UPDATE acquisition_queue
         SET status = 'queued',
             queue_position = ?2,
             started_at = NULL,
             completed_at = NULL,
             failed_at = NULL,
             cancelled_at = NULL,
             error = NULL,
             status_message = ?3,
             failure_stage = NULL,
             failure_reason = NULL,
             failure_detail = NULL,
             selected_provider = NULL,
             selected_tier = NULL,
             validation_summary = COALESCE(validation_summary, ?3),
             output_path = NULL,
             downstream_track_id = NULL,
             scan_completed = 0,
             organize_completed = 0,
             index_completed = 0,
             cancel_requested = 0,
             lifecycle_stage = 'queued',
             lifecycle_progress = 0.0,
             lifecycle_note = ?3,
             updated_at = ?4,
             retry_count = retry_count + CASE WHEN status = 'failed' THEN 1 ELSE 0 END
         WHERE id = ?1",
        params![id, queue_position, message, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn set_target_root(
    conn: &Connection,
    id: i64,
    target_root_id: Option<i64>,
    target_root_path: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET target_root_id = ?2,
             target_root_path = ?3,
             updated_at = ?4
         WHERE id = ?1",
        params![id, target_root_id, target_root_path, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn apply_validation_metadata(
    conn: &Connection,
    id: i64,
    validation_confidence: Option<f64>,
    validation_summary: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET validation_confidence = COALESCE(?2, validation_confidence),
             validation_summary = COALESCE(?3, validation_summary),
             updated_at = ?4
         WHERE id = ?1",
        params![id, validation_confidence, validation_summary, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn mark_failed(
    conn: &Connection,
    id: i64,
    stage: &str,
    reason: &str,
    detail: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET status = 'failed',
             completed_at = ?2,
             failed_at = ?2,
             error = COALESCE(?5, ?4),
             status_message = ?4,
             failure_stage = ?3,
             failure_reason = ?4,
             failure_detail = ?5,
             lifecycle_stage = ?3,
             lifecycle_progress = 1.0,
             lifecycle_note = ?4,
             updated_at = ?2
         WHERE id = ?1",
        params![id, now, stage, reason, detail],
    )?;
    get_acquisition_item(conn, id)
}

pub fn request_cancel(
    conn: &Connection,
    id: i64,
    detail: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let current = get_acquisition_item(conn, id)?;
    let Some(item) = current else {
        return Ok(None);
    };
    if item.status == "completed" || item.status == "failed" || item.status == "cancelled" {
        return Ok(Some(item));
    }
    let now = Utc::now().to_rfc3339();
    if item.status == "queued" || item.status == "validating" {
        conn.execute(
            "UPDATE acquisition_queue
             SET status = 'cancelled',
                 cancelled_at = ?2,
                 completed_at = ?2,
                 error = NULL,
                 status_message = COALESCE(?3, 'Cancelled before acquisition started'),
                 lifecycle_stage = 'cancelled',
                 lifecycle_progress = 1.0,
                 lifecycle_note = COALESCE(?3, 'Cancelled before acquisition started'),
                 updated_at = ?2,
                 cancel_requested = 0
             WHERE id = ?1",
            params![id, now, detail],
        )?;
    } else {
        conn.execute(
            "UPDATE acquisition_queue
             SET cancel_requested = 1,
                 status_message = COALESCE(?3, 'Cancellation requested'),
                 lifecycle_note = COALESCE(?3, lifecycle_note),
                 updated_at = ?2
             WHERE id = ?1",
            params![id, now, detail],
        )?;
    }
    get_acquisition_item(conn, id)
}

pub fn mark_cancelled(
    conn: &Connection,
    id: i64,
    stage: &str,
    detail: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let message = detail.unwrap_or("Cancelled");
    conn.execute(
        "UPDATE acquisition_queue
         SET status = 'cancelled',
             cancelled_at = ?2,
             completed_at = ?2,
             error = NULL,
             status_message = ?4,
             failure_stage = ?3,
             failure_reason = 'cancelled',
             failure_detail = ?4,
             lifecycle_stage = 'cancelled',
             lifecycle_progress = 1.0,
             lifecycle_note = ?4,
             updated_at = ?2,
             cancel_requested = 0
         WHERE id = ?1",
        params![id, now, stage, message],
    )?;
    get_acquisition_item(conn, id)
}

pub fn update_acquisition_status(
    conn: &Connection,
    id: i64,
    status: &str,
    error: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    match status {
        "queued" => requeue_item(conn, id, error),
        "cancelled" => request_cancel(conn, id, error),
        "failed" => mark_failed(conn, id, "manual", error.unwrap_or("Failed"), error),
        "completed" => {
            let now = Utc::now().to_rfc3339();
            conn.execute(
                "UPDATE acquisition_queue
                 SET status = 'completed',
                     completed_at = ?2,
                     error = NULL,
                     status_message = COALESCE(?3, 'Marked completed'),
                     lifecycle_stage = 'completed',
                     lifecycle_progress = 1.0,
                     lifecycle_note = COALESCE(?3, 'Marked completed'),
                     updated_at = ?2
                 WHERE id = ?1",
                params![id, now, error],
            )?;
            get_acquisition_item(conn, id)
        }
        _ => {
            let now = Utc::now().to_rfc3339();
            conn.execute(
                "UPDATE acquisition_queue
                 SET status = ?2,
                     status_message = ?3,
                     lifecycle_stage = ?2,
                     lifecycle_note = ?3,
                     updated_at = ?4
                 WHERE id = ?1",
                params![id, status, error, now],
            )?;
            get_acquisition_item(conn, id)
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub fn update_lifecycle(
    conn: &Connection,
    id: i64,
    status: &str,
    progress: f64,
    note: Option<&str>,
    provider: Option<&str>,
    tier: Option<&str>,
    worker_label: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let started_at = ACTIVE_STATUSES.contains(&status).then_some(now.clone());
    let organize_completed = if status == "organizing" { 1 } else { 0 };
    let scan_completed = if status == "scanning" { 1 } else { 0 };
    let index_completed = if status == "indexing" { 1 } else { 0 };
    conn.execute(
        "UPDATE acquisition_queue
         SET status = ?2,
             started_at = COALESCE(started_at, ?3),
             status_message = COALESCE(?4, status_message),
             selected_provider = COALESCE(?5, selected_provider),
             selected_tier = COALESCE(?6, selected_tier),
             worker_label = COALESCE(?7, worker_label),
             scan_completed = CASE WHEN ?8 = 1 THEN 1 ELSE scan_completed END,
             organize_completed = CASE WHEN ?9 = 1 THEN 1 ELSE organize_completed END,
             index_completed = CASE WHEN ?10 = 1 THEN 1 ELSE index_completed END,
             lifecycle_stage = ?2,
             lifecycle_progress = ?11,
             lifecycle_note = ?4,
             updated_at = ?12
         WHERE id = ?1",
        params![
            id,
            status,
            started_at,
            note,
            provider,
            tier,
            worker_label,
            scan_completed,
            organize_completed,
            index_completed,
            progress,
            now
        ],
    )?;
    get_acquisition_item(conn, id)
}

pub fn mark_output_path(
    conn: &Connection,
    id: i64,
    output_path: &str,
    provider: Option<&str>,
    tier: Option<&str>,
    note: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET output_path = ?2,
             selected_provider = COALESCE(?3, selected_provider),
             selected_tier = COALESCE(?4, selected_tier),
             status_message = COALESCE(?5, status_message),
             lifecycle_note = COALESCE(?5, lifecycle_note),
             updated_at = ?6
         WHERE id = ?1",
        params![id, output_path, provider, tier, note, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn mark_organize_complete(
    conn: &Connection,
    id: i64,
    output_path: &str,
    note: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET output_path = ?2,
             organize_completed = 1,
             status_message = COALESCE(?3, status_message),
             lifecycle_note = COALESCE(?3, lifecycle_note),
             updated_at = ?4
         WHERE id = ?1",
        params![id, output_path, note, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn mark_scan_complete(
    conn: &Connection,
    id: i64,
    track_id: Option<i64>,
    note: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    conn.execute(
        "UPDATE acquisition_queue
         SET scan_completed = 1,
             downstream_track_id = COALESCE(?2, downstream_track_id),
             status_message = COALESCE(?3, status_message),
             lifecycle_note = COALESCE(?3, lifecycle_note),
             updated_at = ?4
         WHERE id = ?1",
        params![id, track_id, note, now],
    )?;
    get_acquisition_item(conn, id)
}

pub fn mark_completed(
    conn: &Connection,
    id: i64,
    track_id: Option<i64>,
    note: Option<&str>,
) -> LyraResult<Option<AcquisitionQueueItem>> {
    let now = Utc::now().to_rfc3339();
    let message = note.unwrap_or("Acquisition indexed and available in library");
    conn.execute(
        "UPDATE acquisition_queue
         SET status = 'completed',
             completed_at = ?2,
             error = NULL,
             status_message = ?4,
             downstream_track_id = COALESCE(?3, downstream_track_id),
             index_completed = 1,
             lifecycle_stage = 'completed',
             lifecycle_progress = 1.0,
             lifecycle_note = ?4,
             updated_at = ?2,
             cancel_requested = 0
         WHERE id = ?1",
        params![id, now, track_id, message],
    )?;
    get_acquisition_item(conn, id)
}

pub fn cancel_requested(conn: &Connection, id: i64) -> LyraResult<bool> {
    Ok(conn
        .query_row(
            "SELECT cancel_requested FROM acquisition_queue WHERE id = ?1",
            params![id],
            |row| row.get::<_, i64>(0),
        )
        .unwrap_or(0)
        != 0)
}

pub fn clear_completed(conn: &Connection) -> LyraResult<i64> {
    let affected = conn.execute(
        "DELETE FROM acquisition_queue WHERE status IN ('completed', 'cancelled')",
        [],
    )?;
    Ok(affected as i64)
}

pub fn retry_failed(conn: &Connection) -> LyraResult<i64> {
    let failed_ids: Vec<i64> = {
        let mut stmt = conn.prepare("SELECT id FROM acquisition_queue WHERE status = 'failed'")?;
        let rows = stmt.query_map([], |row| row.get::<_, i64>(0))?;
        rows.filter_map(Result::ok).collect::<Vec<_>>()
    };
    for id in &failed_ids {
        let _ = requeue_item(conn, *id, Some("Retry queued"));
    }
    Ok(failed_ids.len() as i64)
}

pub fn set_priority(conn: &Connection, id: i64, priority_score: f64) -> LyraResult<()> {
    conn.execute(
        "UPDATE acquisition_queue SET priority_score = ?1, updated_at = ?2 WHERE id = ?3",
        params![priority_score, Utc::now().to_rfc3339(), id],
    )?;
    Ok(())
}

const GENRE_BOOSTS: &[(&str, &[(&str, f64)])] = &[
    (
        "hip-hop",
        &[("energy", 0.6), ("rawness", 0.7), ("density", 0.4)],
    ),
    (
        "rap",
        &[("energy", 0.6), ("rawness", 0.7), ("density", 0.4)],
    ),
    (
        "electronic",
        &[("energy", 0.7), ("movement", 0.8), ("tension", 0.5)],
    ),
    (
        "edm",
        &[("energy", 0.8), ("movement", 0.9), ("tension", 0.6)],
    ),
    (
        "pop",
        &[("valence", 0.7), ("warmth", 0.5), ("density", 0.3)],
    ),
    (
        "rock",
        &[("energy", 0.6), ("rawness", 0.5), ("tension", 0.4)],
    ),
    (
        "jazz",
        &[("complexity", 0.8), ("warmth", 0.6), ("nostalgia", 0.5)],
    ),
    (
        "classical",
        &[("complexity", 0.9), ("space", 0.8), ("tension", 0.3)],
    ),
    (
        "r&b",
        &[("warmth", 0.7), ("valence", 0.6), ("movement", 0.5)],
    ),
    (
        "soul",
        &[("warmth", 0.8), ("rawness", 0.4), ("nostalgia", 0.6)],
    ),
    (
        "ambient",
        &[("space", 0.9), ("energy", 0.1), ("tension", 0.1)],
    ),
    (
        "metal",
        &[("energy", 0.9), ("rawness", 0.9), ("tension", 0.8)],
    ),
    (
        "indie",
        &[("rawness", 0.5), ("nostalgia", 0.4), ("complexity", 0.4)],
    ),
    (
        "folk",
        &[("warmth", 0.7), ("nostalgia", 0.6), ("rawness", 0.4)],
    ),
    (
        "blues",
        &[("rawness", 0.6), ("warmth", 0.7), ("nostalgia", 0.7)],
    ),
];

const DIMS: &[&str] = &[
    "energy",
    "valence",
    "tension",
    "density",
    "warmth",
    "movement",
    "space",
    "rawness",
    "complexity",
    "nostalgia",
];

pub fn compute_initial_priority(
    conn: &Connection,
    artist: &str,
    title: &str,
    album: Option<&str>,
    source: Option<&str>,
) -> LyraResult<f64> {
    let taste = taste::get_taste_profile(conn)?;
    if taste.dimensions.is_empty() {
        return Ok(default_priority_for_source(source));
    }

    let mut statement = conn.prepare(
        "SELECT
            AVG(ts.energy), AVG(ts.valence), AVG(ts.tension), AVG(ts.density),
            AVG(ts.warmth), AVG(ts.movement), AVG(ts.space), AVG(ts.rawness),
            AVG(ts.complexity), AVG(ts.nostalgia)
         FROM track_scores ts
         JOIN tracks t ON t.id = ts.track_id
         LEFT JOIN artists ar ON ar.id = t.artist_id
         WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
           AND ts.energy IS NOT NULL",
    )?;
    let artist_scores: Option<[Option<f64>; 10]> = statement
        .query_row(params![artist], |row| {
            Ok([
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
                row.get(7)?,
                row.get(8)?,
                row.get(9)?,
            ])
        })
        .optional()?;

    let mut candidate = std::collections::HashMap::new();
    if let Some(Some(_)) = artist_scores.as_ref().map(|scores| scores[0]) {
        for (dim, value) in DIMS
            .iter()
            .zip(artist_scores.expect("artist scores present"))
        {
            candidate.insert((*dim).to_string(), value.unwrap_or(0.5));
        }
    } else {
        for dim in DIMS {
            candidate.insert((*dim).to_string(), 0.5);
        }
        let genre_hint = format!("{} {}", album.unwrap_or_default(), title).to_ascii_lowercase();
        for (keyword, boosts) in GENRE_BOOSTS {
            if genre_hint.contains(keyword) {
                for (dim, boost) in *boosts {
                    candidate.insert((*dim).to_string(), *boost);
                }
            }
        }
    }

    let dims = taste
        .dimensions
        .keys()
        .filter(|dim| candidate.contains_key(*dim))
        .collect::<Vec<_>>();
    if dims.is_empty() {
        return Ok(default_priority_for_source(source));
    }

    let dot = dims
        .iter()
        .map(|dim| taste.dimensions[*dim] * candidate[dim.as_str()])
        .sum::<f64>();
    let mag_a = dims
        .iter()
        .map(|dim| taste.dimensions[*dim].powi(2))
        .sum::<f64>()
        .sqrt();
    let mag_b = dims
        .iter()
        .map(|dim| candidate[dim.as_str()].powi(2))
        .sum::<f64>()
        .sqrt();
    if mag_a == 0.0 || mag_b == 0.0 {
        return Ok(default_priority_for_source(source));
    }
    let similarity = (dot / (mag_a * mag_b)).clamp(0.0, 1.0);
    let source_bias = match source.unwrap_or("manual") {
        "recommendation" | "bridge" | "discover" => 0.35,
        "spotify_liked" | "wishlist" => 0.2,
        _ => 0.0,
    };
    Ok((1.0 + similarity * 8.5 + source_bias).clamp(1.0, 9.5))
}

fn default_priority_for_source(source: Option<&str>) -> f64 {
    match source.unwrap_or("manual") {
        "recommendation" | "bridge" | "discover" => 6.2,
        "spotify_liked" | "wishlist" => 5.6,
        _ => 5.0,
    }
}

pub fn move_queue_item(conn: &Connection, id: i64, new_position: i64) -> LyraResult<()> {
    let mut ids = list_acquisition_queue(conn, None)?
        .into_iter()
        .map(|item| item.id)
        .collect::<Vec<_>>();
    let Some(current_idx) = ids.iter().position(|candidate| *candidate == id) else {
        return Ok(());
    };
    let target_idx = new_position.clamp(0, ids.len().saturating_sub(1) as i64) as usize;
    let item_id = ids.remove(current_idx);
    ids.insert(target_idx, item_id);
    for (index, item_id) in ids.iter().enumerate() {
        conn.execute(
            "UPDATE acquisition_queue SET queue_position = ?1 WHERE id = ?2",
            params![index as i64 + 1, item_id],
        )?;
    }
    Ok(())
}

pub fn pending_count(conn: &Connection) -> i64 {
    conn.query_row(
        "SELECT COUNT(*) FROM acquisition_queue
         WHERE status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing')",
        [],
        |row| row.get(0),
    )
    .unwrap_or(0)
}

pub fn summarize_acquisition_queue(conn: &Connection) -> LyraResult<AcquisitionQueueSummary> {
    Ok(conn.query_row(
        "SELECT COUNT(*),
                SUM(CASE WHEN status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing') THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END),
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END),
                SUM(CASE WHEN retry_count > 0 AND status != 'completed' THEN 1 ELSE 0 END),
                AVG(priority_score),
                MIN(CASE WHEN status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing') THEN added_at ELSE NULL END)
         FROM acquisition_queue",
        [],
        |row| {
            Ok(AcquisitionQueueSummary {
                total_count: row.get(0)?,
                pending_count: row.get(1)?,
                completed_count: row.get(2)?,
                failed_count: row.get(3)?,
                skipped_count: row.get(4)?,
                retrying_count: row.get(5)?,
                average_priority: row.get::<_, Option<f64>>(6)?.unwrap_or(0.0),
                oldest_pending_added_at: row.get(7)?,
            })
        },
    )?)
}

pub fn list_acquisition_sources(conn: &Connection) -> LyraResult<Vec<AcquisitionSourceSummary>> {
    let mut stmt = conn.prepare(
        "SELECT COALESCE(NULLIF(source, ''), 'manual') AS source_key,
                COUNT(*) AS total_count,
                SUM(CASE WHEN status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing') THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                AVG(priority_score) AS average_priority
         FROM acquisition_queue
         GROUP BY source_key
         ORDER BY pending_count DESC, average_priority DESC, source_key ASC",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(AcquisitionSourceSummary {
            source: row.get(0)?,
            total_count: row.get(1)?,
            pending_count: row.get(2)?,
            completed_count: row.get(3)?,
            failed_count: row.get(4)?,
            average_priority: row.get::<_, Option<f64>>(5)?.unwrap_or(0.0),
        })
    })?;
    Ok(rows.filter_map(Result::ok).collect())
}

pub fn import_queue_from_legacy(conn: &Connection, legacy: &Connection) -> LyraResult<usize> {
    let mut stmt = legacy.prepare(
        "SELECT artist, title, album, priority_score, source, added_at
         FROM acquisition_queue WHERE status IN ('pending', 'queued')",
    )?;
    let rows: Vec<_> = stmt
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, Option<String>>(2)?,
                row.get::<_, Option<f64>>(3)?,
                row.get::<_, Option<String>>(4)?,
                row.get::<_, Option<String>>(5)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();
    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;
    for (artist, title, album, priority, source, added_at) in rows {
        let exists: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM acquisition_queue WHERE artist = ?1 AND title = ?2 AND status IN ('queued', 'validating', 'acquiring', 'staging', 'scanning', 'organizing', 'indexing')",
                params![artist, title],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if exists > 0 {
            continue;
        }
        let queue_position = next_queue_position(conn)?;
        conn.execute(
            "INSERT INTO acquisition_queue
             (artist, title, album, status, queue_position, priority_score, source, added_at, status_message, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at)
             VALUES (?1, ?2, ?3, 'queued', ?4, ?5, ?6, ?7, 'Imported from legacy queue', 'queued', 0.0, 'Imported from legacy queue', ?7)",
            params![
                artist,
                title,
                album,
                queue_position,
                priority.unwrap_or(0.0),
                source,
                added_at.unwrap_or_else(|| now.clone()),
            ],
        )?;
        count += 1;
    }
    Ok(count)
}

type SpotifyLibraryRow = (
    String,
    String,
    Option<String>,
    Option<String>,
    Option<i64>,
    Option<i64>,
    Option<i64>,
);

pub fn import_spotify_library_as_queue(
    conn: &Connection,
    source: &Connection,
) -> LyraResult<usize> {
    let mut stmt = source.prepare(
        "SELECT sl.artist, sl.title, sl.album, sl.isrc, sl.duration_ms, sl.popularity, sl.explicit
         FROM spotify_library sl
         WHERE COALESCE(sl.source, 'liked') = 'liked'",
    )?;
    let rows: Vec<SpotifyLibraryRow> = stmt
        .query_map([], |row| {
            Ok((
                row.get(0)?,
                row.get(1)?,
                row.get(2)?,
                row.get(3)?,
                row.get(4)?,
                row.get(5)?,
                row.get(6)?,
            ))
        })?
        .filter_map(Result::ok)
        .collect();
    let now = Utc::now().to_rfc3339();
    let mut count = 0_usize;
    for (artist, title, album, isrc, duration_ms, popularity, explicit) in rows {
        let normalized =
            match audio_data::normalize_track_candidate(audio_data::RawTrackCandidate {
                provider: "spotify",
                provider_track_id: &audio_data::provider_track_key(
                    "spotify",
                    &artist,
                    &title,
                    isrc.as_deref(),
                ),
                artist: &artist,
                title: &title,
                album: album.as_deref(),
                release_date: None,
                isrc: isrc.as_deref(),
                duration_ms,
                popularity,
                explicit: explicit.unwrap_or(0) != 0,
            }) {
                Ok(track) => track,
                Err(_) => continue,
            };

        let owned: i64 = conn.query_row(
            "SELECT COUNT(*)
             FROM tracks t
             LEFT JOIN artists ar ON ar.id = t.artist_id
             WHERE lower(trim(COALESCE(ar.name, ''))) = lower(trim(?1))
               AND lower(trim(COALESCE(t.title, ''))) = lower(trim(?2))",
            params![normalized.artist.name, normalized.title],
            |row| row.get(0),
        )?;
        if owned > 0 {
            continue;
        }

        let exists: i64 = conn
            .query_row(
                "SELECT COUNT(*) FROM acquisition_queue WHERE artist = ?1 AND title = ?2",
                params![normalized.artist.name, normalized.title],
                |row| row.get(0),
            )
            .unwrap_or(0);
        if exists > 0 {
            continue;
        }
        let queue_position = next_queue_position(conn)?;
        conn.execute(
            "INSERT INTO acquisition_queue
             (artist, title, album, status, queue_position, priority_score, source, added_at, status_message, lifecycle_stage, lifecycle_progress, lifecycle_note, updated_at)
             VALUES (?1, ?2, ?3, 'queued', ?4, 0.3, 'spotify_liked', ?5, 'Imported from Spotify liked library', 'queued', 0.0, 'Imported from Spotify liked library', ?5)",
            params![
                normalized.artist.name,
                normalized.title,
                normalized.album.as_ref().map(|value| value.title.as_str()),
                queue_position,
                now
            ],
        )?;
        let _ = audio_data::persist_provider_track(
            conn,
            &normalized,
            "library",
            &serde_json::json!({
                "artist": artist,
                "title": title,
                "album": album,
                "isrc": isrc,
                "durationMs": duration_ms,
                "popularity": popularity,
                "explicit": explicit,
                "source": "spotify_liked",
            }),
        );
        count += 1;
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use rusqlite::{params, Connection};

    use super::{
        add_acquisition_item, list_acquisition_queue, list_acquisition_sources, move_queue_item,
        request_cancel, requeue_item, summarize_acquisition_queue, update_acquisition_status,
        update_lifecycle,
    };

    fn setup_conn() -> Connection {
        let conn = Connection::open_in_memory().expect("in-memory sqlite");
        conn.execute_batch(
            "
            CREATE TABLE acquisition_queue (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              artist TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL DEFAULT '',
              album TEXT,
              status TEXT NOT NULL DEFAULT 'queued',
              queue_position INTEGER NOT NULL DEFAULT 0,
              priority_score REAL NOT NULL DEFAULT 0.0,
              source TEXT,
              added_at TEXT NOT NULL,
              started_at TEXT,
              completed_at TEXT,
              failed_at TEXT,
              cancelled_at TEXT,
              error TEXT,
              status_message TEXT,
              failure_stage TEXT,
              failure_reason TEXT,
              failure_detail TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              selected_provider TEXT,
              selected_tier TEXT,
              worker_label TEXT,
              validation_confidence REAL,
              validation_summary TEXT,
              target_root_id INTEGER,
              target_root_path TEXT,
              output_path TEXT,
              downstream_track_id INTEGER,
              scan_completed INTEGER NOT NULL DEFAULT 0,
              organize_completed INTEGER NOT NULL DEFAULT 0,
              index_completed INTEGER NOT NULL DEFAULT 0,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              lifecycle_stage TEXT,
              lifecycle_progress REAL,
              lifecycle_note TEXT,
              updated_at TEXT
            );
            ",
        )
        .expect("queue schema");
        conn
    }

    #[test]
    fn summarizes_queue_state() {
        let conn = setup_conn();
        let rows = [
            (
                "A",
                "One",
                Some("Album"),
                "queued",
                1_i64,
                0.9,
                Some("wishlist"),
                "2026-03-08T01:00:00Z",
                0_i64,
            ),
            (
                "B",
                "Two",
                None,
                "failed",
                2_i64,
                0.6,
                Some("manual"),
                "2026-03-08T02:00:00Z",
                2_i64,
            ),
            (
                "C",
                "Three",
                None,
                "completed",
                3_i64,
                0.4,
                Some("recommendation"),
                "2026-03-08T04:00:00Z",
                1_i64,
            ),
            (
                "D",
                "Four",
                None,
                "cancelled",
                4_i64,
                0.2,
                None,
                "2026-03-08T06:00:00Z",
                0_i64,
            ),
        ];

        for (
            artist,
            title,
            album,
            status,
            queue_position,
            priority,
            source,
            added_at,
            retry_count,
        ) in rows
        {
            conn.execute(
                "INSERT INTO acquisition_queue
                 (artist, title, album, status, queue_position, priority_score, source, added_at, retry_count)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)",
                params![artist, title, album, status, queue_position, priority, source, added_at, retry_count],
            )
            .expect("insert acquisition row");
        }

        let summary = summarize_acquisition_queue(&conn).expect("summary");
        assert_eq!(summary.total_count, 4);
        assert_eq!(summary.pending_count, 1);
        assert_eq!(summary.completed_count, 1);
        assert_eq!(summary.failed_count, 1);
        assert_eq!(summary.skipped_count, 1);
        assert_eq!(summary.retrying_count, 1);
        assert_eq!(
            summary.oldest_pending_added_at.as_deref(),
            Some("2026-03-08T01:00:00Z")
        );
        assert!((summary.average_priority - 0.525).abs() < f64::EPSILON);
    }

    #[test]
    fn groups_queue_by_source() {
        let conn = setup_conn();
        let rows = [
            ("A", "One", "queued", 1_i64, 0.9, Some("wishlist")),
            ("B", "Two", "failed", 2_i64, 0.6, Some("wishlist")),
            ("C", "Three", "completed", 3_i64, 0.3, Some("manual")),
            ("D", "Four", "queued", 4_i64, 0.5, None),
        ];

        for (artist, title, status, queue_position, priority, source) in rows {
            conn.execute(
                "INSERT INTO acquisition_queue
                 (artist, title, status, queue_position, priority_score, source, added_at, retry_count)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, '2026-03-08T01:00:00Z', 0)",
                params![artist, title, status, queue_position, priority, source],
            )
            .expect("insert acquisition row");
        }

        let sources = list_acquisition_sources(&conn).expect("source summary");
        assert_eq!(sources.len(), 2);
        assert_eq!(sources[0].source, "wishlist");
        assert_eq!(sources[0].total_count, 2);
        assert_eq!(sources[0].pending_count, 1);
        assert_eq!(sources[0].failed_count, 1);
        assert_eq!(sources[1].source, "manual");
        assert_eq!(sources[1].total_count, 2);
        assert_eq!(sources[1].completed_count, 1);
        assert_eq!(sources[1].pending_count, 1);
    }

    #[test]
    fn retrying_failed_item_increments_retry_and_clears_error() {
        let conn = setup_conn();
        let item = add_acquisition_item(
            &conn,
            "A",
            "One",
            None,
            Some("manual"),
            0.8,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("item inserted");
        let failed = update_acquisition_status(&conn, item.id, "failed", Some("boom"))
            .expect("failed update")
            .expect("item present");
        assert_eq!(failed.status, "failed");
        assert_eq!(failed.retry_count, 0);
        assert_eq!(failed.error.as_deref(), Some("boom"));
        assert!(failed.completed_at.is_some());

        let retried = requeue_item(&conn, item.id, Some("Retry queued"))
            .expect("retry update")
            .expect("item present");
        assert_eq!(retried.status, "queued");
        assert_eq!(retried.retry_count, 1);
        assert_eq!(retried.error, None);
        assert_eq!(retried.completed_at, None);
        assert_eq!(retried.lifecycle_stage.as_deref(), Some("queued"));
        assert_eq!(retried.lifecycle_progress, Some(0.0));
        assert_eq!(retried.lifecycle_note.as_deref(), Some("Retry queued"));
    }

    #[test]
    fn queued_item_cancels_immediately() {
        let conn = setup_conn();
        let item = add_acquisition_item(
            &conn,
            "A",
            "One",
            None,
            Some("manual"),
            0.5,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("item inserted");
        let cancelled = request_cancel(&conn, item.id, Some("User cancelled"))
            .expect("cancel update")
            .expect("item present");
        assert_eq!(cancelled.status, "cancelled");
        assert!(!cancelled.cancel_requested);
        assert!(cancelled.cancelled_at.is_some());
    }

    #[test]
    fn active_item_sets_cancel_request() {
        let conn = setup_conn();
        let item = add_acquisition_item(
            &conn,
            "A",
            "One",
            None,
            Some("manual"),
            0.5,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("item inserted");
        let _ = update_lifecycle(
            &conn,
            item.id,
            "acquiring",
            0.3,
            Some("Running"),
            Some("qobuz"),
            Some("T1"),
            Some("manual"),
        )
        .expect("transition");
        let cancelled = request_cancel(&conn, item.id, Some("User cancelled"))
            .expect("cancel update")
            .expect("item present");
        assert_eq!(cancelled.status, "acquiring");
        assert!(cancelled.cancel_requested);
    }

    #[test]
    fn move_queue_item_reorders_positions() {
        let conn = setup_conn();
        let first = add_acquisition_item(
            &conn,
            "A",
            "One",
            None,
            Some("manual"),
            0.6,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("first");
        let second = add_acquisition_item(
            &conn,
            "B",
            "Two",
            None,
            Some("manual"),
            0.6,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("second");
        let third = add_acquisition_item(
            &conn,
            "C",
            "Three",
            None,
            Some("manual"),
            0.6,
            Some(0.7),
            Some("validated"),
            None,
            None,
        )
        .expect("third");
        move_queue_item(&conn, third.id, 0).expect("move");
        let ids = list_acquisition_queue(&conn, None)
            .expect("queue")
            .into_iter()
            .map(|item| item.id)
            .collect::<Vec<_>>();
        assert_eq!(ids, vec![third.id, first.id, second.id]);
    }
}

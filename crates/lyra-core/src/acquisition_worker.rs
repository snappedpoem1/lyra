/// Background acquisition worker.
///
/// Polls the acquisition queue and processes items automatically.
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::Duration;
use tracing::{info, warn};

use crate::acquisition_dispatcher;
use crate::config::AppPaths;

/// Global flag to control the worker thread.
static WORKER_RUNNING: AtomicBool = AtomicBool::new(false);

/// Start the background acquisition worker.
///
/// The worker polls the acquisition queue every 30 seconds and processes
/// the next pending item if one exists.
///
/// Returns true if the worker was started, false if already running.
pub fn start_worker(paths: AppPaths) -> bool {
    if WORKER_RUNNING.swap(true, Ordering::SeqCst) {
        warn!("Acquisition worker already running");
        return false;
    }

    info!("Starting acquisition background worker");
    
    thread::spawn(move || {
        while WORKER_RUNNING.load(Ordering::SeqCst) {
            match acquisition_dispatcher::process_next_queue_item(&paths) {
                Ok(true) => {
                    info!("Processed acquisition queue item");
                    // After processing, wait a bit before checking again
                    thread::sleep(Duration::from_secs(5));
                }
                Ok(false) => {
                    // Queue empty, wait longer before checking again
                    thread::sleep(Duration::from_secs(30));
                }
                Err(e) => {
                    warn!("Acquisition worker error: {}", e);
                    thread::sleep(Duration::from_secs(60));
                }
            }
        }
        info!("Acquisition worker stopped");
    });

    true
}

/// Stop the background acquisition worker.
pub fn stop_worker() {
    if WORKER_RUNNING.swap(false, Ordering::SeqCst) {
        info!("Stopping acquisition worker");
    }
}

/// Check if the worker is currently running.
pub fn is_running() -> bool {
    WORKER_RUNNING.load(Ordering::SeqCst)
}

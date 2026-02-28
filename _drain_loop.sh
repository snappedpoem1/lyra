#!/usr/bin/env bash
cd /c/MusicOracle
LOGFILE="logs/drain_loop.log"
mkdir -p logs

log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$LOGFILE"; }

BATCH=75
WORKERS=3
MAX_TIER=5

log "=== Drain loop started. Batch=$BATCH Workers=$WORKERS MaxTier=$MAX_TIER ==="

while true; do
    # How many pending?
    PENDING=$(py -3.12 -c "
from oracle.db.schema import get_connection
c=get_connection().cursor()
c.execute(\"SELECT COUNT(*) FROM acquisition_queue WHERE status='pending'\")
print(c.fetchone()[0])
" 2>/dev/null)

    log "--- Pending: $PENDING ---"
    if [ "$PENDING" -eq 0 ]; then
        log "Queue empty. Done."
        break
    fi

    log "Draining batch of $BATCH (auto-ingest enabled)..."
    py -3.12 -m oracle.cli drain --limit $BATCH --workers $WORKERS --max-tier $MAX_TIER >> "$LOGFILE" 2>&1

    log "Batch complete. Sleeping 5s before next batch..."
    sleep 5
done

log "=== Drain loop finished ==="

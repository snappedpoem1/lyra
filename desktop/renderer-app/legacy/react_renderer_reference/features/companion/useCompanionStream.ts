import { useEffect, useRef, useState } from "react";
import { resolveApiUrl } from "@/services/lyraGateway/client";

export interface CompanionPulseEvent {
  event_type: string;
  context: Record<string, string>;
  at?: number;
}

/**
 * Subscribe to the /ws/companion SSE stream.
 * Returns the most recent companion pulse event, or null before the first event.
 * Re-connects automatically after an error with a 3-second back-off.
 */
export function useCompanionStream(): CompanionPulseEvent | null {
  const [lastEvent, setLastEvent] = useState<CompanionPulseEvent | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;

    function connect() {
      if (!activeRef.current) return;
      if (typeof window === "undefined" || typeof window.EventSource === "undefined") return;

      const source = new window.EventSource(resolveApiUrl("/ws/companion"));
      sourceRef.current = source;

      source.onmessage = (ev) => {
        if (!activeRef.current) return;
        try {
          const raw = JSON.parse(ev.data) as unknown;
          if (raw && typeof raw === "object" && "event_type" in raw) {
            setLastEvent(raw as CompanionPulseEvent);
          }
        } catch {
          // malformed frame — ignore
        }
      };

      source.onerror = () => {
        source.close();
        sourceRef.current = null;
        if (activeRef.current) {
          retryTimer.current = setTimeout(connect, 3000);
        }
      };
    }

    connect();

    return () => {
      activeRef.current = false;
      if (retryTimer.current !== null) {
        clearTimeout(retryTimer.current);
        retryTimer.current = null;
      }
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, []);

  return lastEvent;
}

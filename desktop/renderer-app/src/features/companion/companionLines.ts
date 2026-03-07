/**
 * Companion Pulse authored line templates.
 *
 * Each key maps to a function that receives the event ``context`` object and
 * returns a display string for the companion panel.  Keys match the
 * ``event_type`` values published by the backend ``CompanionPulse``.
 */

type LineFactory = (ctx: Record<string, string>) => string;

export const COMPANION_LINES: Record<string, LineFactory> = {
  track_started: ({ artist, title }) =>
    artist && title ? `Now: ${artist} — ${title}` : "Listening thread is active.",
  track_finished: ({ artist }) =>
    artist ? `${artist} just completed.` : "Track finished.",
  queue_empty: () => "The queue is open. Oracle is ready.",
  paused: () => "Queue held in orbit.",
  resumed: () => "Listening thread resumed.",
  provider_degraded: ({ provider }) =>
    provider ? `${provider} signal weakened.` : "A signal has weakened.",
  provider_recovered: ({ provider }) =>
    provider ? `${provider} signal restored.` : "Signal restored.",
  acquisition_queued: ({ artist, title }) =>
    artist && title ? `Queued: ${artist} — ${title}.` : "Acquisition queued.",
};

/**
 * Resolve a companion display line from a pulse event.
 * Returns ``null`` if the event type has no authored line.
 */
export function resolveCompanionLine(
  eventType: string,
  context: Record<string, string>,
): string | null {
  const factory = COMPANION_LINES[eventType];
  return factory ? factory(context) : null;
}

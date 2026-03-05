import { BackendStatusPanel } from "@/features/system/BackendStatusPanel";
import { DoctorPanel } from "@/features/system/DoctorPanel";
import { useSettingsStore } from "@/stores/settingsStore";

export function SettingsRoute() {
  const apiBaseUrl      = useSettingsStore((state) => state.apiBaseUrl);
  const apiToken        = useSettingsStore((state) => state.apiToken);
  const fixtureMode     = useSettingsStore((state) => state.fixtureMode);
  const developerHud    = useSettingsStore((state) => state.developerHud);
  const resumeSession   = useSettingsStore((state) => state.resumeSession);
  const setApiBaseUrl   = useSettingsStore((state) => state.setApiBaseUrl);
  const setApiToken     = useSettingsStore((state) => state.setApiToken);
  const setFixtureMode  = useSettingsStore((state) => state.setFixtureMode);
  const setDeveloperHud = useSettingsStore((state) => state.setDeveloperHud);
  const setResumeSession = useSettingsStore((state) => state.setResumeSession);

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Settings</span>
        <h1>Configuration &amp; System</h1>
        <p>Backend services, diagnostics, and honest offline behavior.</p>
      </section>

      <section className="lyra-panel">
        <form className="settings-form" onSubmit={(e) => e.preventDefault()}>
          <div className="settings-section">
            <h3 className="settings-section-title">Backend</h3>

            <div className="settings-field">
              <label className="settings-label" htmlFor="api-base-url">Backend URL</label>
              <input
                id="api-base-url"
                className="settings-input"
                value={apiBaseUrl}
                onChange={(e) => setApiBaseUrl(e.target.value)}
                placeholder="http://127.0.0.1:5000"
                spellCheck={false}
              />
              <span className="settings-hint">Flask API address. Change if running on a non-default port.</span>
            </div>

            <div className="settings-field">
              <label className="settings-label" htmlFor="api-token">API Token</label>
              <input
                id="api-token"
                className="settings-input"
                value={apiToken}
                onChange={(e) => setApiToken(e.target.value)}
                placeholder="Optional bearer token"
                spellCheck={false}
              />
              <span className="settings-hint">Leave blank for local-only setups.</span>
            </div>
          </div>

          <div className="settings-section">
            <h3 className="settings-section-title">Behavior</h3>

            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={fixtureMode}
                onChange={(e) => setFixtureMode(e.target.checked)}
              />
              <span>
                <span className="settings-label">Fixture mode</span>
                <span className="settings-hint">Use static sample data when the backend is unreachable.</span>
              </span>
            </label>

            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={resumeSession}
                onChange={(e) => setResumeSession(e.target.checked)}
              />
              <span>
                <span className="settings-label">Restore last queue on launch</span>
                <span className="settings-hint">Pick up where you left off, including track position.</span>
              </span>
            </label>

            <label className="settings-checkbox-row">
              <input
                type="checkbox"
                className="settings-checkbox"
                checked={developerHud}
                onChange={(e) => setDeveloperHud(e.target.checked)}
              />
              <span>
                <span className="settings-label">Developer HUD</span>
                <span className="settings-hint">Overlay showing store state and API latency.</span>
              </span>
            </label>
          </div>

          <div className="settings-section">
            <h3 className="settings-section-title">Keyboard Shortcuts</h3>
            <div className="settings-shortcuts-grid">
              {([
                ["Ctrl K",  "Open command palette"],
                ["/",       "Quick search"],
                ["Space",   "Play / Pause"],
                ["J",       "Previous track"],
                ["K",       "Next track"],
                ["M",       "Toggle mute"],
                ["← →",    "Seek ±5 s"],
                ["Esc",     "Close overlays"],
              ] as [string, string][]).map(([key, desc]) => (
                <div key={key} className="settings-shortcut-row">
                  <span className="kbd">{key}</span>
                  <span className="settings-shortcut-desc">{desc}</span>
                </div>
              ))}
            </div>
          </div>
        </form>
      </section>

      <BackendStatusPanel />
      <DoctorPanel />
    </div>
  );
}

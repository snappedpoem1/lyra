import { BackendStatusPanel } from "@/features/system/BackendStatusPanel";
import { useSettingsStore } from "@/stores/settingsStore";

export function SettingsRoute() {
  const apiBaseUrl = useSettingsStore((state) => state.apiBaseUrl);
  const apiToken = useSettingsStore((state) => state.apiToken);
  const fixtureMode = useSettingsStore((state) => state.fixtureMode);
  const developerHud = useSettingsStore((state) => state.developerHud);
  const setApiBaseUrl = useSettingsStore((state) => state.setApiBaseUrl);
  const setApiToken = useSettingsStore((state) => state.setApiToken);
  const setFixtureMode = useSettingsStore((state) => state.setFixtureMode);
  const setDeveloperHud = useSettingsStore((state) => state.setDeveloperHud);

  return (
    <div className="route-stack">
      <section className="lyra-panel page-intro">
        <span className="hero-kicker">Settings</span>
        <h1>Configuration and system operations</h1>
        <p>Backend services, diagnostics, and honest offline behavior.</p>
      </section>
      <section className="lyra-panel settings-form">
        <label>
          Backend URL
          <input value={apiBaseUrl} onChange={(event) => setApiBaseUrl(event.target.value)} />
        </label>
        <label>
          API token
          <input value={apiToken} onChange={(event) => setApiToken(event.target.value)} placeholder="optional bearer token" />
        </label>
        <label>
          <input type="checkbox" checked={fixtureMode} onChange={(event) => setFixtureMode(event.target.checked)} />
          Enable fixture mode when backend is unreachable
        </label>
        <label>
          <input type="checkbox" checked={developerHud} onChange={(event) => setDeveloperHud(event.target.checked)} />
          Show developer HUD
        </label>
      </section>
      <BackendStatusPanel />
    </div>
  );
}

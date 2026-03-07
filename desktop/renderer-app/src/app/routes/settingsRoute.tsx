import { Badge, Card, Checkbox, Group, SegmentedControl, Stack, Text, TextInput, Title } from "@mantine/core";
import { BackendStatusPanel } from "@/features/system/BackendStatusPanel";
import { DoctorPanel } from "@/features/system/DoctorPanel";
import { useSettingsStore } from "@/stores/settingsStore";
import { LyraPanel } from "@/ui/LyraPanel";

const SHORTCUTS: Array<[string, string]> = [
  ["Ctrl K", "Open command palette"],
  ["/", "Quick search"],
  ["Space", "Play / Pause"],
  ["J", "Previous track"],
  ["K", "Next track"],
  ["M", "Toggle mute"],
  ["Left / Right", "Seek +/- 5 s"],
  ["Esc", "Close overlays"],
];

export function SettingsRoute() {
  const apiBaseUrl = useSettingsStore((state) => state.apiBaseUrl);
  const apiToken = useSettingsStore((state) => state.apiToken);
  const fixtureMode = useSettingsStore((state) => state.fixtureMode);
  const developerHud = useSettingsStore((state) => state.developerHud);
  const resumeSession = useSettingsStore((state) => state.resumeSession);
  const companionEnabled = useSettingsStore((state) => state.companionEnabled);
  const companionStyle = useSettingsStore((state) => state.companionStyle);
  const setApiBaseUrl = useSettingsStore((state) => state.setApiBaseUrl);
  const setApiToken = useSettingsStore((state) => state.setApiToken);
  const setFixtureMode = useSettingsStore((state) => state.setFixtureMode);
  const setDeveloperHud = useSettingsStore((state) => state.setDeveloperHud);
  const setResumeSession = useSettingsStore((state) => state.setResumeSession);
  const setCompanionEnabled = useSettingsStore((state) => state.setCompanionEnabled);
  const setCompanionStyle = useSettingsStore((state) => state.setCompanionStyle);
  const enabledBehaviorCount = [fixtureMode, resumeSession, developerHud, companionEnabled].filter(Boolean).length;

  return (
    <div className="route-stack">
      <LyraPanel className="settings-system-hero">
        <div className="settings-system-copy">
          <span className="hero-kicker">Settings</span>
          <Title order={1}>Configuration, diagnostics, and shell behavior from one system deck.</Title>
          <Text className="settings-system-summary">
            Control runtime posture, recovery choices, shell presence, and diagnostics
            without scattering those decisions across multiple temporary surfaces.
          </Text>
        </div>
        <Group gap="xs" className="settings-system-badges">
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {enabledBehaviorCount} toggles active
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="midnight">
            {apiToken ? "token configured" : "token optional"}
          </Badge>
          <Badge className="home-stat-badge" size="lg" variant="light" color="lyra">
            {companionEnabled ? `companion: ${companionStyle}` : "companion hidden"}
          </Badge>
        </Group>
      </LyraPanel>

      <section className="settings-signal-grid">
        <LyraPanel className="settings-signal-card">
          <span className="insight-kicker">Runtime target</span>
          <strong>{apiBaseUrl || "No backend URL set"}</strong>
          <p>Primary shell, diagnostics, and control traffic point here.</p>
        </LyraPanel>
        <LyraPanel className="settings-signal-card">
          <span className="insight-kicker">Recovery posture</span>
          <strong>{resumeSession ? "Resume queue and position" : "Launch clean"}</strong>
          <p>Controls how much listening context Lyra restores after a restart.</p>
        </LyraPanel>
        <LyraPanel className="settings-signal-card">
          <span className="insight-kicker">Diagnostics mode</span>
          <strong>{developerHud ? "Developer HUD live" : "Panel-only diagnostics"}</strong>
          <p>System truth lives in the panels below, not in ad hoc scattered indicators.</p>
        </LyraPanel>
      </section>

      <section className="settings-grid">
        <Card className="lyra-panel settings-card" padding="xl">
          <Stack gap="lg">
            <div>
              <Title order={3} className="settings-section-title">Backend</Title>
              <Text className="settings-hint">Core transport and auth settings for the Flask API.</Text>
            </div>
            <TextInput
              label="Backend URL"
              value={apiBaseUrl}
              onChange={(event) => setApiBaseUrl(event.currentTarget.value)}
              placeholder="http://127.0.0.1:5000"
              spellCheck={false}
              className="settings-input-wrap"
            />
            <TextInput
              label="API Token"
              value={apiToken}
              onChange={(event) => setApiToken(event.currentTarget.value)}
              placeholder="Optional bearer token"
              spellCheck={false}
              className="settings-input-wrap"
            />
          </Stack>
        </Card>

        <Card className="lyra-panel settings-card" padding="xl">
          <Stack gap="lg">
            <div>
              <Title order={3} className="settings-section-title">Behavior</Title>
              <Text className="settings-hint">Choose how Lyra behaves when booting, recovering, and debugging.</Text>
            </div>
            <Checkbox
              checked={fixtureMode}
              onChange={(event) => setFixtureMode(event.currentTarget.checked)}
              label="Fixture mode"
              description="Use static sample data when the backend is unreachable."
            />
            <Checkbox
              checked={resumeSession}
              onChange={(event) => setResumeSession(event.currentTarget.checked)}
              label="Restore last queue on launch"
              description="Pick up where you left off, including track position."
            />
            <Checkbox
              checked={developerHud}
              onChange={(event) => setDeveloperHud(event.currentTarget.checked)}
              label="Developer HUD"
              description="Overlay showing connectivity, API state, and recent calls."
            />
          </Stack>
        </Card>

        <Card className="lyra-panel settings-card" padding="xl">
          <Stack gap="lg">
            <Group justify="space-between" align="start">
              <div>
                <Title order={3} className="settings-section-title">Companion</Title>
                <Text className="settings-hint">A living shell layer for status, discovery mood, and future avatar work.</Text>
              </div>
              <Badge color="lyra" variant="light">Shell Layer</Badge>
            </Group>
            <Checkbox
              checked={companionEnabled}
              onChange={(event) => setCompanionEnabled(event.currentTarget.checked)}
              label="Enable companion"
              description="Show the floating Lyra presence in the desktop shell."
            />
            <div className="settings-field">
              <Text className="settings-label">Companion style</Text>
              <SegmentedControl
                fullWidth
                value={companionStyle}
                onChange={(value) => setCompanionStyle(value as "orb" | "pixel")}
                data={[
                  { label: "Glowing Orb", value: "orb" },
                  { label: "8-Bit Face", value: "pixel" },
                ]}
                disabled={!companionEnabled}
              />
            </div>
          </Stack>
        </Card>

        <Card className="lyra-panel settings-card settings-card--wide" padding="xl">
          <Stack gap="lg">
            <div>
              <Title order={3} className="settings-section-title">Keyboard Shortcuts</Title>
              <Text className="settings-hint">Primary shell actions already wired into the live desktop path.</Text>
            </div>
            <div className="settings-shortcuts-grid">
              {SHORTCUTS.map(([key, desc]) => (
                <div key={key} className="settings-shortcut-row">
                  <Badge variant="outline" color="gray" className="settings-shortcut-badge">{key}</Badge>
                  <span className="settings-shortcut-desc">{desc}</span>
                </div>
              ))}
            </div>
          </Stack>
        </Card>
      </section>

      <section className="settings-diagnostics-stack">
        <div className="section-heading">
          <h2>Diagnostics</h2>
          <span>Backend health and doctor evidence</span>
        </div>
        <BackendStatusPanel />
        <DoctorPanel />
      </section>
    </div>
  );
}

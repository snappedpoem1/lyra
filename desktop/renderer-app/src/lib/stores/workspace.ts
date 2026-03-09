import { writable } from "svelte/store";
import type { AcquisitionPreflight, EnrichmentEntry, ExplainPayload, TrackRecord } from "$lib/types";

export type InspectorTab = "context" | "explain" | "provenance" | "bridge" | "queue" | "acquisition";

export type BridgeAction = {
  label: string;
  href?: string;
  detail?: string;
  emphasis?: "default" | "accent";
};

export type AcquisitionWorkspaceSnapshot = {
  pending: number;
  active: number;
  failed: number;
  workerRunning: boolean;
  preflight: AcquisitionPreflight | null;
  recentEvents: Array<{ at: string; message: string; tone: "info" | "success" | "warning" | "error" }>;
};

export type WorkspaceState = {
  leftRailOpen: boolean;
  rightRailOpen: boolean;
  inspectorTab: InspectorTab;
  composerText: string;
  pageEyebrow: string;
  pageTitle: string;
  pageSubtitle: string;
  selectedTrack: TrackRecord | null;
  selectedArtist: string | null;
  explanation: ExplainPayload | null;
  provenance: EnrichmentEntry[];
  bridgeActions: BridgeAction[];
  acquisition: AcquisitionWorkspaceSnapshot | null;
};

const defaultWorkspace: WorkspaceState = {
  leftRailOpen: true,
  rightRailOpen: true,
  inspectorTab: "context",
  composerText: "",
  pageEyebrow: "Cassette",
  pageTitle: "Music companion workspace",
  pageSubtitle: "One shell for discovery, playlist authorship, bridge-finding, acquisition, and explanation.",
  selectedTrack: null,
  selectedArtist: null,
  explanation: null,
  provenance: [],
  bridgeActions: [],
  acquisition: null,
};

export const workspace = writable<WorkspaceState>(defaultWorkspace);

export function toggleLeftRail(): void {
  workspace.update((state) => ({ ...state, leftRailOpen: !state.leftRailOpen }));
}

export function toggleRightRail(): void {
  workspace.update((state) => ({ ...state, rightRailOpen: !state.rightRailOpen }));
}

export function setInspectorTab(tab: InspectorTab): void {
  workspace.update((state) => ({ ...state, inspectorTab: tab, rightRailOpen: true }));
}

export function setComposerText(text: string): void {
  workspace.update((state) => ({ ...state, composerText: text }));
}

export function setWorkspacePage(
  pageEyebrow: string,
  pageTitle: string,
  pageSubtitle: string,
  tab: InspectorTab = "context",
): void {
  workspace.update((state) => ({
    ...state,
    pageEyebrow,
    pageTitle,
    pageSubtitle,
    inspectorTab: tab,
  }));
}

export function setWorkspaceTrack(track: TrackRecord | null): void {
  workspace.update((state) => ({ ...state, selectedTrack: track, inspectorTab: "context", rightRailOpen: true }));
}

export function setWorkspaceArtist(artist: string | null): void {
  workspace.update((state) => ({ ...state, selectedArtist: artist, inspectorTab: "context", rightRailOpen: true }));
}

export function setWorkspaceExplanation(explanation: ExplainPayload | null, track?: TrackRecord | null): void {
  workspace.update((state) => ({
    ...state,
    explanation,
    selectedTrack: track ?? state.selectedTrack,
    inspectorTab: "explain",
    rightRailOpen: true,
  }));
}

export function setWorkspaceProvenance(entries: EnrichmentEntry[], track?: TrackRecord | null): void {
  workspace.update((state) => ({
    ...state,
    provenance: entries,
    selectedTrack: track ?? state.selectedTrack,
    inspectorTab: "provenance",
    rightRailOpen: true,
  }));
}

export function setWorkspaceBridgeActions(actions: BridgeAction[], artist?: string | null): void {
  workspace.update((state) => ({
    ...state,
    bridgeActions: actions,
    selectedArtist: artist ?? state.selectedArtist,
    inspectorTab: "bridge",
    rightRailOpen: true,
  }));
}

export function setWorkspaceAcquisition(acquisition: AcquisitionWorkspaceSnapshot | null): void {
  workspace.update((state) => ({
    ...state,
    acquisition,
    inspectorTab: "acquisition",
    rightRailOpen: true,
  }));
}

export function clearWorkspaceDetails(): void {
  workspace.update((state) => ({
    ...state,
    explanation: null,
    provenance: [],
    bridgeActions: [],
    acquisition: null,
  }));
}

import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { resolveApiUrl } from "@/services/lyraGateway/client";
import { usePlayerStore } from "@/stores/playerStore";
import type { TrackListItem } from "@/types/domain";

type PlaybackListener = () => void;

function resolveTrackExplanation(track: TrackListItem): string | undefined {
  return track.reasons[0]?.text ?? track.reason;
}

function resolveTrackSource(track: TrackListItem): string {
  if (track.path) {
    return `lyra-media://track?path=${encodeURIComponent(track.path)}`;
  }
  if (track.streamUrl) {
    return track.streamUrl.startsWith("http") ? track.streamUrl : resolveApiUrl(track.streamUrl);
  }
  return "";
}

class AudioEngine {
  private audio = new Audio();
  private listeners = new Set<PlaybackListener>();
  private pendingSeekSec = 0;

  constructor() {
    this.audio.preload = "auto";
    this.audio.addEventListener("play", () => {
      usePlayerStore.getState().setStatus("playing");
      this.emit();
    });
    this.audio.addEventListener("pause", () => {
      usePlayerStore.getState().setStatus("paused");
      this.emit();
    });
    this.audio.addEventListener("ended", () => {
      usePlayerStore.getState().setStatus("ended");
      this.emit();
    });
    this.audio.addEventListener("timeupdate", () => {
      usePlayerStore.getState().setTime(this.audio.currentTime, this.audio.duration || usePlayerStore.getState().durationSec);
      this.emit();
    });
    this.audio.addEventListener("loadedmetadata", () => {
      if (this.pendingSeekSec > 0) {
        this.audio.currentTime = Math.max(0, Math.min(this.pendingSeekSec, this.audio.duration || this.pendingSeekSec));
        this.pendingSeekSec = 0;
      }
      usePlayerStore.getState().setTime(this.audio.currentTime, this.audio.duration || 0);
      this.emit();
    });
    this.audio.addEventListener("error", () => {
      usePlayerStore.getState().setError("Stream URL missing or backend unavailable.");
      this.emit();
    });
  }

  get element(): HTMLAudioElement {
    return this.audio;
  }

  subscribe(listener: PlaybackListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  async playTrack(track: TrackListItem): Promise<void> {
    const state = usePlayerStore.getState();
    const source = resolveTrackSource(track);
    state.setTrack(track, state.sourceLabel, resolveTrackExplanation(track));
    if (!source) {
      usePlayerStore.getState().setError("Track path or stream URL missing.");
      this.emit();
      return;
    }
    this.audio.src = source;
    this.audio.volume = state.volume;
    this.audio.muted = state.muted;
    await audioAnalyzer.resume();
    try {
      await this.audio.play();
    } catch {
      usePlayerStore.getState().setError("Playback could not start. Local path or stream may be unavailable.");
      this.emit();
    }
  }

  loadTrack(track: TrackListItem, startTimeSec = 0): void {
    const state = usePlayerStore.getState();
    const source = resolveTrackSource(track);
    this.pendingSeekSec = Math.max(0, startTimeSec);
    if (!source) {
      usePlayerStore.getState().setError("Track path or stream URL missing.");
      this.emit();
      return;
    }
    this.audio.src = source;
    this.audio.volume = state.volume;
    this.audio.muted = state.muted;
    this.audio.load();
  }

  async play(): Promise<void> {
    await audioAnalyzer.resume();
    await this.audio.play();
  }

  pause(): void {
    this.audio.pause();
  }

  stop(): void {
    this.audio.pause();
    this.audio.currentTime = 0;
    this.audio.removeAttribute("src");
    this.audio.load();
    usePlayerStore.getState().setTrack(null);
    this.emit();
  }

  seek(progress: number): void {
    const duration = this.audio.duration || usePlayerStore.getState().durationSec;
    if (duration > 0) {
      this.audio.currentTime = Math.max(0, Math.min(duration, duration * progress));
    }
  }

  setVolume(volume: number): void {
    this.audio.volume = volume;
  }

  setMuted(muted: boolean): void {
    this.audio.muted = muted;
  }

  private emit(): void {
    this.listeners.forEach((listener) => listener());
  }
}

export const audioEngine = new AudioEngine();

import { audioAnalyzer } from "@/services/audio/audioAnalyzer";
import { resolveApiUrl } from "@/services/lyraGateway/client";
import { usePlayerStore } from "@/stores/playerStore";
import type { TrackListItem } from "@/types/domain";

type PlaybackListener = () => void;

class AudioEngine {
  private audio = new Audio();
  private listeners = new Set<PlaybackListener>();

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
    state.setTrack(track, state.sourceLabel, track.reason);
    this.audio.src = track.streamUrl.startsWith("http") ? track.streamUrl : resolveApiUrl(track.streamUrl);
    this.audio.volume = state.volume;
    this.audio.muted = state.muted;
    await audioAnalyzer.resume();
    try {
      await this.audio.play();
    } catch {
      usePlayerStore.getState().setError("Playback could not start. Stream URL may be missing.");
      this.emit();
    }
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

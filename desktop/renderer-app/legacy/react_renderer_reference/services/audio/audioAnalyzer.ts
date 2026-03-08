import type { VisualizerFrame } from "@/types/domain";

export class AudioAnalyzer {
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private source: MediaElementAudioSourceNode | null = null;
  private waveformArray: Uint8Array<ArrayBuffer> | null = null;
  private spectrumArray: Uint8Array<ArrayBuffer> | null = null;

  attach(audio: HTMLAudioElement): void {
    if (this.context || !window.AudioContext) {
      return;
    }

    try {
      this.context = new window.AudioContext();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 256;
      this.waveformArray = new Uint8Array(new ArrayBuffer(this.analyser.fftSize));
      this.spectrumArray = new Uint8Array(new ArrayBuffer(this.analyser.frequencyBinCount));
      this.source = this.context.createMediaElementSource(audio);
      this.source.connect(this.analyser);
      this.analyser.connect(this.context.destination);
    } catch {
      this.context = null;
      this.analyser = null;
    }
  }

  async resume(): Promise<void> {
    if (this.context?.state === "suspended") {
      await this.context.resume();
    }
  }

  frameFromFallback(seed: number, isPlaying: boolean): VisualizerFrame {
    const waveform = Array.from({ length: 64 }, (_, index) => {
      const value = Math.sin(seed / 8 + index / 4) * 0.5 + Math.sin(seed / 20 + index / 7) * 0.5;
      return Number((((value + 1) / 2) * (isPlaying ? 1 : 0.25)).toFixed(3));
    });
    const spectrum = Array.from({ length: 48 }, (_, index) => {
      const wave = Math.cos(seed / 14 + index / 5) * 0.5 + 0.5;
      return Number((wave * (isPlaying ? 1 : 0.2)).toFixed(3));
    });
    return {
      waveform,
      spectrum,
      energy: spectrum.slice(0, 12).reduce((sum, value) => sum + value, 0) / 12,
      tension: spectrum.slice(12, 24).reduce((sum, value) => sum + value, 0) / 12,
      movement: spectrum.slice(24, 36).reduce((sum, value) => sum + value, 0) / 12,
      isPlaying,
    };
  }

  getFrame(isPlaying: boolean, seed: number): VisualizerFrame {
    if (!this.analyser || !this.waveformArray || !this.spectrumArray) {
      return this.frameFromFallback(seed, isPlaying);
    }

    this.analyser.getByteTimeDomainData(this.waveformArray);
    this.analyser.getByteFrequencyData(this.spectrumArray);

    const waveform = [...this.waveformArray.slice(0, 64)].map((value) => Number((value / 255).toFixed(3)));
    const spectrum = [...this.spectrumArray.slice(0, 48)].map((value) => Number((value / 255).toFixed(3)));

    return {
      waveform,
      spectrum,
      energy: spectrum.slice(0, 12).reduce((sum, value) => sum + value, 0) / 12,
      tension: spectrum.slice(12, 24).reduce((sum, value) => sum + value, 0) / 12,
      movement: spectrum.slice(24, 36).reduce((sum, value) => sum + value, 0) / 12,
      isPlaying,
    };
  }
}

export const audioAnalyzer = new AudioAnalyzer();

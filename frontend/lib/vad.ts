// REQ-F-003 VAD 공개 인터페이스 + WebAudio(AnalyserNode) 구현.
// 나중에 Silero VAD 등으로 교체할 때는 `VoiceActivityDetector` 를 구현하는 클래스만 바꿔 끼우면 된다.
import { VadCore, computeRms, type VadConfig } from "./vadCore";

export type { VadConfig } from "./vadCore";

export interface VadCallbacks {
  onSpeechStart?: () => void;
  onSpeechEnd?: () => void;
}

export interface VoiceActivityDetector {
  /** 마이크 스트림 감시 시작. 이미 실행 중이면 먼저 stop() 한다. */
  start(stream: MediaStream): void;
  /** 감시 종료(스트림 자체는 닫지 않는다). */
  stop(): void;
  /** AI 음성 재생 중(바지인 감시) 여부 — 임계↑, 최소 발화↑. */
  setPlaybackMode(on: boolean): void;
  readonly speaking: boolean;
}

const FRAME_MS = 20;

export class AnalyserVad implements VoiceActivityDetector {
  private core: VadCore;
  private ctx: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private analyser: AnalyserNode | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private pendingPlayback = false;
  private callbacks: VadCallbacks;
  private config: Partial<VadConfig>;

  constructor(callbacks: VadCallbacks = {}, config: Partial<VadConfig> = {}) {
    this.callbacks = callbacks;
    this.config = config;
    this.core = this.makeCore();
  }

  private makeCore(): VadCore {
    return new VadCore(this.config, {
      onSpeechStart: () => this.callbacks.onSpeechStart?.(),
      onSpeechEnd: () => this.callbacks.onSpeechEnd?.(),
    });
  }

  get speaking(): boolean {
    return this.core.currentState === "speech";
  }

  setPlaybackMode(on: boolean): void {
    this.pendingPlayback = on;
    this.core.setPlaybackMode(on);
  }

  start(stream: MediaStream): void {
    this.stop();
    const Ctx: typeof AudioContext | undefined =
      typeof window !== "undefined"
        ? (window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)
        : undefined;
    if (!Ctx) return; // 미지원 환경: VAD 없이 수동 동작만(호출부는 그대로 동작)
    this.core = this.makeCore();
    this.core.setPlaybackMode(this.pendingPlayback);
    const ctx = new Ctx();
    void ctx.resume().catch(() => {});
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser); // destination 에는 연결하지 않는다(에코 방지)
    const buf = new Float32Array(analyser.fftSize);
    this.ctx = ctx;
    this.source = source;
    this.analyser = analyser;
    this.timer = setInterval(() => {
      analyser.getFloatTimeDomainData(buf);
      this.core.push(computeRms(buf), performance.now());
    }, FRAME_MS);
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    try {
      this.source?.disconnect();
    } catch {
      // 이미 해제됨
    }
    void this.ctx?.close().catch(() => {});
    this.ctx = null;
    this.source = null;
    this.analyser = null;
  }
}

// REQ-F-003 VAD 순수 DSP 코어 — WebAudio 에 의존하지 않아 node 에서 그대로 테스트한다.
//
// 입력: 프레임별 RMS(0~1) 와 단조 증가하는 시각(ms). 출력: speechStart / speechEnd 이벤트.
//  - 적응형 소음 바닥: 발화가 아닌 구간에서 RMS 를 지수 이동평균으로 추적(내려갈 땐 빠르게, 올라갈 땐
//    느리게). 시작 임계 = max(absMinRms, floor * startRatio), 종료 임계 = max(absMinRms*0.6, floor * endRatio)
//    (히스테리시스: 종료 임계가 더 낮아 발화 중 작은 음절 사이 에너지 저하에 끊기지 않는다).
//  - 최소 발화 길이: 임계 이상 구간이 minSpeechMs 이상 이어져야 speechStart. (짧은 기침/클릭 무시)
//  - 행오버: 마지막 "유성" 프레임 이후 hangoverMs 이상 침묵이면 speechEnd.
//  - 재생 모드(바지인): 임계를 thresholdMultiplier 배로 올리고 최소 발화 길이를 playbackMinSpeechMs 로
//    늘리며 소음 바닥 추적을 멈춘다(스피커 에코가 바닥을 끌어올리는 것 방지).

export interface VadConfig {
  /** 최소 발화 길이(ms). 이보다 짧은 에너지 구간은 무시. */
  minSpeechMs: number;
  /** 침묵이 이 시간 이상 이어지면 speechEnd (ms). */
  hangoverMs: number;
  /** 시작 임계 = floor * startRatio (절대 하한 absMinRms 와 큰 쪽). */
  startRatio: number;
  /** 종료 임계 = floor * endRatio. */
  endRatio: number;
  /** 절대 최소 RMS(디지털 풀스케일 1.0 기준, 약 -36dBFS). */
  absMinRms: number;
  /** 소음 바닥 초기값. */
  initialFloor: number;
  /** 소음 바닥 하한 (0 으로 수렴해 임계가 사라지는 것 방지). */
  minFloor: number;
  /** 바닥이 내려갈 때 시정수(ms). */
  floorFallTauMs: number;
  /** 임계 미만 프레임으로 바닥이 올라갈 때 시정수(ms). */
  floorRiseTauMs: number;
  /** 임계 이상이지만 아직 발화 확정 전인 프레임이 바닥을 올리는 시정수(ms, 매우 느림). */
  floorLoudRiseTauMs: number;
  /** 후보 발화 구간 중 이 시간까지의 에너지 저하는 이어진 것으로 본다(ms). */
  candidateGapMs: number;
  /** 재생(바지인) 모드 임계 배수. */
  playbackThresholdMultiplier: number;
  /** 재생(바지인) 모드 최소 발화 길이(ms). */
  playbackMinSpeechMs: number;
}

export const DEFAULT_VAD_CONFIG: VadConfig = {
  minSpeechMs: 250,
  hangoverMs: 1800,
  startRatio: 3,
  endRatio: 1.8,
  absMinRms: 0.015,
  initialFloor: 0.005,
  minFloor: 0.002,
  floorFallTauMs: 300,
  floorRiseTauMs: 2000,
  floorLoudRiseTauMs: 8000,
  candidateGapMs: 120,
  playbackThresholdMultiplier: 2.5,
  playbackMinSpeechMs: 300,
};

export interface VadHandlers {
  /** startedAtMs: 에너지가 처음 임계를 넘은 시각(확정 판정 시각보다 이르다). */
  onSpeechStart?: (info: { startedAtMs: number; atMs: number }) => void;
  /** silenceMs: 마지막 유성 프레임 이후 침묵 길이. speechMs: 발화 시작~마지막 유성 프레임. */
  onSpeechEnd?: (info: { atMs: number; silenceMs: number; speechMs: number }) => void;
}

export type VadState = "idle" | "speech";

export function computeRms(samples: ArrayLike<number>): number {
  const n = samples.length;
  if (n === 0) return 0;
  let sum = 0;
  for (let i = 0; i < n; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / n);
}

export class VadCore {
  private cfg: VadConfig;
  private handlers: VadHandlers;
  private floor: number;
  private state: VadState = "idle";
  private playback = false;
  private lastT: number | null = null;
  private candStart: number | null = null;
  private candLastAbove = 0;
  private speechStartedAt = 0;
  private lastVoiceT = 0;

  constructor(config: Partial<VadConfig> = {}, handlers: VadHandlers = {}) {
    this.cfg = { ...DEFAULT_VAD_CONFIG, ...config };
    this.handlers = handlers;
    this.floor = this.cfg.initialFloor;
  }

  get currentState(): VadState {
    return this.state;
  }
  get noiseFloor(): number {
    return this.floor;
  }
  get startThreshold(): number {
    const base = Math.max(this.cfg.absMinRms, this.floor * this.cfg.startRatio);
    return this.playback ? base * this.cfg.playbackThresholdMultiplier : base;
  }
  get endThreshold(): number {
    const base = Math.max(this.cfg.absMinRms * 0.6, this.floor * this.cfg.endRatio);
    return this.playback ? base * this.cfg.playbackThresholdMultiplier : base;
  }
  get playbackMode(): boolean {
    return this.playback;
  }

  setHandlers(handlers: VadHandlers): void {
    this.handlers = handlers;
  }

  setPlaybackMode(on: boolean): void {
    this.playback = on;
  }

  /** 상태·소음 바닥 초기화(재시작). 설정/핸들러는 유지. */
  reset(): void {
    this.floor = this.cfg.initialFloor;
    this.state = "idle";
    this.playback = false;
    this.lastT = null;
    this.candStart = null;
  }

  private ema(current: number, target: number, dtMs: number, tauMs: number): number {
    const a = 1 - Math.exp(-dtMs / tauMs);
    return current + (target - current) * a;
  }

  private updateFloor(rms: number, dt: number, aboveStart: boolean): void {
    if (this.playback) return; // 에코가 바닥을 오염시키지 않도록 동결
    let next: number;
    if (rms < this.floor) next = this.ema(this.floor, rms, dt, this.cfg.floorFallTauMs);
    else if (aboveStart) next = this.ema(this.floor, rms, dt, this.cfg.floorLoudRiseTauMs);
    else next = this.ema(this.floor, rms, dt, this.cfg.floorRiseTauMs);
    this.floor = Math.max(this.cfg.minFloor, next);
  }

  /** 프레임 하나를 처리한다. tMs 는 단조 증가해야 한다. */
  push(rms: number, tMs: number): void {
    const dt = this.lastT === null ? 0 : Math.max(0, tMs - this.lastT);
    this.lastT = tMs;

    if (this.state === "idle") {
      const above = rms >= this.startThreshold;
      this.updateFloor(rms, dt, above); // 임계 판정은 갱신 전 값 기준(위에서 계산)
      if (above) {
        if (this.candStart === null) {
          this.candStart = tMs;
        }
        this.candLastAbove = tMs;
        const need = this.playback ? this.cfg.playbackMinSpeechMs : this.cfg.minSpeechMs;
        if (tMs - this.candStart >= need) {
          this.state = "speech";
          this.speechStartedAt = this.candStart;
          this.lastVoiceT = tMs;
          const startedAtMs = this.candStart;
          this.candStart = null;
          this.handlers.onSpeechStart?.({ startedAtMs, atMs: tMs });
        }
      } else if (this.candStart !== null && tMs - this.candLastAbove > this.cfg.candidateGapMs) {
        this.candStart = null; // 너무 오래 끊겼으면 후보 폐기
      }
      return;
    }

    // speech
    if (rms >= this.endThreshold) {
      this.lastVoiceT = tMs;
      return;
    }
    const silence = tMs - this.lastVoiceT;
    if (silence >= this.cfg.hangoverMs) {
      this.state = "idle";
      this.candStart = null;
      this.handlers.onSpeechEnd?.({
        atMs: tMs,
        silenceMs: silence,
        speechMs: this.lastVoiceT - this.speechStartedAt,
      });
    }
  }
}

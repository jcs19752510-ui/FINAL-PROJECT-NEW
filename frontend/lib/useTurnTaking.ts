"use client";

// REQ-F-003 Turn-taking 훅: VAD 이벤트를 "자동 제출"과 "바지인"으로 연결한다.
//  - watchRecording(stream): 녹음 중 감시. 말을 한 번이라도 시작한 뒤 침묵이 hangoverMs 이어지면
//    onAutoSubmit 을 정확히 1회 호출(말을 시작하지 않았다면 호출 안 함 → 빈 제출 방지).
//  - watchPlayback(stream): AI 음성 재생 중 감시(재생 모드 임계). 발화가 확정되면 onBargeIn 1회.
//    onBargeIn 이후 호출부가 같은 스트림으로 녹음을 시작하면 switchToRecording() 으로 같은 VAD 를
//    녹음 모드로 이어 쓴다(이미 말하는 중이므로 이후 침묵만으로 자동 제출 가능).
import { useCallback, useEffect, useRef } from "react";
import { AnalyserVad, type VadConfig, type VoiceActivityDetector } from "./vad";

export const AUTO_SUBMIT_HANGOVER_MS = 1800;
export const AUTO_SUBMIT_STORAGE_KEY = "interview.autoSubmitOnSilence";

/** getUserMedia 제약 — 스피커 에코·소음 완화(바지인 오탐 감소). */
export const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: { echoCancellation: true, noiseSuppression: true },
};

export function readAutoSubmitPref(): boolean {
  try {
    return window.localStorage.getItem(AUTO_SUBMIT_STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export function writeAutoSubmitPref(on: boolean): void {
  try {
    window.localStorage.setItem(AUTO_SUBMIT_STORAGE_KEY, on ? "on" : "off");
  } catch {
    // 저장 불가(프라이빗 모드 등) — 이번 세션 상태로만 유지
  }
}

/** 같은 녹음에서 AI 개입 신호를 한 번만 처리하게 하는 게이트. */
export function createOnceGate() {
  let used = false;
  return {
    tryOpen(): boolean {
      if (used) return false;
      used = true;
      return true;
    },
    reset(): void {
      used = false;
    },
  };
}

export interface TurnTakingOptions {
  /** 침묵 자동 제출 사용 여부(토글). 호출 시점 값이 쓰인다. */
  autoSubmit: boolean;
  hangoverMs?: number;
  vadConfig?: Partial<VadConfig>;
  onAutoSubmit: () => void;
  onBargeIn: () => void;
  /** 테스트/교체용 VAD 팩토리(Silero 등). */
  createVad?: (cb: { onSpeechStart: () => void; onSpeechEnd: () => void }, cfg: Partial<VadConfig>) => VoiceActivityDetector;
}

type Mode = "idle" | "recording" | "playback";

export function useTurnTaking(options: TurnTakingOptions) {
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  const vadRef = useRef<VoiceActivityDetector | null>(null);
  const modeRef = useRef<Mode>("idle");
  const spokeRef = useRef(false);
  const firedRef = useRef(false);

  const stop = useCallback(() => {
    modeRef.current = "idle";
    vadRef.current?.stop();
    vadRef.current = null;
  }, []);

  const begin = useCallback(
    (stream: MediaStream, mode: Mode) => {
      vadRef.current?.stop();
      modeRef.current = mode;
      spokeRef.current = false;
      firedRef.current = false;
      const o = optsRef.current;
      const cb = {
        onSpeechStart: () => {
          if (modeRef.current === "playback") {
            if (firedRef.current) return;
            firedRef.current = true;
            optsRef.current.onBargeIn();
          } else if (modeRef.current === "recording") {
            spokeRef.current = true;
          }
        },
        onSpeechEnd: () => {
          if (modeRef.current !== "recording") return;
          if (!spokeRef.current || firedRef.current) return;
          if (!optsRef.current.autoSubmit) return;
          firedRef.current = true;
          optsRef.current.onAutoSubmit();
        },
      };
      const cfg: Partial<VadConfig> = { hangoverMs: o.hangoverMs ?? AUTO_SUBMIT_HANGOVER_MS, ...o.vadConfig };
      const vad = o.createVad ? o.createVad(cb, cfg) : new AnalyserVad(cb, cfg);
      vad.setPlaybackMode(mode === "playback");
      vadRef.current = vad;
      vad.start(stream);
    },
    [],
  );

  const watchRecording = useCallback((stream: MediaStream) => begin(stream, "recording"), [begin]);
  const watchPlayback = useCallback((stream: MediaStream) => begin(stream, "playback"), [begin]);

  /** 바지인 직후: 같은 VAD 를 녹음 모드로 전환(이미 발화 중으로 간주). */
  const switchToRecording = useCallback(() => {
    if (!vadRef.current) return;
    modeRef.current = "recording";
    spokeRef.current = true;
    firedRef.current = false;
    vadRef.current.setPlaybackMode(false);
  }, []);

  useEffect(() => stop, [stop]);

  return { watchRecording, watchPlayback, switchToRecording, stop };
}

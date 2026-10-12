import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_VAD_CONFIG, VadCore, computeRms } from "./vadCore.ts";

// 결정적 의사난수(LCG) — 합성 잡음 지터용.
function rng(seed = 12345) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

// 하니스: 이벤트를 기록하면서 프레임을 밀어 넣는다.
function harness(cfg = {}, frameMs = 20) {
  const events = [];
  const core = new VadCore(cfg, {
    onSpeechStart: (i) => events.push({ type: "start", ...i }),
    onSpeechEnd: (i) => events.push({ type: "end", ...i }),
  });
  const rand = rng();
  let t = 0;
  return {
    core,
    events,
    get t() {
      return t;
    },
    // level: RMS 수준, jitter: ±비율
    feed(ms, level, jitter = 0) {
      const n = Math.round(ms / frameMs);
      for (let i = 0; i < n; i++) {
        const r = level * (1 + jitter * (rand() * 2 - 1));
        core.push(Math.max(0, r), t);
        t += frameMs;
      }
    },
    ramp(ms, from, to) {
      const n = Math.round(ms / frameMs);
      for (let i = 0; i < n; i++) {
        core.push(from + ((to - from) * i) / n, t);
        t += frameMs;
      }
    },
  };
}

const SPEECH = 0.1; // 발화 수준 RMS
const NOISE = 0.004; // 조용한 방 잡음
const types = (h) => h.events.map((e) => e.type);

test("computeRms: 사인파 A 의 RMS 는 A/sqrt(2), 무음·빈 입력은 0", () => {
  const sine = Float32Array.from({ length: 4800 }, (_, i) => 0.5 * Math.sin((2 * Math.PI * 440 * i) / 48000));
  assert.ok(Math.abs(computeRms(sine) - 0.5 / Math.SQRT2) < 1e-3);
  assert.equal(computeRms(new Float32Array(1024)), 0);
  assert.equal(computeRms([]), 0);
});

test("무음/조용한 잡음만 있으면 이벤트가 없다", () => {
  const h = harness();
  h.feed(10_000, NOISE, 0.3);
  assert.deepEqual(h.events, []);
  assert.equal(h.core.currentState, "idle");
});

test("발화 후 침묵: speechStart 1회, 행오버 이후 speechEnd 1회", () => {
  const h = harness();
  h.feed(500, NOISE, 0.2);
  h.feed(3000, SPEECH, 0.3);
  h.feed(4000, NOISE, 0.2);
  assert.deepEqual(types(h), ["start", "end"]);
  const [s, e] = h.events;
  assert.ok(s.startedAtMs >= 500 && s.startedAtMs <= 540, `startedAtMs=${s.startedAtMs}`);
  assert.ok(s.atMs - s.startedAtMs >= 250);
  assert.ok(e.silenceMs >= 1800 && e.silenceMs < 1840, `silenceMs=${e.silenceMs}`);
  assert.ok(e.speechMs > 2900 && e.speechMs < 3100, `speechMs=${e.speechMs}`);
});

test("최소 발화 길이 경계: 250ms 미만은 무시, 250ms 이상은 시작 (10ms 프레임)", () => {
  const under = harness({}, 10);
  under.feed(100, NOISE);
  under.feed(250, SPEECH); // 프레임 t=100..340 → 지속 340-100=240ms 시점까지만
  under.feed(1000, NOISE);
  assert.deepEqual(under.events, [], "240ms 지속은 발화가 아니다");

  const at = harness({}, 10);
  at.feed(100, NOISE);
  at.feed(260, SPEECH); // 지속 250ms 도달 프레임 포함
  assert.deepEqual(types(at), ["start"], "정확히 250ms 지속이면 시작");
  assert.equal(at.events[0].atMs - at.events[0].startedAtMs, 250);
});

test("짧은 클릭/기침(100~200ms 버스트)은 무시", () => {
  for (const burst of [20, 100, 200]) {
    const h = harness();
    h.feed(500, NOISE);
    h.feed(burst, SPEECH);
    h.feed(3000, NOISE);
    assert.deepEqual(h.events, [], `${burst}ms 버스트`);
  }
});

test("후보 구간의 짧은 에너지 저하(<=120ms)는 이어진 발화, 긴 저하는 후보 폐기", () => {
  const ok = harness();
  ok.feed(100, SPEECH);
  ok.feed(100, NOISE);
  ok.feed(400, SPEECH);
  assert.deepEqual(types(ok), ["start"]);

  const bad = harness();
  bad.feed(100, SPEECH);
  bad.feed(200, NOISE);
  bad.feed(160, SPEECH); // 새 후보 160ms — 250ms 미만
  bad.feed(2000, NOISE);
  assert.deepEqual(bad.events, []);
});

test("행오버 경계: 침묵 1.78s 는 종료 아님, 1.8s 에서 종료 (10ms 프레임)", () => {
  const h = harness({}, 10);
  h.feed(1000, SPEECH); // 마지막 유성 프레임 t=990
  assert.deepEqual(types(h), ["start"]);
  h.feed(1780, NOISE); // 마지막 침묵 프레임 t=2770 → 침묵 1780ms
  assert.deepEqual(types(h), ["start"], "1780ms 침묵은 아직 종료 아님");
  h.feed(10, NOISE); // t=2780 → 침묵 1790
  assert.deepEqual(types(h), ["start"]);
  h.feed(10, NOISE); // t=2790 → 1800
  assert.deepEqual(types(h), ["start", "end"], "1800ms 침묵에서 종료");
  assert.equal(h.events[1].silenceMs, 1800);
});

test("발화 중 1.5s 휴지는 종료되지 않고, 말이 이어지면 끝은 마지막 발화 기준", () => {
  const h = harness();
  h.feed(1000, SPEECH, 0.3);
  h.feed(1500, NOISE, 0.2);
  assert.deepEqual(types(h), ["start"]);
  h.feed(1000, SPEECH, 0.3);
  assert.deepEqual(types(h), ["start"], "발화 재개 → 종료 취소");
  h.feed(2500, NOISE, 0.2);
  assert.deepEqual(types(h), ["start", "end"]);
});

test("행오버 설정값이 반영된다(900ms)", () => {
  const h = harness({ hangoverMs: 900 }, 10);
  h.feed(1000, SPEECH);
  h.feed(880, NOISE);
  assert.deepEqual(types(h), ["start"]);
  h.feed(20, NOISE);
  assert.deepEqual(types(h), ["start", "end"]);
});

test("소음 바닥 적응: 지속 잡음 0.01 에서 바닥이 따라가고, 이후 발화는 검출된다", () => {
  const h = harness();
  h.feed(15_000, 0.01, 0.2);
  assert.ok(h.core.noiseFloor > 0.008 && h.core.noiseFloor < 0.013, `floor=${h.core.noiseFloor}`);
  assert.deepEqual(h.events, []);
  h.feed(1000, SPEECH, 0.2);
  assert.deepEqual(types(h), ["start"]);
});

test("소음 바닥 상승: 서서히 커지는 잡음(0.004→0.03, 30초)은 발화로 오인하지 않는다", () => {
  const h = harness();
  h.ramp(30_000, 0.004, 0.03);
  h.feed(5000, 0.03, 0.1);
  assert.deepEqual(h.events, []);
  assert.ok(h.core.noiseFloor > 0.02);
  // 바닥이 올라간 뒤의 임계는 높아졌다: 바닥 위 약한 신호(0.05)는 시작 임계 미달
  assert.ok(h.core.startThreshold > 0.05, `thr=${h.core.startThreshold}`);
  h.feed(1000, 0.2, 0.1);
  assert.deepEqual(types(h), ["start"], "충분히 큰 발화는 여전히 검출");
});

test("소음 바닥 하강: 시끄러운 환경이 조용해지면 임계도 내려간다", () => {
  const h = harness();
  h.feed(15_000, 0.03, 0.1);
  const high = h.core.startThreshold;
  h.feed(5_000, 0.003, 0.1);
  assert.ok(h.core.startThreshold < high);
  assert.ok(h.core.startThreshold >= DEFAULT_VAD_CONFIG.absMinRms);
});

test("발화 확정 이후에는 소음 바닥이 발화 에너지로 끌려가지 않는다", () => {
  const h = harness();
  h.feed(500, NOISE);
  h.feed(1000, SPEECH, 0.3);
  assert.deepEqual(types(h), ["start"]);
  const atStart = h.core.noiseFloor;
  assert.ok(atStart < 0.012, `후보 구간(250ms) 동안의 상승은 미미해야 함: ${atStart}`);
  h.feed(10_000, SPEECH, 0.3);
  assert.equal(h.core.noiseFloor, atStart);
  h.feed(2500, NOISE);
  assert.deepEqual(types(h), ["start", "end"]);
});

test("에코 누설 수준의 약한 신호: 일반 모드에선 발화, 재생(바지인) 모드에선 무시", () => {
  const ECHO = 0.03;
  const normal = harness();
  normal.feed(500, NOISE);
  normal.feed(1000, ECHO, 0.1);
  assert.deepEqual(types(normal), ["start"]);

  const playing = harness();
  playing.core.setPlaybackMode(true);
  playing.feed(500, NOISE);
  playing.feed(3000, ECHO, 0.1);
  assert.deepEqual(playing.events, [], "재생 중 에코 수준은 바지인 아님");
});

test("바지인: 재생 중 실제 발화(0.15)는 300ms 지속 후에만 시작 (10ms 프레임)", () => {
  const under = harness({}, 10);
  under.core.setPlaybackMode(true);
  under.feed(200, NOISE);
  under.feed(300, 0.15); // 지속 290ms
  under.feed(500, NOISE);
  assert.deepEqual(under.events, [], "290ms 는 바지인 아님");

  const at = harness({}, 10);
  at.core.setPlaybackMode(true);
  at.feed(200, NOISE);
  at.feed(310, 0.15); // 지속 300ms 도달
  assert.deepEqual(types(at), ["start"]);
  assert.equal(at.events[0].atMs - at.events[0].startedAtMs, 300);
});

test("재생 모드 최소 발화(300ms)가 일반 모드(250ms)보다 길다: 270ms 버스트", () => {
  const normal = harness({}, 10);
  normal.feed(100, NOISE);
  normal.feed(280, 0.15);
  assert.deepEqual(types(normal), ["start"]);
  const playing = harness({}, 10);
  playing.core.setPlaybackMode(true);
  playing.feed(100, NOISE);
  playing.feed(280, 0.15);
  assert.deepEqual(playing.events, []);
});

test("재생 모드에서는 소음 바닥이 동결된다(에코가 바닥을 오염시키지 않음)", () => {
  const h = harness();
  h.feed(2000, NOISE);
  const before = h.core.noiseFloor;
  h.core.setPlaybackMode(true);
  h.feed(5000, 0.02, 0.1);
  assert.equal(h.core.noiseFloor, before);
  h.core.setPlaybackMode(false);
  assert.equal(h.core.playbackMode, false);
});

test("바지인 후 일반 모드 전환: 발화 상태 유지, 이후 침묵 1.8s 에 종료", () => {
  const h = harness();
  h.core.setPlaybackMode(true);
  h.feed(300, NOISE);
  h.feed(700, 0.15);
  assert.deepEqual(types(h), ["start"]);
  h.core.setPlaybackMode(false);
  h.feed(1700, NOISE);
  assert.deepEqual(types(h), ["start"]);
  h.feed(200, NOISE);
  assert.deepEqual(types(h), ["start", "end"]);
});

test("재시작: reset 후 상태·바닥 초기화, 다시 발화/종료 검출", () => {
  const h = harness();
  h.feed(15_000, 0.012, 0.1);
  assert.ok(h.core.noiseFloor > 0.01, `floor=${h.core.noiseFloor}`);
  h.core.reset();
  assert.equal(h.core.currentState, "idle");
  assert.equal(h.core.noiseFloor, DEFAULT_VAD_CONFIG.initialFloor);
  h.events.length = 0;
  h.feed(500, NOISE);
  h.feed(1000, SPEECH);
  h.feed(2500, NOISE);
  assert.deepEqual(types(h), ["start", "end"]);
});

test("연속 두 번의 발화: 각각 start/end 쌍으로 판정", () => {
  const h = harness();
  for (let k = 0; k < 2; k++) {
    h.feed(500, NOISE, 0.2);
    h.feed(1500, SPEECH, 0.3);
    h.feed(2500, NOISE, 0.2);
  }
  assert.deepEqual(types(h), ["start", "end", "start", "end"]);
});

test("사인파 합성 발화(여러 주파수) 프레임의 RMS 로 end-to-end 판정", () => {
  const sr = 16000;
  const frame = 320; // 20ms
  const rand = rng(7);
  const core = new VadCore({}, {});
  const events = [];
  core.setHandlers({ onSpeechStart: () => events.push("start"), onSpeechEnd: () => events.push("end") });
  let sample = 0;
  let t = 0;
  const gen = (amp) => {
    const buf = new Float32Array(frame);
    for (let i = 0; i < frame; i++, sample++) {
      const x = sample / sr;
      const speech = Math.sin(2 * Math.PI * 180 * x) + 0.6 * Math.sin(2 * Math.PI * 460 * x) + 0.4 * Math.sin(2 * Math.PI * 1300 * x);
      buf[i] = amp * speech + 0.002 * (rand() * 2 - 1);
    }
    return buf;
  };
  const run = (ms, amp) => {
    for (let i = 0; i < ms / 20; i++) {
      core.push(computeRms(gen(amp)), t);
      t += 20;
    }
  };
  run(500, 0);
  run(3000, 0.2);
  run(4000, 0);
  assert.deepEqual(events, ["start", "end"]);
});

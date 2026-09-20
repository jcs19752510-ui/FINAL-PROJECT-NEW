"use client";

/**
 * [C-06] 면접장(메인) — 텍스트 턴 + 음성 턴 (unit-4: REQ-003, unit-5: REQ-004/REQ-005,
 * 04-ux-design.md §2 [C-06]).
 *
 * unit-4는 텍스트 채팅만 다뤘다. 이번 유닛(unit-5)은 04-ux-design [C-06]의
 * `AudioRecorderControl`(idle/recording/uploading/error)을 추가해 마이크
 * 녹음→정지→업로드 흐름을 구현한다.
 *
 * unit-20: 웹캠 프리뷰 타일(unit-16), 코드 에디터(unit-9), 화이트보드(unit-17)를 이
 * 화면에 배선한다(04-ux-design [C-06]/§6). 패널 자체 로직은 각 컴포넌트가 소유하고,
 * 이 파일은 "언제 어떤 패널을 어디에 노출하는가"만 결정한다.
 *
 * **스텁 경계(unit-4에서 이어짐, 여전히 유효)**: `POST /interviews/{id}/turns`는
 * 텍스트/음성 모두 실제로 TRANSCRIPTS에 저장하고(음성은 faster-whisper로 실제
 * STT 변환) 202 {job_id}를 반환하지만, AI가 실제로 응답을 생성해 WebSocket으로
 * `stage_update`/`turn_result`를 보내는 주체(AI Worker, unit-7)는 아직 없다.
 * 이 화면은 턴 제출 후 일정 시간(`AI_WAIT_TIMEOUT_MS`) 안에 아무 이벤트도 오지
 * 않으면 "AI 응답 엔진은 아직 준비 중입니다"라는 안내로 전환한다(unit-4 그대로).
 *
 * **음성 턴의 낙관적 UI 차이(unit-5 신규)**: 텍스트는 사용자가 입력한 문자열을
 * 그대로 화면에 즉시 표시할 수 있지만, 음성은 서버가 STT로 변환하기 전까지
 * 클라이언트가 인식 결과를 알 수 없다. 그래서 음성 제출 성공(202) 직후
 * `GET /transcripts`를 한 번 다시 호출해 서버가 실제로 저장한 인식 텍스트를
 * 반영한다(낙관적 placeholder 대신 "인식 중..." 배지를 잠깐 보여준 뒤 실제
 * 텍스트로 교체).
 */
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ApiError,
  type ConsentOut,
  type InterviewDetailOut,
  type TranscriptOut,
  createConsent,
  getInterview,
  interviewWsUrl,
  listMyConsents,
  listTranscripts,
  readAccessToken,
  submitTextTurn,
  submitVoiceTurn,
} from "@/lib/api";
import { useMediaQuery } from "@/lib/useMediaQuery";
import WebcamPreview from "@/components/WebcamPreview";
import InterviewSidePanel, { SIDE_PANEL_LABEL, type SidePanelId } from "./components/InterviewSidePanel";

// 04-ux-design.md §2 [C-06] "대기열 임계 초과 안내"류 구현 세부값과 동일한 성격의
// 클라이언트 전용 상수(설계서 미명시, 비가역성 낮음) — 이 시간을 넘기면 자동으로
// 녹음을 종료해 무제한 업로드를 방지한다(backend MAX_VOICE_UPLOAD_BYTES와 동일한
// 목적의 프런트 측 안전장치).
const MAX_RECORDING_MS = 120_000;

// 03-design §4.3 서버→클라이언트 이벤트 스키마 그대로.
type WsEvent =
  | { type: "queue_status"; job_id: string; position: number; eta_seconds: number }
  | { type: "stage_update"; job_id: string; stage: "stt" | "llm" | "tts" }
  | {
      type: "turn_result";
      job_id: string;
      transcript?: string;
      ai_text: string;
      audio_url?: string | null;
      control?: { action: "next_question" | "end_interview" | "switch_to_coding" | "none" };
    }
  | { type: "report_ready"; job_id: string; interview_id: string }
  | { type: "error"; job_id: string; code: string; message: string };

// 실제 AI Worker(unit-7)가 없어 stage_update/turn_result가 영원히 오지 않는 스텁
// 상태를 화면이 무한정 기다리지 않도록 하는 클라이언트 전용 타임아웃(설계서에
// 명시된 값이 아님 — 이번 유닛의 그레이스풀 디그레이드 구현 세부사항).
const AI_WAIT_TIMEOUT_MS = 12_000;
const MAX_TEXT_LENGTH = 4000;

type LocalMessage = TranscriptOut & { pending?: boolean };

const SIDE_PANEL_DOM_ID = "interview-side-panel";
const WEBCAM_DOM_ID = "interview-webcam";
const SIDE_PANEL_IDS: SidePanelId[] = ["code", "whiteboard"];
// 04-ux-design.md §6: <768px(Mobile)만 분할 뷰 대신 전체화면 모달.
const MOBILE_QUERY = "(max-width: 767px)";

export default function InterviewRoomPage() {
  const params = useParams<{ id: string }>();
  const interviewId = params.id;
  const router = useRouter();

  const [accessToken] = useState<string | null>(() => readAccessToken());
  const [interview, setInterview] = useState<InterviewDetailOut | null>(null);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [inputText, setInputText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [waitingForAi, setWaitingForAi] = useState(false);
  const [stubNotice, setStubNotice] = useState<string | null>(null);
  const [stage, setStage] = useState<"stt" | "llm" | "tts" | null>(null);

  // 음성 녹음 (unit-5, 04-ux-design §4 AudioRecorderControl: idle/recording/uploading/error)
  const [micSupported] = useState(
    () => typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && !!window.MediaRecorder,
  );
  const [hasVoiceConsent, setHasVoiceConsent] = useState<boolean | null>(null); // null=아직 서버에서 확인 안 됨
  const [showConsentPrompt, setShowConsentPrompt] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  // 보조 패널(unit-20): activePanel=현재 노출 패널(null=채팅만), mountedPanels=한 번이라도
  // 열린 패널(닫아도 unmount하지 않아 로컬 편집 내용을 보존, InterviewSidePanel 참고).
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [activePanel, setActivePanel] = useState<SidePanelId | null>(null);
  const [mountedPanels, setMountedPanels] = useState<Record<SidePanelId, boolean>>({
    code: false,
    whiteboard: false,
  });
  // null=화면 크기 기본값(모바일은 접힘, 그 외는 노출)을 따른다. 사용자가 토글하면 그 값으로 고정.
  const [webcamExpanded, setWebcamExpanded] = useState<boolean | null>(null);
  const tabRefs = useRef<Record<SidePanelId, HTMLButtonElement | null>>({ code: null, whiteboard: null });
  const lastOpenedPanelRef = useRef<SidePanelId>("code");
  const wasModalRef = useRef(false);

  const wsRef = useRef<WebSocket | null>(null);
  const waitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const timelineEndRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const maxRecordingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
    }
  }, [accessToken, router]);

  // 로딩(초기 진입): 세션 상세 + 대화 이력을 함께 불러온다.
  useEffect(() => {
    if (!accessToken || !interviewId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const [detail, transcripts] = await Promise.all([
          getInterview(accessToken!, interviewId),
          listTranscripts(accessToken!, interviewId),
        ]);
        if (cancelled) return;
        setInterview(detail);
        setMessages(transcripts);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            router.push("/login");
            return;
          }
          setLoadError(err.message);
        } else {
          setLoadError("네트워크 오류로 면접장을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [accessToken, interviewId, router]);

  // (unit-5) 마이크 버튼을 처음 누르기 전에 이미 유효한 biometric_voice 동의가
  // 있는지 서버에 물어 미리 확인해둔다(04-ux-design [C-06] "클라이언트가 로컬
  // 상태로 먼저 확인" — 서버 재조회가 보안 경계라는 원칙은 그대로, 이 조회는
  // UX상 불필요한 동의 팝업을 줄이기 위한 선제 확인일 뿐이다). 실패해도 채팅
  // 기능 자체를 막지 않고, 첫 녹음 시도 시 서버가 그대로 진위를 판정한다.
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    listMyConsents(accessToken)
      .then((consents: ConsentOut[]) => {
        if (cancelled) return;
        const active = consents.some((c) => c.consent_type === "biometric_voice" && c.revoked_at === null);
        setHasVoiceConsent(active);
      })
      .catch(() => {
        if (!cancelled) setHasVoiceConsent(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  // WebSocket 연결: 서버→클라이언트 push 전용 채널(§4.3). 턴 제출은 항상 REST로만 한다.
  useEffect(() => {
    if (!accessToken || !interviewId || !interview) return;
    // completed/expired 세션은 더 이상 진행형 대화가 없으므로 WS를 열지 않는다
    // (읽기 전용 이력 열람만 지원).
    if (interview.status !== "live" && interview.status !== "paused") return;

    let closedByCleanup = false;
    const ws = new WebSocket(interviewWsUrl(interviewId, accessToken));
    wsRef.current = ws;

    ws.onmessage = (event) => {
      let data: WsEvent;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.type === "stage_update" && data.job_id === activeJobIdRef.current) {
        setStage(data.stage);
      } else if (data.type === "turn_result" && data.job_id === activeJobIdRef.current) {
        clearWaitTimeout();
        setWaitingForAi(false);
        setStubNotice(null);
        setStage(null);
        activeJobIdRef.current = null;
        setMessages((prev) => [
          ...prev,
          {
            id: `ws-${data.job_id}`,
            interview_id: interviewId,
            question_id: null,
            turn_index: prev.length,
            speaker: "ai",
            input_mode: "text",
            content_text: data.ai_text,
            audio_ref: data.audio_url ?? null,
            created_at: new Date().toISOString(),
          },
        ]);
        // 04-ux-design §1.1 6-e: switch_to_coding이면 코드 에디터 패널을 노출한다.
        // 화이트보드용 제어 신호는 03-design §4.3 enum에 없어 사용자가 탭으로만 연다.
        if (data.control?.action === "switch_to_coding" && interview.status === "live") {
          openSidePanel("code");
        }
      } else if (data.type === "error" && data.job_id === activeJobIdRef.current) {
        clearWaitTimeout();
        setWaitingForAi(false);
        setStage(null);
        activeJobIdRef.current = null;
        setSubmitError(data.message || "AI 응답 처리 중 오류가 발생했습니다. 다시 시도해주세요.");
      }
    };

    ws.onerror = () => {
      // 연결 실패 자체가 화면을 막지는 않는다 — 턴 제출/조회는 REST로 계속 가능하고,
      // 실시간 진행상황 표시만 못 받을 뿐이다.
    };

    return () => {
      closedByCleanup = true;
      ws.close();
      if (wsRef.current === ws) wsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, interviewId, interview?.status]);

  useEffect(() => {
    timelineEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, stubNotice]);

  function clearWaitTimeout() {
    if (waitTimeoutRef.current) {
      clearTimeout(waitTimeoutRef.current);
      waitTimeoutRef.current = null;
    }
  }

  useEffect(() => () => clearWaitTimeout(), []);

  function openSidePanel(id: SidePanelId) {
    lastOpenedPanelRef.current = id;
    setMountedPanels((prev) => (prev[id] ? prev : { ...prev, [id]: true }));
    setActivePanel(id);
  }

  function toggleSidePanel(id: SidePanelId) {
    if (activePanel === id) {
      setActivePanel(null);
    } else {
      openSidePanel(id);
    }
  }

  // 모바일 모달이 닫히면 포커스를 그 패널을 연 탭으로 돌려준다(모달 중에는 탭이 inert라
  // 닫힌 뒤 렌더가 끝난 시점에 옮겨야 한다).
  const modalOpen = isMobile && activePanel !== null;
  useEffect(() => {
    if (wasModalRef.current && !modalOpen) {
      tabRefs.current[lastOpenedPanelRef.current]?.focus();
    }
    wasModalRef.current = modalOpen;
  }, [modalOpen]);

  const remainingChars = MAX_TEXT_LENGTH - inputText.length;
  const canSubmit = useMemo(
    () =>
      inputText.trim().length > 0 &&
      inputText.length <= MAX_TEXT_LENGTH &&
      !submitting &&
      !waitingForAi &&
      !recording &&
      !voiceUploading,
    [inputText, submitting, waitingForAi, recording, voiceUploading],
  );
  const canUseMic = useMemo(
    () => micSupported && !submitting && !waitingForAi && !voiceUploading,
    [micSupported, submitting, waitingForAi, voiceUploading],
  );

  // 텍스트/음성 공통: 202 응답 이후 stage_update/turn_result를 기다리다 unit-7
  // 미구현 스텁 경계에서 안내 문구로 전환하는 로직(unit-4 handleSubmit에서 추출).
  function beginWaitingForAi(jobId: string) {
    activeJobIdRef.current = jobId;
    setWaitingForAi(true);
    setStage(null);
    clearWaitTimeout();
    waitTimeoutRef.current = setTimeout(() => {
      setWaitingForAi(false);
      setStage(null);
      activeJobIdRef.current = null;
      setStubNotice(
        "AI 면접관의 실시간 응답 생성 기능은 아직 준비 중입니다(엔진 구현 예정, unit-7). 방금 보낸 답변은 서버에 정상적으로 저장되었습니다 — 계속해서 다음 답변을 입력해보실 수 있습니다.",
      );
    }, AI_WAIT_TIMEOUT_MS);
  }

  function describeApiError(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 410) return "이 세션은 만료되었습니다. 홈으로 이동해 새 면접을 시작해주세요.";
      if (err.status === 429) return "현재 이용자가 많습니다. 잠시 후 다시 시도해주세요.";
      return err.message;
    }
    return "네트워크 오류가 발생했습니다. 다시 시도해주세요.";
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!accessToken || !interview || interview.status !== "live" || !canSubmit) return;

    const text = inputText.trim();
    setSubmitting(true);
    setSubmitError(null);
    setStubNotice(null);

    const optimistic: LocalMessage = {
      id: `pending-${Date.now()}`,
      interview_id: interviewId,
      question_id: null,
      turn_index: messages.length,
      speaker: "user",
      input_mode: "text",
      content_text: text,
      audio_ref: null,
      created_at: new Date().toISOString(),
      pending: true,
    };

    try {
      const res = await submitTextTurn(accessToken, interviewId, text);
      setMessages((prev) => [...prev, { ...optimistic, pending: false }]);
      setInputText("");
      beginWaitingForAi(res.job_id);
    } catch (err) {
      setSubmitError(describeApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  // --- 음성 녹음 (unit-5, REQ-004/REQ-005) ---

  function stopRecordingTimers() {
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    if (maxRecordingTimeoutRef.current) {
      clearTimeout(maxRecordingTimeoutRef.current);
      maxRecordingTimeoutRef.current = null;
    }
  }

  function releaseMicStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  }

  useEffect(() => () => {
    stopRecordingTimers();
    releaseMicStream();
  }, []);

  async function startRecording() {
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      audioChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        stopRecordingTimers();
        releaseMicStream();
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        audioChunksRef.current = [];
        void handleVoiceUpload(blob);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => setRecordingSeconds((s) => s + 1), 1000);
      maxRecordingTimeoutRef.current = setTimeout(() => {
        // [C-06] 04-ux-design 명시값 아님 — 무제한 업로드 방지용 클라이언트 안전장치.
        mediaRecorderRef.current?.stop();
      }, MAX_RECORDING_MS);
    } catch {
      // 04-ux-design [C-06] "마이크 권한 없음": 음성 버튼 비활성 + 텍스트 입력만 강조.
      setVoiceError("마이크 권한이 거부되었거나 사용할 수 없습니다. 텍스트로 답변해주세요.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  function handleMicButtonClick() {
    if (recording) {
      stopRecording();
      return;
    }
    if (hasVoiceConsent === false || hasVoiceConsent === null) {
      // 04-ux-design [C-06]: 로컬 상태로 먼저 확인 후 없으면 인라인 동의 팝업.
      setShowConsentPrompt(true);
      return;
    }
    void startRecording();
  }

  async function handleGrantVoiceConsent() {
    if (!accessToken) return;
    try {
      await createConsent(accessToken, "biometric_voice");
      setHasVoiceConsent(true);
      setShowConsentPrompt(false);
      void startRecording();
    } catch (err) {
      setVoiceError(describeApiError(err));
    }
  }

  async function handleVoiceUpload(blob: Blob) {
    if (!accessToken || !interview) return;
    setVoiceUploading(true);
    setVoiceError(null);
    setSubmitError(null);
    try {
      const res = await submitVoiceTurn(accessToken, interviewId, blob);
      // 서버가 STT로 실제 변환한 텍스트를 반영하기 위해 이력을 다시 조회한다
      // (음성은 텍스트와 달리 클라이언트가 인식 결과를 미리 알 수 없다, 모듈 상단 설명 참고).
      const transcripts = await listTranscripts(accessToken, interviewId);
      setMessages(transcripts);
      beginWaitingForAi(res.job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403 && err.code === "CONSENT_REQUIRED_VOICE") {
        // DEC-023: 세션 도중 철회된 경우(§6.2 실시간 재검사) 여기서 다시 걸릴 수 있다.
        setHasVoiceConsent(false);
        setShowConsentPrompt(true);
        setVoiceError("음성 답변을 위한 생체정보(음성) 수집 동의가 필요합니다.");
      } else {
        setVoiceError(describeApiError(err));
      }
    } finally {
      setVoiceUploading(false);
    }
  }

  if (loading) {
    return (
      <div className="interview-room">
        <div className="interview-room__skeleton">면접장을 불러오는 중입니다...</div>
      </div>
    );
  }

  if (loadError || !interview) {
    return (
      <div className="interview-room">
        <div className="banner-error">{loadError ?? "면접 세션을 찾을 수 없습니다."}</div>
        <Link href="/">홈으로 돌아가기</Link>
      </div>
    );
  }

  // WS 연결/이력 열람은 live·paused 둘 다 허용하지만, 턴 제출은 백엔드가 `live`
  // 상태만 허용한다(interviews.py `submit_text_turn`) — paused에서 제출해 불필요한
  // 409 왕복을 만들지 않도록 프런트에서도 동일 기준으로 입력을 잠근다.
  const isLive = interview.status === "live" || interview.status === "paused";
  const canSubmitTurn = interview.status === "live";
  const isEmpty = messages.length === 0;
  // 코드/화이트보드는 턴 제출과 같은 기준(live)일 때만 연다 — 그 외 상태에서는 편집해도 면접
  // 평가 맥락에 반영되지 않고, 복원 전용 읽기 모드는 04 디자인서 범위 밖의 추가 UI다.
  const canUsePanels = interview.status === "live";
  const splitOpen = !isMobile && activePanel !== null;
  const showWebcam = webcamExpanded ?? !isMobile;

  return (
    <div className={`interview-room${splitOpen ? " interview-room--split" : ""}`}>
      <header className="interview-room__header">
        <h1>면접장</h1>
        <span className={`status-badge status-badge--${interview.status}`}>{interview.status}</span>
      </header>

      {!isLive && (
        <div className="banner-info">
          이 세션은 현재 진행 중(live)이 아니라 대화 이력만 열람할 수 있습니다 (상태: {interview.status}).
        </div>
      )}

      <div className="interview-room__toolbar" inert={modalOpen}>
        <div className="interview-room__tabs" role="group" aria-label="보조 패널 전환">
          {SIDE_PANEL_IDS.map((id) => (
            <button
              key={id}
              type="button"
              ref={(el) => {
                tabRefs.current[id] = el;
              }}
              className={`room-tab${activePanel === id ? " room-tab--active" : ""}`}
              aria-pressed={activePanel === id}
              aria-controls={SIDE_PANEL_DOM_ID}
              disabled={!canUsePanels}
              onClick={() => toggleSidePanel(id)}
            >
              {SIDE_PANEL_LABEL[id]}
            </button>
          ))}
          {!canUsePanels && (
            <span className="room-tabs__note">면접이 진행 중(live)일 때만 사용할 수 있습니다.</span>
          )}
        </div>
        <div className="interview-room__webcam">
          <button
            type="button"
            className="ghost-button interview-room__webcam-toggle"
            aria-expanded={showWebcam}
            aria-controls={WEBCAM_DOM_ID}
            onClick={() => setWebcamExpanded(!showWebcam)}
          >
            {showWebcam ? "웹캠 숨기기" : "웹캠 보기"}
          </button>
          {showWebcam && (
            <div id={WEBCAM_DOM_ID}>
              <WebcamPreview variant="tile" className="webcam-tile" />
            </div>
          )}
        </div>
      </div>

      <div className="interview-room__body">
        <div className="interview-room__chat" inert={modalOpen}>
          <div className="interview-room__timeline">
            {isEmpty && canSubmitTurn && (
              <div className="chat-empty">
                AI 면접관이 질문을 준비하고 있습니다... (세션 시작 시 자동으로 첫 질문이 enqueue되지만, 실제 AI
                응답 생성 엔진은 아직 준비 중입니다 — 아래 입력창에서 자유롭게 첫 답변을 입력해도 저장됩니다.)
              </div>
            )}
            {isEmpty && !canSubmitTurn && <div className="chat-empty">아직 대화 이력이 없습니다.</div>}

            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble chat-bubble--${m.speaker}`}>
                <div className="chat-bubble__meta">
                  {m.speaker === "ai" ? "AI 면접관" : "나"} · {m.input_mode === "voice" ? "음성" : "텍스트"}
                  {m.pending && " · 전송 중..."}
                </div>
                <div className="chat-bubble__text">{m.content_text}</div>
              </div>
            ))}

            {voiceUploading && (
              <div className="chat-bubble chat-bubble--user chat-bubble--processing">
                <div className="chat-bubble__meta">나 · 음성</div>
                <div className="chat-bubble__text">음성 인식 중...</div>
              </div>
            )}

            {waitingForAi && (
              <div className="chat-bubble chat-bubble--ai chat-bubble--processing">
                <div className="chat-bubble__meta">AI 면접관</div>
                <div className="chat-bubble__text">
                  {stage === "stt" && "음성 인식 중..."}
                  {stage === "llm" && "AI가 답변을 준비하고 있어요..."}
                  {stage === "tts" && "음성 합성 중..."}
                  {!stage && "AI가 답변을 준비하고 있어요..."}
                </div>
              </div>
            )}

            {stubNotice && <div className="banner-info chat-stub-notice">{stubNotice}</div>}

            <div ref={timelineEndRef} />
          </div>

          {submitError && <div className="banner-error">{submitError}</div>}
          {voiceError && <div className="banner-error">{voiceError}</div>}

          {showConsentPrompt && (
            <div className="voice-consent-prompt banner-info">
              <p>
                음성으로 답변하려면 생체정보(음성) 수집 동의가 필요합니다. 동의 시 답변 음성은 텍스트 변환 즉시
                폐기되며, 변환된 텍스트만 저장됩니다.
              </p>
              <div className="voice-consent-prompt__actions">
                <button type="button" className="submit-button" onClick={handleGrantVoiceConsent}>
                  동의하고 녹음 시작
                </button>
                <button type="button" className="ghost-button" onClick={() => setShowConsentPrompt(false)}>
                  취소
                </button>
              </div>
            </div>
          )}

          <form className="interview-room__composer" onSubmit={handleSubmit}>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder={canSubmitTurn ? "답변을 입력하세요..." : "이 세션은 현재 답변을 제출할 수 없습니다."}
              disabled={!canSubmitTurn || submitting || waitingForAi || recording || voiceUploading}
              maxLength={MAX_TEXT_LENGTH}
              rows={3}
            />
            <div className="interview-room__composer-footer">
              <span className={`char-counter ${remainingChars < 0 ? "char-counter--over" : ""}`}>
                {inputText.length}/{MAX_TEXT_LENGTH}
              </span>
              {micSupported && (
                <button
                  type="button"
                  className={`mic-button ${recording ? "mic-button--recording" : ""}`}
                  onClick={handleMicButtonClick}
                  disabled={!canSubmitTurn || !canUseMic}
                  aria-pressed={recording}
                >
                  {recording
                    ? `녹음 중지 (${recordingSeconds}s)`
                    : voiceUploading
                      ? "인식 중..."
                      : "음성으로 답변"}
                </button>
              )}
              <button
                type="submit"
                className="submit-button"
                disabled={!canSubmitTurn || !canSubmit || recording || voiceUploading}
              >
                {submitting ? "전송 중..." : "전송"}
              </button>
            </div>
          </form>
        </div>

        <InterviewSidePanel
          domId={SIDE_PANEL_DOM_ID}
          interviewId={interviewId}
          accessToken={accessToken}
          active={activePanel}
          mounted={mountedPanels}
          modal={modalOpen}
          onClose={() => setActivePanel(null)}
        />
      </div>
    </div>
  );
}

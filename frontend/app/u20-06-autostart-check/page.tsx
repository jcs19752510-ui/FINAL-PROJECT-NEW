"use client";

// 06단계(unit-20) 임시 검증 라우트 — DEF-001(unit-16-test.md §6) autoStart 경로의 SSR/hydration을
// 재확인하기 위한 용도. [C-05] 장치점검 화면이 아직 없어(unit-20-note.md §9 Q1) autoStart props가
// 쓰이는 실제 화면이 없으므로, 05단계와 동일한 방식으로 임시 라우트를 만들어 검증한 뒤 삭제한다.
// 저장소에 영구히 남기지 않는다(def001-static.spec.ts E2E_AUTOSTART_PATH 안내 주석 참고).
import WebcamPreview from "@/components/WebcamPreview";

export default function AutoStartCheckPage() {
  return <WebcamPreview variant="panel" autoStart />;
}

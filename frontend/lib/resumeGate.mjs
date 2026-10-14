// 면접 시작 API의 RESUME_REQUIRED(409) 및 이력서 profile_status → 안내 문구 매핑 (순수 로직).
export const RESUME_REQUIRED_CODE = "RESUME_REQUIRED";
export const RESUME_REQUIRED_MESSAGE =
  "이력서가 있어야 맞춤 면접을 시작할 수 있어요. 글자를 읽을 수 있는 PDF(스캔본 말고)로 이력서를 제출해 주세요.";
export const RESUME_UNREADABLE_MESSAGE = "이력서에서 글자를 읽지 못했습니다. 글자를 읽을 수 있는 PDF(스캔본 말고)로 다시 제출해 주세요.";
export const APPLY_PATH = "/apply";

/** @param {unknown} err */
export function isResumeRequiredError(err) {
  return (
    typeof err === "object" && err !== null && "code" in err && err.code === RESUME_REQUIRED_CODE
  );
}

/** RESUME_REQUIRED면 안내 박스 정보, 아니면 null. */
export function resumeRequiredNotice(err) {
  if (!isResumeRequiredError(err)) return null;
  return { message: RESUME_REQUIRED_MESSAGE, href: APPLY_PATH, linkLabel: "이력서 제출하러 가기" };
}

/** profile_status==='unreadable'일 때만 경고 문구, 아니면 null (null/undefined 안전). */
export function profileStatusWarning(status) {
  if (!status || status.profile_status !== "unreadable") return null;
  return RESUME_UNREADABLE_MESSAGE;
}

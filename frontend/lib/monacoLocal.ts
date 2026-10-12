"use client";

/**
 * Monaco 에디터를 인터넷 CDN 대신 같은 서버(/monaco/vs)에서 읽도록 설정한다
 * (2026-10-12, 온프리미스/폐쇄망 대응 — 사용자 승인).
 *
 * `@monaco-editor/react` 의 기본값은 https://cdn.jsdelivr.net/npm/monaco-editor@.../min/vs 이다.
 * 내부망 PC 는 이 주소에 닿지 않아 에디터가 로딩 상태에서 멈춘다. `scripts/copy-monaco.mjs` 가
 * 설치/빌드 시 node_modules/monaco-editor/min/vs 를 public/monaco/vs 로 복사해 두며, 이 모듈을
 * import 하는 것만으로 loader 설정이 적용된다(모듈은 번들당 한 번만 평가된다).
 */
import { loader } from "@monaco-editor/react";

export const MONACO_VS_PATH = "/monaco/vs";

loader.config({ paths: { vs: MONACO_VS_PATH } });

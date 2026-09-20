"use client";

import { useSyncExternalStore } from "react";

// 04-ux-design.md §6 반응형 분기(모바일=전체화면 모달 / 태블릿·데스크톱=분할 뷰)를 CSS만으로는
// 표현할 수 없는 부분(dialog 시맨틱, inert, 웹캠 타일 기본 접힘)에 쓴다.
// 서버 스냅샷은 false(=모바일 아님)로 고정해 SSR/hydration 결과가 환경에 따라 갈리지 않게 한다.
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

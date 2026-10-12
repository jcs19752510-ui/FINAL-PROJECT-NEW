// 채용담당자 지원자 리포트 목록의 통계 계산(차트용) — 순수 함수라 화면과 분리해 테스트한다. (2026-10-12)

export interface StatsItem {
  status: string;
  overall_score: string | null;
}

export interface StatusCount {
  key: string;
  label: string;
  count: number;
}

export interface ScoreBin {
  range: string;
  count: number;
}

export interface ScoreStats {
  bins: ScoreBin[];
  scored: number; // 점수가 있는 건수
  unscored: number; // 점수가 없거나 해석할 수 없는 건수
}

const STATUS_ORDER = ["scheduled", "live", "paused", "completed", "expired"] as const;

export function countByStatus(items: StatsItem[], labels: Record<string, string>): StatusCount[] {
  const counts = new Map<string, number>();
  for (const item of items) counts.set(item.status, (counts.get(item.status) ?? 0) + 1);
  const known = STATUS_ORDER.map((key) => ({ key, label: labels[key] ?? key, count: counts.get(key) ?? 0 }));
  // 목록에 없는 새 상태값이 오더라도 누락되지 않게 뒤에 덧붙인다.
  const extras = [...counts.keys()]
    .filter((key) => !(STATUS_ORDER as readonly string[]).includes(key))
    .map((key) => ({ key, label: labels[key] ?? key, count: counts.get(key) ?? 0 }));
  return [...known, ...extras];
}

// 점수는 1~5점 척도. [1,2) [2,3) [3,4) [4,5] 네 구간(5점은 마지막 구간에 포함).
export function scoreHistogram(items: StatsItem[]): ScoreStats {
  const bins: ScoreBin[] = [
    { range: "1~2점", count: 0 },
    { range: "2~3점", count: 0 },
    { range: "3~4점", count: 0 },
    { range: "4~5점", count: 0 },
  ];
  let scored = 0;
  let unscored = 0;
  for (const item of items) {
    const value = item.overall_score === null ? NaN : Number(item.overall_score);
    if (!Number.isFinite(value) || value < 1 || value > 5) {
      unscored += 1;
      continue;
    }
    const index = Math.min(Math.floor(value) - 1, 3);
    bins[index].count += 1;
    scored += 1;
  }
  return { bins, scored, unscored };
}

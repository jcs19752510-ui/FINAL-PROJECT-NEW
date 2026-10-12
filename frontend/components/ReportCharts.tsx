"use client";

/**
 * 채용담당자 지원자 리포트 목록의 통계 차트 (원본 계획서 4.1 Recruiter Dashboard의 Recharts 시각화, 2026-10-12).
 * 서버가 내려준 목록(추가 API 호출 없음)으로 "면접 상태 분포"와 "종합 점수 분포"를 막대 차트로 보여준다.
 * 색은 라이트/다크 배경 모두에서 읽히는 중간 파랑을 쓰고, 글자색은 부모(currentColor)를 따른다.
 */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { countByStatus, scoreHistogram, type StatsItem } from "../lib/reportStats";

const BAR_COLOR = "#3b7de0";

interface Props {
  reports: StatsItem[];
  statusLabels: Record<string, string>;
}

function ChartBox({ title, summary, children }: { title: string; summary: string; children: React.ReactNode }) {
  return (
    <figure style={{ margin: 0, flex: "1 1 280px", minWidth: 0 }}>
      <figcaption style={{ fontWeight: 700, marginBottom: 6 }}>{title}</figcaption>
      <div role="img" aria-label={`${title}: ${summary}`} style={{ width: "100%", height: 200 }}>
        {children}
      </div>
    </figure>
  );
}

export default function ReportCharts({ reports, statusLabels }: Props) {
  if (reports.length === 0) return null;
  const statusData = countByStatus(reports, statusLabels);
  const { bins, scored, unscored } = scoreHistogram(reports);
  const statusSummary = statusData.map((d) => `${d.label} ${d.count}건`).join(", ");
  const scoreSummary = scored === 0 ? "점수가 있는 리포트가 없습니다" : bins.map((b) => `${b.range} ${b.count}건`).join(", ");

  return (
    <section aria-label="리포트 통계" style={{ display: "flex", flexWrap: "wrap", gap: 24, margin: "12px 0 20px" }}>
      <ChartBox title="면접 상태 분포" summary={statusSummary}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={statusData} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.2} />
            <XAxis dataKey="label" tick={{ fill: "currentColor", fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} />
            <Tooltip formatter={(value) => [`${value}건`, "건수"]} />
            <Bar dataKey="count" fill={BAR_COLOR} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartBox>
      <ChartBox title="종합 점수 분포" summary={scoreSummary}>
        {scored === 0 ? (
          <p style={{ margin: 0, opacity: 0.7 }}>아직 점수가 있는 리포트가 없습니다.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={bins} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.2} />
              <XAxis dataKey="range" tick={{ fill: "currentColor", fontSize: 12 }} />
              <YAxis allowDecimals={false} tick={{ fill: "currentColor", fontSize: 12 }} />
              <Tooltip formatter={(value) => [`${value}건`, "건수"]} />
              <Bar dataKey="count" fill={BAR_COLOR} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
        {unscored > 0 && scored > 0 ? (
          <p style={{ margin: "4px 0 0", fontSize: 12, opacity: 0.7 }}>점수 미산출 {unscored}건은 제외</p>
        ) : null}
      </ChartBox>
    </section>
  );
}

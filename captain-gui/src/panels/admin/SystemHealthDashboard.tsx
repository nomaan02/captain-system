import type { DiagnosticScore } from "@/api/types";
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer } from "recharts";
import { Badge } from "@/components/Badge";
import { HeartPulse } from "lucide-react";

interface Props {
  scores: DiagnosticScore[];
}

export function SystemHealthDashboard({ scores }: Props) {
  const chartData = scores.map((s) => ({
    dimension: s.dimension.replace(/_/g, " "),
    score: s.score ?? 0,
    fullMark: 100,
  }));

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <HeartPulse className="h-3.5 w-3.5" /> System Health (8 Dimensions)
        </span>
      </div>

      {scores.length === 0 ? (
        <p className="text-sm text-gray-400">No diagnostic data</p>
      ) : (
        <>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={chartData}>
                <PolarGrid stroke="#374151" />
                <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 9, fill: "#9ca3af" }} />
                <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 8 }} />
                <Radar name="Score" dataKey="score" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-2 grid grid-cols-2 gap-1">
            {scores.map((s) => {
              const cls =
                s.status === "CRITICAL" ? "bg-red-500/20 text-red-600"
                : s.status === "DEGRADED" ? "bg-yellow-500/20 text-yellow-700"
                : "bg-green-500/20 text-green-600";
              return (
                <div key={s.dimension} className="flex items-center justify-between rounded px-2 py-1 text-xs">
                  <span className="text-gray-600 dark:text-gray-300">{s.dimension}</span>
                  <Badge label={`${s.score ?? 0}`} className={cls} />
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

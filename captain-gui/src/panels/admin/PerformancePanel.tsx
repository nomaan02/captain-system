import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp } from "lucide-react";

interface Props {
  // Performance data will come from reports or dashboard extensions
  data?: Array<{ label: string; pnl: number }>;
}

export function PerformancePanel({ data = [] }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <TrendingUp className="h-3.5 w-3.5" /> Performance
        </span>
      </div>
      {data.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          Performance data available via RPT-02 / RPT-10
        </p>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar
                dataKey="pnl"
                fill="#3b82f6"
                radius={[2, 2, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

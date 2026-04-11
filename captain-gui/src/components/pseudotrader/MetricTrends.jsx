import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";

const CHART_GRID = { stroke: "#1e293b", strokeDasharray: "3 3" };
const TICK_STYLE = { fill: "#94a3b8", fontSize: 9, fontFamily: "JetBrains Mono" };
const TOOLTIP_STYLE = {
  backgroundColor: "#111827",
  border: "1px solid #2e4e5a",
  fontFamily: "JetBrains Mono",
  fontSize: 11,
};

const formatDate = (val) =>
  new Date(val).toLocaleDateString("en-US", {
    month: "short", day: "numeric", timeZone: "America/New_York",
  });

const MetricTrends = ({ trends }) => {
  const dailyCounts = useMemo(() => {
    const map = {};
    trends.forEach((t) => {
      const day = new Date(t.ts).toLocaleDateString("en-US", { timeZone: "America/New_York" });
      if (!map[day]) map[day] = { date: day, adopt: 0, reject: 0 };
      if (t.recommendation === "ADOPT") map[day].adopt++;
      else if (t.recommendation === "REJECT") map[day].reject++;
    });
    return Object.values(map).sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [trends]);

  if (trends.length === 0) {
    return (
      <div className="text-[#64748b] text-xs font-mono py-6 text-center">
        No trend data available
      </div>
    );
  }

  const sorted = [...trends].sort((a, b) => new Date(a.ts) - new Date(b.ts));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* D11 Metrics Over Time */}
      <div>
        <div className="text-[10px] text-[#64748b] font-mono mb-2 uppercase tracking-wider">
          D11 Metrics Over Time
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={sorted} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid {...CHART_GRID} />
            <XAxis dataKey="ts" tickFormatter={formatDate} tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={formatDate} />
            <Legend wrapperStyle={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
            <Line type="monotone" dataKey="sharpe_improvement" stroke="#10b981" dot={false} strokeWidth={1.5} name="Sharpe Imp." />
            <Line type="monotone" dataKey="pbo" stroke="#06b6d4" dot={false} strokeWidth={1.5} name="PBO" />
            <Line type="monotone" dataKey="dsr" stroke="#f59e0b" dot={false} strokeWidth={1.5} name="DSR" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Adopt/Reject Ratio */}
      <div>
        <div className="text-[10px] text-[#64748b] font-mono mb-2 uppercase tracking-wider">
          Adopt / Reject Ratio
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={dailyCounts} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid {...CHART_GRID} />
            <XAxis dataKey="date" tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Legend wrapperStyle={{ fontSize: 10, fontFamily: "JetBrains Mono" }} />
            <Bar dataKey="adopt" fill="#10b981" name="Adopt" />
            <Bar dataKey="reject" fill="#ef4444" name="Reject" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default MetricTrends;

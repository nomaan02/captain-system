import { useMemo } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";

const CHART_GRID = { stroke: "#1e293b", strokeDasharray: "3 3" };
const TICK_STYLE = { fill: "#94a3b8", fontSize: 9, fontFamily: "JetBrains Mono" };
const TOOLTIP_STYLE = {
  backgroundColor: "#111827",
  border: "1px solid #2e4e5a",
  fontFamily: "JetBrains Mono",
  fontSize: 11,
};

const LINE_COLORS = {
  full_history: "#06b6d4",
  rolling_252: "#f59e0b",
};

function extractCurveData(equityCurve) {
  if (!equityCurve) return null;
  if (Array.isArray(equityCurve) && equityCurve.length > 0) return equityCurve;
  if (typeof equityCurve === "object") {
    const keys = Object.keys(equityCurve);
    if (keys.length === 0) return null;
    // Handle { dates: [...], values: [...] } shape
    if (equityCurve.dates && equityCurve.values) {
      return equityCurve.dates.map((d, i) => ({
        date: d,
        equity: equityCurve.values[i],
      }));
    }
    // Handle { equity: [...] } shape
    if (equityCurve.equity && Array.isArray(equityCurve.equity)) {
      return equityCurve.equity.map((v, i) => ({ index: i, equity: v }));
    }
  }
  return null;
}

const MetricsTable = ({ metrics }) => {
  if (!metrics || typeof metrics !== "object") return null;
  const entries = Object.entries(metrics);
  if (entries.length === 0) return null;

  return (
    <div className="mb-3">
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between py-0.5 border-b border-border-subtle last:border-b-0">
          <span className="text-[10px] text-[#94a3b8] font-mono">{k.replace(/_/g, " ")}</span>
          <span className="text-[10px] text-white font-mono">
            {typeof v === "number" ? v.toFixed(4) : String(v ?? "\u2014")}
          </span>
        </div>
      ))}
    </div>
  );
};

const ForecastPanel = ({ forecast, color }) => {
  const curveData = useMemo(() => extractCurveData(forecast.equity_curve), [forecast.equity_curve]);
  const xKey = curveData && curveData.length > 0
    ? (curveData[0].date != null ? "date" : "index")
    : "index";

  return (
    <div>
      <div className="text-[10px] text-[#64748b] font-mono mb-2 uppercase tracking-wider">
        {forecast.forecast_type?.replace(/_/g, " ") || "Forecast"}
        {forecast.version && (
          <span className="ml-2 text-[#475569]">v{forecast.version}</span>
        )}
      </div>

      <MetricsTable metrics={forecast.metrics} />

      {curveData ? (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={curveData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid {...CHART_GRID} />
            <XAxis dataKey={xKey} tick={TICK_STYLE} />
            <YAxis tick={TICK_STYLE} />
            <Tooltip contentStyle={TOOLTIP_STYLE} />
            <Line type="monotone" dataKey="equity" stroke={color} dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="text-[#475569] text-[10px] font-mono py-4 text-center border border-border-subtle">
          No equity curve data
        </div>
      )}
    </div>
  );
};

const ForecastComparison = ({ forecasts }) => {
  if (forecasts.length === 0) {
    return (
      <div className="text-[#64748b] text-xs font-mono py-6 text-center">
        No forecast data available
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {forecasts.map((f) => (
        <ForecastPanel
          key={f.forecast_id || f.forecast_type}
          forecast={f}
          color={LINE_COLORS[f.forecast_type] || "#06b6d4"}
        />
      ))}
    </div>
  );
};

export default ForecastComparison;

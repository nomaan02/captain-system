import { useEffect, useCallback } from "react";
import usePseudotraderStore from "../stores/pseudotraderStore";
import DecisionLog from "../components/pseudotrader/DecisionLog";
import HealthChecklist from "../components/pseudotrader/HealthChecklist";
import ParameterPanels from "../components/pseudotrader/ParameterPanels";
import GateActivityFeed from "../components/pseudotrader/GateActivityFeed";
import MetricTrends from "../components/pseudotrader/MetricTrends";
import ForecastComparison from "../components/pseudotrader/ForecastComparison";
import VersionTimeline from "../components/pseudotrader/VersionTimeline";
import StatBox from "../components/shared/StatBox";

const PanelCard = ({ title, children, headerRight }) => (
  <div className="bg-surface-card border border-border-subtle p-3">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase">{title}</h3>
      {headerRight}
    </div>
    {children}
  </div>
);

const PseudotraderPage = () => {
  const {
    decisions, parameters, health, trends, versions, forecasts,
    loading, error, fetchAll, fetchHealth,
  } = usePseudotraderStore();

  useEffect(() => {
    fetchAll();
  }, []);

  // Auto-refresh health every 30 seconds
  const refreshHealth = useCallback(() => {
    fetchHealth();
  }, [fetchHealth]);

  useEffect(() => {
    const id = setInterval(refreshHealth, 30000);
    return () => clearInterval(id);
  }, [refreshHealth]);

  if (loading) {
    return (
      <div className="h-full bg-surface p-4 flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-[#00ad74] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Summary stats
  const adoptCount = decisions.filter((d) => d.recommendation === "ADOPT").length;
  const rejectCount = decisions.filter((d) => d.recommendation === "REJECT").length;
  const adoptRate = decisions.length > 0
    ? ((adoptCount / decisions.length) * 100).toFixed(1)
    : null;

  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      {/* Title row */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-mono text-white tracking-[2px] uppercase">
          Pseudotrader
        </h1>
        <button
          onClick={fetchAll}
          className="px-2 py-1 text-[9px] font-mono border border-solid bg-transparent border-[#2e4e5a] text-[#64748b] cursor-pointer hover:bg-[rgba(100,116,139,0.05)] hover:text-white transition-colors"
        >
          Refresh All
        </button>
      </div>

      {error && (
        <div className="mb-4 p-2 bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.3)] text-[#ef4444] text-xs font-mono">
          {error}
        </div>
      )}

      {/* Summary stats row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <StatBox label="Total Decisions" value={decisions.length} />
        <StatBox label="Adopted" value={adoptCount} color="text-[#10b981]" />
        <StatBox label="Rejected" value={rejectCount} color="text-[#ef4444]" />
        <StatBox
          label="Adopt Rate"
          value={adoptRate != null ? `${adoptRate}%` : "\u2014"}
          color={adoptRate >= 50 ? "text-[#10b981]" : "text-[#f59e0b]"}
        />
        <StatBox label="Versions" value={versions.length} />
      </div>

      {/* Main content: Decision Log + Health Checklist */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 mb-4">
        {/* Decision Log (3/4 width on large screens) */}
        <div className="lg:col-span-3">
          <PanelCard
            title="Decision Log"
            headerRight={
              <span className="text-[11px] text-[#64748b] font-mono">
                {decisions.length} entries
              </span>
            }
          >
            <DecisionLog decisions={decisions} />
          </PanelCard>
        </div>

        {/* Health Checklist (1/4 width on large screens) */}
        <div className="lg:col-span-1">
          <PanelCard
            title="Health"
            headerRight={
              <button
                onClick={refreshHealth}
                className="px-2 py-1 text-[9px] font-mono border border-solid bg-transparent border-[#2e4e5a] text-[#64748b] cursor-pointer hover:bg-[rgba(100,116,139,0.05)] transition-colors"
              >
                Refresh
              </button>
            }
          >
            <HealthChecklist health={health} />
          </PanelCard>
        </div>
      </div>

      {/* Gated Parameters */}
      <div className="mb-4">
        <PanelCard title="Gated Parameters"
          headerRight={<span className="text-[11px] text-[#64748b] font-mono">D02 + D05 + D12</span>}>
          <ParameterPanels parameters={parameters} />
        </PanelCard>
      </div>

      {/* Gate Activity Feed */}
      <div className="mb-4">
        <PanelCard title="Gate Activity"
          headerRight={<span className="text-[11px] text-[#64748b] font-mono">b3_pseudotrader</span>}>
          <GateActivityFeed maxHeight="250px" />
        </PanelCard>
      </div>

      {/* Metric Trends */}
      <div className="mb-4">
        <PanelCard title="Metric Trends"
          headerRight={<span className="text-[11px] text-[#64748b] font-mono">D11 time series</span>}>
          <MetricTrends trends={trends} />
        </PanelCard>
      </div>

      {/* Forecast Comparison */}
      <div className="mb-4">
        <PanelCard title="Forecast Comparison"
          headerRight={<span className="text-[11px] text-[#64748b] font-mono">D27 dual forecasts</span>}>
          <ForecastComparison forecasts={forecasts} />
        </PanelCard>
      </div>

      {/* Version History */}
      <div className="mb-4">
        <PanelCard title="Version History"
          headerRight={<span className="text-[11px] text-[#64748b] font-mono">{versions.length} snapshots</span>}>
          <VersionTimeline versions={versions} />
        </PanelCard>
      </div>
    </div>
  );
};

export default PseudotraderPage;

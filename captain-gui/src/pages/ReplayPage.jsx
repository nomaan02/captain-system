import React, { useEffect } from "react";
import TopBar from "../components/layout/TopBar";
import ReplayConfigPanel from "../components/replay/ReplayConfigPanel";
import PipelineStepper from "../components/replay/PipelineStepper";
import BlockDetail from "../components/replay/BlockDetail";
import AssetCard from "../components/replay/AssetCard";
import PlaybackControls from "../components/replay/PlaybackControls";
import SimulatedPosition from "../components/replay/SimulatedPosition";
import ReplaySummary from "../components/replay/ReplaySummary";
import WhatIfComparison from "../components/replay/WhatIfComparison";
import ReplayHistory from "../components/replay/ReplayHistory";
import useReplayStore from "../stores/replayStore";
import api from "../api/client";

// Expose store on window in dev mode for debugging
if (import.meta.env.DEV) {
  window.__replayStore = useReplayStore;
}

// Error boundary to catch and display component crashes instead of blank screen
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error, info) {
    console.error("ReplayPage ErrorBoundary:", error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-2 bg-[rgba(239,68,68,0.1)] border border-solid border-[#ef4444] m-1 font-mono text-[10px]">
          <div className="text-[#ef4444] text-[11px] mb-1">Component Error: {this.props.name || "unknown"}</div>
          <div className="text-[#e2e8f0] break-all">{this.state.error.message}</div>
        </div>
      );
    }
    return this.props.children;
  }
}

const ReplayPage = () => {
  const assetOrder = useReplayStore((s) => s.assetOrder);
  const assetResults = useReplayStore((s) => s.assetResults);
  const expandedStage = useReplayStore((s) => s.expandedStage);
  const status = useReplayStore((s) => s.status);

  // Load presets + history on mount
  useEffect(() => {
    api.replayPresets().then((data) => {
      const list = data?.presets ?? data;
      useReplayStore.getState().setPresets(Array.isArray(list) ? list : []);
    }).catch(() => {});
    api.replayHistory().then((data) => {
      const list = data?.replays ?? data?.history ?? data;
      useReplayStore.getState().setHistory(Array.isArray(list) ? list : []);
    }).catch(() => {});
  }, []);

  return (
    <div data-testid="replay-page" className="h-screen w-full bg-[#0a0f0d] overflow-hidden flex flex-col text-white font-mono">
      {/* TopBar */}
      <div className="shrink-0">
        <TopBar />
      </div>

      {/* Playback controls bar */}
      <div className="shrink-0">
        <ErrorBoundary name="PlaybackControls"><PlaybackControls /></ErrorBoundary>
      </div>

      {/* Main content: 3-column CSS grid layout */}
      <div className="flex-1 min-h-0 grid grid-cols-[280px_1fr_280px]">
        {/* Left Column -- Config + Pipeline */}
        <div className="h-full overflow-y-auto border-r border-solid border-[#1e293b]">
          <ErrorBoundary name="ReplayConfigPanel"><ReplayConfigPanel /></ErrorBoundary>
          <ErrorBoundary name="PipelineStepper"><PipelineStepper /></ErrorBoundary>
          {expandedStage && (
            <ErrorBoundary name="BlockDetail"><BlockDetail blockId={expandedStage} /></ErrorBoundary>
          )}
        </div>

        {/* Center Column -- Asset Cards + Simulated Position */}
        <div className="h-full flex flex-col overflow-hidden">
          {/* Simulated position */}
          <div className="shrink-0">
            <ErrorBoundary name="SimulatedPosition"><SimulatedPosition /></ErrorBoundary>
          </div>

          {/* Asset cards grid */}
          <div className="flex-1 overflow-y-auto p-3">
            {assetOrder.length === 0 && status === "idle" && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-[12px] text-[#64748b] font-mono mb-2">Session Replay</div>
                <div className="text-[10px] text-[#4a5568] font-mono max-w-[300px]">
                  Configure parameters on the left and click RUN REPLAY to simulate a historical trading session.
                </div>
              </div>
            )}
            {assetOrder.length === 0 && status === "running" && (
              <div className="flex items-center justify-center h-full">
                <div className="text-[11px] text-[#06b6d4] font-mono animate-pulse">
                  Initializing replay...
                </div>
              </div>
            )}
            {assetOrder.length > 0 && (
              <div data-testid="asset-card-grid" className="grid grid-cols-2 gap-2">
                {assetOrder.map((asset) => (
                  <ErrorBoundary key={asset} name={`AssetCard-${asset}`}>
                    <AssetCard asset={asset} data={assetResults[asset]} />
                  </ErrorBoundary>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column -- Summary + What-If + History */}
        <div className="h-full overflow-y-auto border-l border-solid border-[#1e293b]">
          <ErrorBoundary name="ReplaySummary"><ReplaySummary /></ErrorBoundary>
          <ErrorBoundary name="WhatIfComparison"><WhatIfComparison /></ErrorBoundary>
          <ErrorBoundary name="ReplayHistory"><ReplayHistory /></ErrorBoundary>
        </div>
      </div>
    </div>
  );
};

export default ReplayPage;

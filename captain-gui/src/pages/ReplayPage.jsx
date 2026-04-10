import React, { useEffect, useState, useRef, useCallback } from "react";
import ReplayConfigPanel from "../components/replay/ReplayConfigPanel";
import PipelineStepper from "../components/replay/PipelineStepper";
import BlockDetail from "../components/replay/BlockDetail";
import AssetCard from "../components/replay/AssetCard";
import PlaybackControls from "../components/replay/PlaybackControls";
import SimulatedPosition from "../components/replay/SimulatedPosition";
import ReplaySummary from "../components/replay/ReplaySummary";
import WhatIfComparison from "../components/replay/WhatIfComparison";
import ReplayHistory from "../components/replay/ReplayHistory";
import BatchPnlReport from "../components/replay/BatchPnlReport";
import useReplayStore from "../stores/replayStore";
import useWebSocket from "../ws/useWebSocket";
import api from "../api/client";

if (import.meta.env.DEV) {
  window.__replayStore = useReplayStore;
}

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

const ResizableBottomPanel = ({ expandedStage }) => {
  const [panelHeight, setPanelHeight] = useState(250);
  const isDragging = useRef(false);
  const startY = useRef(0);
  const startH = useRef(0);

  const onMouseDown = useCallback((e) => {
    isDragging.current = true;
    startY.current = e.clientY;
    startH.current = panelHeight;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, [panelHeight]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!isDragging.current) return;
      const delta = startY.current - e.clientY;
      const newH = Math.min(Math.max(startH.current + delta, 100), window.innerHeight * 0.7);
      setPanelHeight(newH);
    };
    const onMouseUp = () => {
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div className="shrink-0 border-t border-solid border-[#1e293b] bg-[#080e0d]">
      <ErrorBoundary name="PipelineStepper">
        <div className="flex justify-center">
          <PipelineStepper />
        </div>
      </ErrorBoundary>
      {expandedStage && (
        <>
          {/* Drag handle */}
          <div
            onMouseDown={onMouseDown}
            className="h-[5px] cursor-row-resize border-t border-solid border-[#1e293b] hover:bg-[#10b981]/30 active:bg-[#10b981]/50 transition-colors"
          />
          <ErrorBoundary name="BlockDetail">
            <div style={{ height: panelHeight }} className="overflow-y-auto">
              <BlockDetail blockId={expandedStage} />
            </div>
          </ErrorBoundary>
        </>
      )}
    </div>
  );
};

const ReplayPage = () => {
  // WebSocket connection — required to receive replay streaming events
  useWebSocket("primary_user");

  const assetOrder = useReplayStore((s) => s.assetOrder);
  const assetResults = useReplayStore((s) => s.assetResults);
  const combinedModifier = useReplayStore((s) => s.combinedModifier);
  const expandedStage = useReplayStore((s) => s.expandedStage);
  const status = useReplayStore((s) => s.status);

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
    <div data-testid="replay-page" className="w-full bg-[#0a0f0d] overflow-hidden flex flex-col flex-1 min-h-0 text-white font-mono">
      {/* Playback controls bar */}
      <div className="shrink-0">
        <ErrorBoundary name="PlaybackControls"><PlaybackControls /></ErrorBoundary>
      </div>

      {/* Main content: 3-column layout */}
      <div className="flex-1 min-h-0 grid grid-cols-[280px_1fr_280px]">
        {/* Left Column -- Config only */}
        <div className="h-full overflow-y-auto border-r border-solid border-[#1e293b]">
          <ErrorBoundary name="ReplayConfigPanel"><ReplayConfigPanel /></ErrorBoundary>
        </div>

        {/* Center Column -- Asset Cards + Simulated Position */}
        <div className="h-full flex flex-col overflow-hidden">
          <div className="shrink-0">
            <ErrorBoundary name="SimulatedPosition"><SimulatedPosition /></ErrorBoundary>
          </div>

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
                    <AssetCard asset={asset} data={assetResults[asset]} aimModifier={combinedModifier[asset]} />
                  </ErrorBoundary>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column -- Summary + What-If + History */}
        <div className="h-full overflow-y-auto border-l border-solid border-[#1e293b]">
          <ErrorBoundary name="BatchPnlReport"><BatchPnlReport /></ErrorBoundary>
          <ErrorBoundary name="ReplaySummary"><ReplaySummary /></ErrorBoundary>
          <ErrorBoundary name="WhatIfComparison"><WhatIfComparison /></ErrorBoundary>
          <ErrorBoundary name="ReplayHistory"><ReplayHistory /></ErrorBoundary>
        </div>
      </div>

      {/* Bottom Bar -- Pipeline Stepper + resizable detail panel */}
      <ResizableBottomPanel expandedStage={expandedStage} />
    </div>
  );
};

export default ReplayPage;

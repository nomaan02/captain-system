import { useEffect } from "react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
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

// Expose store on window in dev mode for Playwright E2E tests
if (import.meta.env.DEV) {
  window.__replayStore = useReplayStore;
}

const ResizeHandle = ({ orientation = "horizontal" }) => (
  <Separator
    className={`group relative flex items-center justify-center ${
      orientation === "horizontal"
        ? "w-[5px] cursor-col-resize"
        : "h-[5px] cursor-row-resize"
    }`}
  >
    <div
      className={`resize-handle-bar transition-colors duration-150 ${
        orientation === "horizontal"
          ? "w-[1px] h-full bg-[#1e293b]"
          : "h-[1px] w-full bg-[#1e293b]"
      }`}
    />
  </Separator>
);

const useMainLayout = () =>
  useDefaultLayout({ id: "captain-replay-main-layout" });

const useLeftLayout = () =>
  useDefaultLayout({ id: "captain-replay-left-layout" });

const useRightLayout = () =>
  useDefaultLayout({ id: "captain-replay-right-layout" });

const ReplayPage = () => {
  const assetOrder = useReplayStore((s) => s.assetOrder);
  const assetResults = useReplayStore((s) => s.assetResults);
  const expandedStage = useReplayStore((s) => s.expandedStage);
  const status = useReplayStore((s) => s.status);

  const { defaultLayout: mainLayout, onLayoutChanged: onMainChanged } = useMainLayout();
  const { defaultLayout: leftLayout, onLayoutChanged: onLeftChanged } = useLeftLayout();
  const { defaultLayout: rightLayout, onLayoutChanged: onRightChanged } = useRightLayout();

  // Load presets + history on mount
  useEffect(() => {
    api.replayPresets()
      .then((data) => {
        useReplayStore.getState().setPresets(data.presets || data || []);
      })
      .catch(() => {});

    api.replayHistory()
      .then((data) => {
        useReplayStore.getState().setHistory(data.history || data || []);
      })
      .catch(() => {});
  }, []);

  return (
    <div data-testid="replay-page" className="h-screen w-full bg-surface overflow-hidden flex flex-col">
      {/* TopBar */}
      <div className="shrink-0">
        <TopBar />
      </div>

      {/* Playback controls bar */}
      <div className="shrink-0">
        <PlaybackControls />
      </div>

      {/* Resizable 3-column layout */}
      <Group
        orientation="horizontal"
        defaultLayout={mainLayout}
        onLayoutChanged={onMainChanged}
        className="flex-1 min-h-0"
      >
        {/* Left Column -- Config + Pipeline */}
        <Panel id="replay-left" defaultSize={25} minSize={15}>
          <Group
            orientation="vertical"
            defaultLayout={leftLayout}
            onLayoutChanged={onLeftChanged}
            className="h-full"
          >
            {/* Config Panel */}
            <Panel id="replay-config" defaultSize={70} minSize={20}>
              <div className="h-full overflow-y-auto border-r border-[#1e293b]">
                <ReplayConfigPanel />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            {/* Pipeline Stepper */}
            <Panel id="replay-pipeline" defaultSize={30} minSize={10}>
              <div className="h-full overflow-y-auto border-r border-[#1e293b]">
                <PipelineStepper />
                {/* Block Detail expands below stepper */}
                {expandedStage && <BlockDetail blockId={expandedStage} />}
              </div>
            </Panel>
          </Group>
        </Panel>

        <ResizeHandle orientation="horizontal" />

        {/* Center Column -- Asset Cards + Simulated Position */}
        <Panel id="replay-center" defaultSize={50} minSize={20}>
          <div className="h-full flex flex-col">
            {/* Simulated position */}
            <div className="shrink-0">
              <SimulatedPosition />
            </div>

            {/* Asset cards grid */}
            <div className="flex-1 overflow-y-auto p-3">
              {assetOrder.length === 0 && status === "idle" && (
                <div className="flex flex-col items-center justify-center h-full text-center">
                  <div className="text-[12px] text-[#64748b] font-mono mb-2">Session Replay</div>
                  <div className="text-[10px] text-[#4a5568] font-mono max-w-[300px]">
                    Configure parameters on the left and click RUN REPLAY to simulate a historical trading session with custom risk parameters.
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
                    <AssetCard
                      key={asset}
                      asset={asset}
                      data={assetResults[asset]}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </Panel>

        <ResizeHandle orientation="horizontal" />

        {/* Right Column -- Summary + What-If + History */}
        <Panel id="replay-right" defaultSize={25} minSize={15}>
          <Group
            orientation="vertical"
            defaultLayout={rightLayout}
            onLayoutChanged={onRightChanged}
            className="h-full"
          >
            {/* Summary + What-If */}
            <Panel id="replay-summary" defaultSize={60} minSize={15}>
              <div className="h-full overflow-y-auto border-l border-[#1e293b]">
                <ReplaySummary />
                <WhatIfComparison />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            {/* History */}
            <Panel id="replay-history" defaultSize={40} minSize={10}>
              <div className="h-full overflow-y-auto border-l border-[#1e293b]">
                <ReplayHistory />
              </div>
            </Panel>
          </Group>
        </Panel>
      </Group>
    </div>
  );
};

export default ReplayPage;

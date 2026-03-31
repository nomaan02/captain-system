import { create } from "zustand";

const useReplayStore = create((set, get) => ({
  // State
  replayId: null,
  status: "idle", // idle | running | paused | complete
  speed: 50,
  progress: 0,
  currentAsset: null,

  // Config (sandboxed, never touches live)
  config: {
    date: new Date().toISOString().slice(0, 10),
    session: "NY",
    capital: 150000,
    budgetDivisor: 20,
    riskGoal: "PASS_EVAL",
    maxPositions: 5,
    maxContracts: 15,
    tpMultiple: 0.70,
    slMultiple: 0.35,
    cbEnabled: true,
    mddLimit: 4500,
    mllLimit: 2250,
  },
  presets: [],

  // Pipeline tracking
  pipelineStages: {}, // {B1: {status: "complete", summary: "10 assets"}, B2: {...}}
  expandedStage: null,

  // Per-asset results (populated as replay streams)
  assetResults: {}, // {ES: {orResult, sizingResult, status, error, ticks: []}}
  assetOrder: [],

  // Active simulation position
  activeSimPosition: null,

  // Summary
  summary: null,
  comparison: null, // what-if overlay
  replayHistory: [],

  // Actions
  setConfig: (updates) => set((s) => ({ config: { ...s.config, ...updates } })),
  setSpeed: (speed) => set({ speed }),
  setExpandedStage: (stage) => set((s) => ({ expandedStage: s.expandedStage === stage ? null : stage })),

  reset: () => set({
    replayId: null, status: "idle", progress: 0, currentAsset: null,
    pipelineStages: {}, assetResults: {}, assetOrder: [],
    activeSimPosition: null, summary: null, comparison: null,
    expandedStage: null,
  }),

  handleWsMessage: (data) => {
    const state = get();
    const msgType = data.type || data.event;
    switch (msgType) {
      case "replay_started":
        set({ replayId: data.replay_id, status: "running", progress: 0 });
        break;
      case "replay_tick": {
        const event = data.event;
        if (event === "config_loaded") {
          set({ pipelineStages: { ...state.pipelineStages, B1: { status: "complete", data: data.data } } });
        } else if (event === "auth_complete") {
          set({ pipelineStages: { ...state.pipelineStages, B1_AUTH: { status: "complete", data: data.data } } });
        } else if (event === "or_computed") {
          const asset = data.asset;
          set({
            currentAsset: asset,
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], orResult: data.data, status: "or_complete" },
            },
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
            pipelineStages: { ...state.pipelineStages, B2: { status: "complete", summary: "Regime neutral" } },
          });
        } else if (event === "regime_computed") {
          set({
            pipelineStages: { ...state.pipelineStages, B2: { status: "complete", data: data.data, summary: data.data?.summary || "Regime computed" } },
          });
        } else if (event === "aim_scored") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], aimResult: data.data, status: "aim_scored" },
            },
            pipelineStages: { ...state.pipelineStages, B3: { status: "complete", data: data.data } },
          });
        } else if (event === "breakout") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], breakout: data.data, status: "breakout" },
            },
            activeSimPosition: {
              asset_id: asset,
              direction: data.data.direction > 0 ? "LONG" : "SHORT",
              entry_price: data.data.entry_price,
              contracts: null,
              tp_level: data.data.tp_level,
              sl_level: data.data.sl_level,
            },
          });
        } else if (event === "exit") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], exitResult: data.data, status: "exited" },
            },
            activeSimPosition: null,
          });
        } else if (event === "sizing_complete") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], sizing: data.data, status: "sized" },
            },
            pipelineStages: { ...state.pipelineStages, B4: { status: "complete", data: data.data } },
          });
        } else if (event === "position_limit_applied") {
          set({
            pipelineStages: { ...state.pipelineStages, B5: { status: "complete", data: data.data } },
          });
        } else if (event === "compliance_check") {
          set({
            pipelineStages: { ...state.pipelineStages, B5C: { status: "complete", data: data.data } },
          });
        } else if (event === "signal_emitted") {
          set({
            pipelineStages: { ...state.pipelineStages, B6: { status: "complete", data: data.data } },
          });
        } else if (event === "asset_error") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], error: data.data?.error, status: "error" },
            },
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
          });
        } else if (event === "asset_blocked") {
          const asset = data.asset;
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], blocked: data.data?.reason, status: "blocked" },
            },
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
          });
        } else if (event === "progress") {
          set({ progress: data.data?.percent ?? state.progress });
        }
        break;
      }
      case "replay_complete":
        set({ status: "complete", summary: data.summary || data.data, progress: 100 });
        break;
      case "replay_error":
        set({ status: "complete", summary: { error: data.error || data.message } });
        break;
      case "replay_paused":
        set({ status: "paused" });
        break;
      case "replay_resumed":
        set({ status: "running", speed: data.speed || get().speed });
        break;
      default:
        break;
    }
  },

  setPresets: (presets) => set({ presets }),
  setHistory: (history) => set({ replayHistory: history }),
  setComparison: (comparison) => set({ comparison }),
}));

export default useReplayStore;

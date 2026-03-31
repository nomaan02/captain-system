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

    // Backend flattens event_data into the message via **event_data,
    // so fields like direction, asset, entry_price are at top level alongside
    // type, replay_id, event. Extract a payload object for convenience.
    const { type: _t, replay_id: _r, event: _e, ...payload } = data;

    switch (msgType) {
      case "replay_started":
        set({ replayId: data.replay_id, status: "running", progress: 0 });
        break;
      case "replay_tick": {
        const event = data.event;
        const asset = payload.asset;
        if (event === "config_loaded") {
          set({ pipelineStages: { ...state.pipelineStages, B1: { status: "complete", data: payload } } });
        } else if (event === "auth_complete") {
          set({ pipelineStages: { ...state.pipelineStages, B1_AUTH: { status: "complete", data: payload } } });
        } else if (event === "asset_bars_fetched") {
          // Add asset to order when bars arrive
          set({
            currentAsset: asset,
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], status: "loading", bar_count: payload.bar_count },
            },
          });
        } else if (event === "or_computed") {
          set({
            currentAsset: asset,
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], orResult: payload, status: "or_complete" },
            },
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
            pipelineStages: { ...state.pipelineStages, B2: { status: "complete", summary: "Regime neutral" } },
          });
        } else if (event === "breakout") {
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], breakout: payload, status: "breakout" },
            },
            activeSimPosition: {
              asset_id: asset,
              direction: payload.direction > 0 ? "LONG" : "SHORT",
              entry_price: payload.entry_price,
              contracts: null,
              tp_level: payload.tp_level,
              sl_level: payload.sl_level,
            },
          });
        } else if (event === "exit") {
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], exitResult: payload, status: "exited" },
            },
            activeSimPosition: null,
          });
        } else if (event === "sizing_complete") {
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], sizing: payload, status: "sized" },
            },
            pipelineStages: { ...state.pipelineStages, B4: { status: "complete", data: payload } },
          });
        } else if (event === "position_limit_applied") {
          set({
            pipelineStages: { ...state.pipelineStages, B5: { status: "complete", data: payload } },
          });
        } else if (event === "asset_error") {
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], error: payload.error, status: "error" },
            },
            assetOrder: state.assetOrder.includes(asset) ? state.assetOrder : [...state.assetOrder, asset],
          });
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

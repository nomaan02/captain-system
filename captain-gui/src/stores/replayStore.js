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
    mode: "single", // "single" | "period"
    date: new Date().toISOString().slice(0, 10),
    dateFrom: "",
    dateTo: "",
    sessions: ["NY", "LONDON", "APAC", "NY_PRE"],
    capital: 150000,
    budgetDivisor: 20,
    riskGoal: "PASS_EVAL",
    maxPositions: 5,
    maxContracts: 15,
    tpMultiple: 0.70,
    slMultiple: 0.35,
    cbEnabled: true,
    aimEnabled: false,
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
  aimBreakdown: {}, // {asset_id: {aim_id: {modifier, confidence, reason_tag, dma_weight}}}
  combinedModifier: {}, // {asset_id: float}
  aimDebug: {}, // {asset_id: {aim_id: {modifier, weight, tag}}}
  replayHistory: [],

  // Batch (period) replay state
  batchStatus: "idle", // idle | running | paused | complete
  batchDayResults: [], // [{date, trades, wins, losses, pnl, cumulativePnl}]
  batchSummary: null,
  batchCurrentDay: null,
  batchTotalDays: 0,
  batchCompletedDays: 0,
  batchProgress: 0,

  // Actions
  setConfig: (updates) => set((s) => ({ config: { ...s.config, ...updates } })),
  setSpeed: (speed) => set({ speed }),
  setExpandedStage: (stage) => set((s) => ({ expandedStage: s.expandedStage === stage ? null : stage })),

  reset: () => set({
    replayId: null, status: "idle", progress: 0, currentAsset: null,
    pipelineStages: {}, assetResults: {}, assetOrder: [],
    activeSimPosition: null, summary: null, comparison: null,
    aimBreakdown: {}, combinedModifier: {}, aimDebug: {},
    expandedStage: null,
    batchStatus: "idle", batchDayResults: [], batchSummary: null,
    batchCurrentDay: null, batchTotalDays: 0, batchCompletedDays: 0,
    batchProgress: 0,
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
          const stages = { ...state.pipelineStages, B4: { status: "complete", data: payload } };
          if (payload.cb_enabled !== undefined) {
            stages.B5C = {
              status: "complete",
              data: {
                cb_enabled: payload.cb_enabled,
                cb_blocked: payload.cb_blocked,
                cb_l1_halt: payload.cb_l1_halt,
                cb_rho_j: payload.cb_rho_j,
                cb_l1_l_t: payload.cb_l1_l_t,
                cb_l2_blocked: payload.cb_l2_blocked,
                cb_l2_N: payload.cb_l2_N,
                cb_l2_n_t: payload.cb_l2_n_t,
                cb_l3_blocked: payload.cb_l3_blocked,
                cb_l3_mu_b: payload.cb_l3_mu_b,
                cb_l0_blocked: payload.cb_l0_blocked,
                cb_l4_blocked: payload.cb_l4_blocked,
              },
            };
          }
          set({
            assetResults: {
              ...state.assetResults,
              [asset]: { ...state.assetResults[asset], sizing: payload, status: "sized" },
            },
            pipelineStages: stages,
            activeSimPosition: state.activeSimPosition?.asset_id === asset
              ? { ...state.activeSimPosition, contracts: payload.contracts ?? payload.final ?? null }
              : state.activeSimPosition,
          });
        } else if (event === "aim_scored") {
          set({
            aimBreakdown: payload.aim_breakdown || {},
            combinedModifier: payload.combined_modifier || {},
            aimDebug: payload.aim_debug || {},
            pipelineStages: { ...state.pipelineStages, B3: { status: "complete", data: payload } },
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
        } else if (event === "replay_complete") {
          // replay_complete arrives as type:"replay_tick" event:"replay_complete"
          set({
            status: "complete",
            summary: payload.summary || payload,
            progress: 100,
            pipelineStages: { ...state.pipelineStages, B6: { status: "complete", summary: "Done" } },
          });
        } else if (event === "error") {
          set({ status: "complete", summary: { error: payload.error || "Unknown error" } });
        }
        break;
      }
      case "replay_complete":
        // Fallback for direct type:"replay_complete" messages
        set({ status: "complete", summary: payload.summary || payload, progress: 100 });
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

      // Batch (period) replay events
      case "batch_started":
        set({
          replayId: data.replay_id,
          status: "running",
          batchStatus: "running",
          batchTotalDays: data.total_days,
          batchCompletedDays: 0,
          batchDayResults: [],
          batchSummary: null,
          batchCurrentDay: null,
          batchProgress: 0,
        });
        break;
      case "batch_day_started":
        set({
          batchCurrentDay: data.date,
          assetResults: {},
          assetOrder: [],
          currentAsset: null,
          pipelineStages: {},
          activeSimPosition: null,
          summary: null,
        });
        break;
      case "batch_day_completed":
        set((s) => ({
          batchCompletedDays: data.day_index + 1,
          batchProgress: Math.round(((data.day_index + 1) / data.total_days) * 100),
          batchDayResults: [...s.batchDayResults, {
            date: data.date,
            trades: data.day_trades,
            wins: data.day_wins,
            losses: data.day_losses,
            pnl: data.day_pnl,
            cumulativePnl: data.cumulative_pnl,
          }],
        }));
        break;
      case "batch_complete":
        set({
          status: "complete",
          batchStatus: "complete",
          batchSummary: data.summary,
          batchProgress: 100,
        });
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

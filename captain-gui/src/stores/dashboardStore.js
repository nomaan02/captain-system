import { create } from "zustand";
import api from "../api/client";

// Direction normalization: backend sends 1/-1 integers, frontend needs "LONG"/"SHORT" strings
const normalizeDirection = (dir) => {
  if (typeof dir === "string") return dir;
  return dir > 0 ? "LONG" : dir < 0 ? "SHORT" : "NEUTRAL";
};

const normalizePositions = (positions) =>
  positions.map((p) => ({ ...p, direction: normalizeDirection(p.direction) }));

const normalizeSignals = (signals) =>
  signals.map((s) => ({ ...s, direction: normalizeDirection(s.direction) }));

const useDashboardStore = create((set, get) => ({
  // Connection state
  connected: false,
  timestamp: null,

  // New Phase 3 fields
  pipelineStage: "WAITING", // "WAITING" | "OR_FORMING" | "SIGNAL_GEN" | "EXECUTED"
  autoExecute: false,
  orStatus: null, // { or_high, or_low, or_state, or_direction, session }

  // Account selection
  selectedAccount: "PRAC-V2-551001-43861321",
  accounts: [
    { id: "PRAC-V2-551001-43861321", label: "Practice 150K", type: "practice" },
    { id: "150KTC-V2-551001-19064435", label: "Live Prop 150K", type: "live" },
  ],

  // Dashboard data
  capitalSilo: null,
  dailyTradeStats: null,
  openPositions: [],
  pendingSignals: [],
  aimStates: [],
  tsmStatus: [],
  decayAlerts: [],
  warmupGauges: [],
  regimePanel: null,
  payoutPanel: [],
  scalingDisplay: [],
  liveMarket: null,
  apiStatus: null,
  lastAck: null,

  // Actions
  setConnected: (connected) => set({ connected }),

  setSnapshot: (snapshot) => {
    const state = get();
    set({
      timestamp: snapshot.timestamp ?? state.timestamp,
      capitalSilo: snapshot.capital_silo ?? state.capitalSilo,
      dailyTradeStats: snapshot.daily_trade_stats ?? state.dailyTradeStats,
      openPositions: snapshot.open_positions
        ? normalizePositions(snapshot.open_positions)
        : state.openPositions,
      pendingSignals: snapshot.pending_signals
        ? normalizeSignals(snapshot.pending_signals)
        : state.pendingSignals,
      aimStates: snapshot.aim_states ?? state.aimStates,
      tsmStatus: snapshot.tsm_status ?? state.tsmStatus,
      decayAlerts: snapshot.decay_alerts ?? state.decayAlerts,
      warmupGauges: snapshot.warmup_gauges ?? state.warmupGauges,
      regimePanel: snapshot.regime_panel ?? state.regimePanel,
      payoutPanel: snapshot.payout_panel ?? state.payoutPanel,
      scalingDisplay: snapshot.scaling_display ?? state.scalingDisplay,
      // Preserve newer liveMarket if snapshot's is stale
      liveMarket: snapshot.live_market ?? state.liveMarket,
      apiStatus: snapshot.api_status ?? state.apiStatus,
      pipelineStage: snapshot.pipeline_stage ?? state.pipelineStage,
      autoExecute: snapshot.auto_execute ?? state.autoExecute,
      orStatus: snapshot.or_status ?? state.orStatus,
    });
  },

  setLiveMarket: (lm) => {
    const current = get().liveMarket;
    // Incremental merge — only non-null fields overwrite
    if (!current) {
      set({ liveMarket: lm });
    } else {
      const merged = { ...current };
      for (const [key, val] of Object.entries(lm)) {
        if (val != null) merged[key] = val;
      }
      set({ liveMarket: merged });
    }
  },

  addSignal: (signal) => {
    const normalized = { ...signal, direction: normalizeDirection(signal.direction) };
    set((state) => ({
      pendingSignals: [normalized, ...state.pendingSignals],
    }));
  },

  removeSignal: (signalId) =>
    set((state) => ({
      pendingSignals: state.pendingSignals.filter((s) => s.signal_id !== signalId),
    })),

  setCommandAck: (ack) => set({ lastAck: ack }),

  setPipelineStage: (stage) => set({ pipelineStage: stage }),
  setAutoExecute: (enabled) => set({ autoExecute: enabled }),
  setOrStatus: (orStatus) => set({ orStatus }),
  setSelectedAccount: (id) => {
    set({ selectedAccount: id });
    // Persist to backend .env — fire and forget
    api.setAccount(id).catch((err) => {
      console.warn("Failed to persist account selection:", err);
    });
  },
}));

export default useDashboardStore;

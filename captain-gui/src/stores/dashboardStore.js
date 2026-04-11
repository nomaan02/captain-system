import { create } from "zustand";
import api from "../api/client";

// Direction normalization: backend sends 1/-1 integers, "BUY"/"SELL" strings, or null
const DIRECTION_MAP = { BUY: "LONG", SELL: "SHORT", LONG: "LONG", SHORT: "SHORT" };
const normalizeDirection = (dir) => {
  if (dir == null) return "UNKNOWN";
  if (typeof dir === "string") return DIRECTION_MAP[dir.toUpperCase()] || "UNKNOWN";
  return dir > 0 ? "LONG" : dir < 0 ? "SHORT" : "UNKNOWN";
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

  // Account selection — loaded dynamically from GET /api/accounts
  selectedAccount: "",
  accounts: [],

  // Service health (populated from dashboard snapshot if backend sends it)
  serviceHealth: { questdb: "unknown", redis: "unknown" },

  // Dashboard data
  capitalSilo: null,
  dailyTradeStats: null,
  openPositions: [],
  closedTrades: [],
  pendingSignals: [],
  signalHistory: JSON.parse(localStorage.getItem("captain:signalHistory") || "[]"),
  aimStates: [],
  tsmStatus: [],
  decayAlerts: [],
  warmupGauges: [],
  regimePanel: null,
  payoutPanel: [],
  scalingDisplay: [],
  liveMarket: {},
  apiStatus: null,
  lastAck: null,
  selectedSignalId: null,

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
      closedTrades: snapshot.closed_trades ?? snapshot.trade_history ?? state.closedTrades,
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
      // Merge live_market assets from snapshot
      liveMarket: snapshot.live_market
        ? { ...state.liveMarket, ...snapshot.live_market }
        : state.liveMarket,
      apiStatus: snapshot.api_status ?? state.apiStatus,
      pipelineStage: snapshot.pipeline_stage ?? state.pipelineStage,
      autoExecute: snapshot.auto_execute ?? state.autoExecute,
      orStatus: snapshot.or_status ?? state.orStatus,
      serviceHealth: snapshot.service_health ?? state.serviceHealth,
    });
  },

  setLiveMarket: (lm) => {
    // lm.assets is a dict keyed by symbol: { ES: {...}, MES: {...} }
    const assets = lm.assets || lm;
    const current = get().liveMarket || {};
    const merged = { ...current };
    for (const [symbol, data] of Object.entries(assets)) {
      if (data != null) merged[symbol] = data;
    }
    set({ liveMarket: merged });
  },

  addSignal: (signal) => {
    const normalized = { ...signal, direction: normalizeDirection(signal.direction) };
    set((state) => ({
      pendingSignals: [normalized, ...state.pendingSignals],
    }));
  },

  setSelectedSignalId: (id) =>
    set((state) => ({ selectedSignalId: state.selectedSignalId === id ? null : id })),

  removeSignal: (signalId) =>
    set((state) => ({
      pendingSignals: state.pendingSignals.filter((s) => s.signal_id !== signalId),
      ...(state.selectedSignalId === signalId ? { selectedSignalId: null } : {}),
    })),

  clearSignals: () => {
    const { pendingSignals, signalHistory } = get();
    if (pendingSignals.length === 0) return;
    const signalIds = pendingSignals.map((s) => s.signal_id).filter(Boolean);
    const cleared_at = new Date().toISOString();
    const archived = pendingSignals.map((s) => ({ ...s, cleared_at }));
    const updated = [...archived, ...signalHistory].slice(0, 500);
    localStorage.setItem("captain:signalHistory", JSON.stringify(updated));
    set({ pendingSignals: [], signalHistory: updated, selectedSignalId: null });
    // Tell backend so they don't return on refresh
    if (signalIds.length > 0) {
      api.clearSignals("primary_user", signalIds).catch((err) => {
        console.warn("Failed to clear signals on backend:", err);
      });
    }
  },

  setClosedTrades: (trades) => set({ closedTrades: normalizePositions(trades) }),

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
  fetchAccounts: async () => {
    try {
      const data = await api.accounts();
      const list = data.accounts || [];
      set({ accounts: list });
      // Auto-select first account if none selected yet
      if (!get().selectedAccount && list.length > 0) {
        set({ selectedAccount: list[0].id });
      }
    } catch (err) {
      console.warn("Failed to fetch accounts:", err);
    }
  },
}));

export default useDashboardStore;

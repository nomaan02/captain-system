import { create } from "zustand";
import type {
  DashboardSnapshot,
  OpenPosition,
  PendingSignal,
  AimState,
  TsmStatus,
  DecayAlert,
  WarmupGauge,
  PayoutEntry,
  ScalingEntry,
  CapitalSilo,
  LiveMarket,
  ApiStatus,
  WsCommandAck,
  WsSignalMessage,
} from "@/api/types";

interface DashboardState {
  connected: boolean;
  timestamp: string | null;
  capitalSilo: CapitalSilo | null;
  openPositions: OpenPosition[];
  pendingSignals: PendingSignal[];
  aimStates: AimState[];
  tsmStatus: TsmStatus[];
  decayAlerts: DecayAlert[];
  warmupGauges: WarmupGauge[];
  payoutPanel: PayoutEntry[];
  scalingDisplay: ScalingEntry[];
  liveMarket: LiveMarket | null;
  apiStatus: ApiStatus | null;
  lastAck: WsCommandAck | null;

  setConnected: (c: boolean) => void;
  setSnapshot: (s: DashboardSnapshot) => void;
  setLiveMarket: (lm: LiveMarket) => void;
  addSignal: (sig: WsSignalMessage["signal"]) => void;
  setCommandAck: (ack: WsCommandAck) => void;
  removeSignal: (signalId: string) => void;
}

export const useDashboardStore = create<DashboardState>()((set) => ({
  connected: false,
  timestamp: null,
  capitalSilo: null,
  openPositions: [],
  pendingSignals: [],
  aimStates: [],
  tsmStatus: [],
  decayAlerts: [],
  warmupGauges: [],
  payoutPanel: [],
  scalingDisplay: [],
  liveMarket: null,
  apiStatus: null,
  lastAck: null,

  setConnected: (connected) => set({ connected }),

  setLiveMarket: (lm) =>
    set((state) => {
      if (!state.liveMarket) return { liveMarket: lm };
      // Merge: only overwrite with non-null values from the update
      const merged = { ...state.liveMarket };
      for (const [k, v] of Object.entries(lm)) {
        if (v != null) (merged as any)[k] = v;
      }
      return { liveMarket: merged };
    }),

  setSnapshot: (s) =>
    set((state) => {
      // Merge live_market from snapshot instead of replacing — the 1Hz
      // live_market channel is more authoritative than the 60s dashboard.
      // Only use snapshot's live_market on first load (state.liveMarket null).
      let liveMarket = state.liveMarket;
      if (s.live_market) {
        if (!liveMarket) {
          liveMarket = s.live_market;
        } else {
          liveMarket = { ...liveMarket };
          for (const [k, v] of Object.entries(s.live_market)) {
            if (v != null) (liveMarket as any)[k] = v;
          }
        }
      }
      return {
        timestamp: s.timestamp,
        capitalSilo: s.capital_silo,
        openPositions: s.open_positions,
        pendingSignals: s.pending_signals,
        aimStates: s.aim_states,
        tsmStatus: s.tsm_status,
        decayAlerts: s.decay_alerts,
        warmupGauges: s.warmup_gauges,
        payoutPanel: s.payout_panel,
        scalingDisplay: s.scaling_display,
        liveMarket,
        apiStatus: s.api_status,
      };
    }),

  addSignal: (sig) =>
    set((state) => ({
      pendingSignals: [
        {
          signal_id: sig.signal_id,
          asset: sig.asset,
          timestamp: sig.timestamp,
          direction: sig.direction,
          confidence_tier: sig.confidence_tier,
          quality_score: sig.quality_score,
        },
        ...state.pendingSignals,
      ],
    })),

  setCommandAck: (ack) => set({ lastAck: ack }),

  removeSignal: (signalId) =>
    set((state) => ({
      pendingSignals: state.pendingSignals.filter(
        (s) => s.signal_id !== signalId,
      ),
    })),
}));

import { useEffect, useState } from "react";
import { Group, Panel, Separator, useDefaultLayout } from "react-resizable-panels";
import MarketTicker from "../components/layout/MarketTicker";
import RiskPanel from "../components/risk/RiskPanel";
import AimRegistryPanel from "../components/aim/AimRegistryPanel";
import LiveTerminal from "../components/terminal/LiveTerminal";
import ChartPanel from "../components/chart/ChartPanel";
import ActivePosition from "../components/trading/ActivePosition";
import SignalExecutionBar from "../components/signals/SignalExecutionBar";
import SignalCards from "../components/signals/SignalCards";
import TradeLog from "../components/trading/TradeLog";
import SystemLog from "../components/system/SystemLog";
import useWebSocket from "../ws/useWebSocket";
import useDashboardStore from "../stores/dashboardStore";
import useNotificationStore from "../stores/notificationStore";
import useTerminalStore from "../stores/terminalStore";
import api from "../api/client";

// Expose store on window in dev mode for Playwright E2E tests
if (import.meta.env.DEV) {
  window.__dashboardStore = useDashboardStore;
}

// ── DEV MOCK DATA (2026-03-30 NY session replay) ──────────────────────
// Remove this block once live backend data is confirmed working.
const DEV_MOCK_ENABLED = import.meta.env.VITE_DEV_MOCK === 'true';

const MOCK_SIGNALS = [
  { signal_id: "SIG-MES-20260330", asset: "MES", direction: "SHORT", strategy_name: "ORB v1.3", entry_price: 6455.00, tp_level: 6443.80, sl_level: 6460.60, quality_score: 0.82, confidence_tier: "HIGH", pnl: 616.00, timestamp: "2026-03-30T09:35:00" },
  { signal_id: "SIG-ES-20260330", asset: "ES", direction: "SHORT", strategy_name: "ORB v1.3", entry_price: 6454.75, tp_level: 6443.20, sl_level: 6460.53, quality_score: 0.78, confidence_tier: "HIGH", pnl: 577.50, timestamp: "2026-03-30T09:35:00" },
  { signal_id: "SIG-MNQ-20260330", asset: "MNQ", direction: "SHORT", strategy_name: "ORB v1.3", entry_price: 23457.00, tp_level: 23400.30, sl_level: 23485.35, quality_score: 0.75, confidence_tier: "MEDIUM", pnl: 567.00, timestamp: "2026-03-30T09:35:00" },
  { signal_id: "SIG-M2K-20260330", asset: "M2K", direction: "SHORT", strategy_name: "ORB v1.3", entry_price: 2474.50, tp_level: 2466.45, sl_level: 2478.53, quality_score: 0.71, confidence_tier: "MEDIUM", pnl: 362.25, timestamp: "2026-03-30T09:35:00" },
  { signal_id: "SIG-MYM-20260330", asset: "MYM", direction: "SHORT", strategy_name: "ORB v1.3", entry_price: 45756.00, tp_level: 45675.50, sl_level: 45796.25, quality_score: 0.68, confidence_tier: "MEDIUM", pnl: 161.00, timestamp: "2026-03-30T09:35:01" },
];

const MOCK_NOTIFICATIONS = [
  { notif_id: "n-001", priority: "LOW", message: "Session NY (1) opening — beginning evaluation", timestamp: "2026-03-30T09:28:00", source: "orchestrator" },
  { notif_id: "n-002", priority: "LOW", message: "ON-B1: 9 assets eligible, 124 features computed", timestamp: "2026-03-30T09:28:06", source: "online" },
  { notif_id: "n-003", priority: "LOW", message: "ON-B4: Kelly sizing for user primary_user (1 accounts, 9 assets)", timestamp: "2026-03-30T09:28:06", source: "online" },
  { notif_id: "n-004", priority: "LOW", message: "ON-B5: Trade selection: 5/9 assets selected", timestamp: "2026-03-30T09:28:06", source: "online" },
  { notif_id: "n-005", priority: "LOW", message: "Phase A complete — 9 assets registered for OR tracking", timestamp: "2026-03-30T09:28:06", source: "online" },
  { notif_id: "n-006", priority: "LOW", message: "OR FORMING: ES (6467.75), MES (6467.75), NQ (23509.75), MNQ (23509.75)", timestamp: "2026-03-30T09:30:00", source: "or_tracker" },
  { notif_id: "n-007", priority: "LOW", message: "OR COMPLETE: all 6 NY assets", timestamp: "2026-03-30T09:35:00", source: "or_tracker" },
  { notif_id: "n-008", priority: "MEDIUM", message: "BREAKOUT SHORT: M2K, MES, NQ, ES, MNQ, MYM (all within 5 seconds)", timestamp: "2026-03-30T09:35:00", source: "or_tracker" },
  { notif_id: "n-009", priority: "LOW", message: "Signal generated: MES SHORT @ 6455.00 conf=0.82 (11 contracts)", timestamp: "2026-03-30T09:35:00", source: "signal" },
  { notif_id: "n-010", priority: "LOW", message: "Signal generated: ES SHORT @ 6454.75 conf=0.78 (1 contract)", timestamp: "2026-03-30T09:35:00", source: "signal" },
  { notif_id: "n-011", priority: "LOW", message: "Signal generated: MNQ SHORT @ 23457.00 conf=0.75 (5 contracts)", timestamp: "2026-03-30T09:35:00", source: "signal" },
  { notif_id: "n-012", priority: "LOW", message: "Signal generated: M2K SHORT @ 2474.50 conf=0.71 (9 contracts)", timestamp: "2026-03-30T09:35:00", source: "signal" },
  { notif_id: "n-013", priority: "LOW", message: "Signal generated: MYM SHORT @ 45756.00 conf=0.68 (4 contracts)", timestamp: "2026-03-30T09:35:01", source: "signal" },
  { notif_id: "n-014", priority: "HIGH", message: "Direction-format bug: -1 integer vs \"SELL\" string — orders NOT placed", timestamp: "2026-03-30T09:35:02", source: "system" },
  { notif_id: "n-015", priority: "MEDIUM", message: "NQ blocked by risk gate: risk/contract $293.92 > daily budget $225", timestamp: "2026-03-30T09:35:00", source: "risk" },
  { notif_id: "n-016", priority: "MEDIUM", message: "NKD blocked by risk gate: risk/contract $510.79 > daily budget $225", timestamp: "2026-03-30T09:35:00", source: "risk" },
  { notif_id: "n-017", priority: "LOW", message: "TP HIT: MES @ 6443.80 (+$616.00) — 5 min duration", timestamp: "2026-03-30T09:40:00", source: "signal" },
  { notif_id: "n-018", priority: "LOW", message: "TP HIT: ES @ 6443.20 (+$577.50) — 5 min duration", timestamp: "2026-03-30T09:40:00", source: "signal" },
  { notif_id: "n-019", priority: "LOW", message: "TP HIT: MNQ @ 23400.30 (+$567.00) — 5 min duration", timestamp: "2026-03-30T09:40:00", source: "signal" },
  { notif_id: "n-020", priority: "LOW", message: "TP HIT: M2K @ 2466.45 (+$362.25) — 5 min duration", timestamp: "2026-03-30T09:40:00", source: "signal" },
  { notif_id: "n-021", priority: "LOW", message: "TP HIT: MYM @ 45675.50 (+$161.00) — 6 min duration", timestamp: "2026-03-30T09:41:00", source: "signal" },
  { notif_id: "n-022", priority: "LOW", message: "Session complete: 5/5 TP HIT, +$2,283.75 (simulated)", timestamp: "2026-03-30T09:42:00", source: "orchestrator" },
  // ── test entries: ensure each filter category has clear hits ──
  { notif_id: "t-err-1", priority: "CRITICAL", message: "WebSocket connection lost — reconnecting in 5s", timestamp: "2026-03-30T09:43:00", source: "system" },
  { notif_id: "t-err-2", priority: "HIGH", message: "Order rejected by brokerage: insufficient margin", timestamp: "2026-03-30T09:43:05", source: "system" },
  { notif_id: "t-err-3", priority: "MEDIUM", message: "MGC blocked by circuit breaker layer-2", timestamp: "2026-03-30T09:43:10", source: "risk" },
  { notif_id: "t-sig-1", priority: "LOW", message: "Signal generated: ZN LONG @ 108.25 conf=0.88 (3 contracts)", timestamp: "2026-03-30T09:44:00", source: "signal" },
  { notif_id: "t-sig-2", priority: "LOW", message: "OR FORMING: MGC (2341.50), ZB (118.75)", timestamp: "2026-03-30T09:44:05", source: "or_tracker" },
  { notif_id: "t-sig-3", priority: "MEDIUM", message: "BREAKOUT LONG: ZN, ZB (within 2 seconds)", timestamp: "2026-03-30T09:44:10", source: "or_tracker" },
  { notif_id: "t-ord-1", priority: "LOW", message: "SL HIT: ZN @ 107.90 (-$105.00) — 12 min duration", timestamp: "2026-03-30T09:45:00", source: "signal" },
  { notif_id: "t-ord-2", priority: "LOW", message: "Bracket order filled: ES LONG 2 @ 6470.25", timestamp: "2026-03-30T09:45:05", source: "system" },
  { notif_id: "t-ord-3", priority: "LOW", message: "TP HIT: ZB @ 119.40 (+$203.13) — 8 min duration", timestamp: "2026-03-30T09:45:10", source: "signal" },
];

const MOCK_TERMINAL_ENTRIES = [
  { process: "COMMAND", level: "INFO",  source: "main",         message: "QuestDB connection verified",                                     timestamp: "2026-03-30T09:24:55" },
  { process: "COMMAND", level: "INFO",  source: "main",         message: "Redis connection verified (v7.2.4)",                               timestamp: "2026-03-30T09:24:55" },
  { process: "COMMAND", level: "INFO",  source: "main",         message: "TSM files loaded \u2014 1 account state(s)",                       timestamp: "2026-03-30T09:24:56" },
  { process: "COMMAND", level: "INFO",  source: "telegram",     message: "Telegram bot started (@CaptainSystemBot)",                         timestamp: "2026-03-30T09:24:57" },
  { process: "COMMAND", level: "INFO",  source: "topstep",      message: "TopstepX auth success \u2014 token expires 2026-03-30T10:24:58",   timestamp: "2026-03-30T09:24:58" },
  { process: "COMMAND", level: "INFO",  source: "topstep",      message: "Account resolved: PRAC-V2-551001-43861321 ($150,000.00)",          timestamp: "2026-03-30T09:24:58" },
  { process: "COMMAND", level: "INFO",  source: "topstep",      message: "Contracts preloaded: 10 assets mapped",                            timestamp: "2026-03-30T09:24:59" },
  { process: "COMMAND", level: "INFO",  source: "stream",       message: "MarketStream connected \u2014 10 contracts subscribed",             timestamp: "2026-03-30T09:25:00" },
  { process: "COMMAND", level: "INFO",  source: "stream",       message: "UserStream connected \u2014 account 20319811",                     timestamp: "2026-03-30T09:25:01" },
  { process: "COMMAND", level: "INFO",  source: "orchestrator", message: "Command orchestrator started (scheduler + signal reader)",          timestamp: "2026-03-30T09:25:02" },
  { process: "COMMAND", level: "INFO",  source: "api",          message: "FastAPI server listening on 0.0.0.0:8000",                         timestamp: "2026-03-30T09:25:03" },
  { process: "OFFLINE", level: "INFO",  source: "main",         message: "QuestDB + Redis verified",                                        timestamp: "2026-03-30T09:25:10" },
  { process: "OFFLINE", level: "INFO",  source: "main",         message: "AIM states seeded \u2014 270 rows (16 AIMs x 10 assets)",          timestamp: "2026-03-30T09:25:11" },
  { process: "OFFLINE", level: "INFO",  source: "orchestrator", message: "Offline orchestrator started \u2014 listening for trade outcomes",  timestamp: "2026-03-30T09:25:12" },
  { process: "ONLINE",  level: "INFO",  source: "main",         message: "QuestDB + Redis verified",                                        timestamp: "2026-03-30T09:25:15" },
  { process: "ONLINE",  level: "INFO",  source: "main",         message: "MarketStream started \u2014 10 contracts",                         timestamp: "2026-03-30T09:25:16" },
  { process: "ONLINE",  level: "INFO",  source: "orchestrator", message: "Online orchestrator started \u2014 next session: NY(1) at 09:28",  timestamp: "2026-03-30T09:25:17" },
  { process: "COMMAND", level: "INFO",  source: "scheduler",    message: "Health check: ONLINE=ok, OFFLINE=ok, COMMAND=ok",                  timestamp: "2026-03-30T09:25:30" },
  { process: "ONLINE",  level: "INFO",  source: "orchestrator", message: "Session NY(1) opening \u2014 beginning evaluation",                timestamp: "2026-03-30T09:28:00" },
  { process: "ONLINE",  level: "INFO",  source: "b1_data",      message: "B1: Data ingestion \u2014 10 assets, 124 features",                timestamp: "2026-03-30T09:28:02" },
  { process: "ONLINE",  level: "INFO",  source: "b2_regime",    message: "B2: Regime probability \u2014 10 assets classified",               timestamp: "2026-03-30T09:28:03" },
  { process: "ONLINE",  level: "INFO",  source: "b3_aim",       message: "B3: AIM aggregation \u2014 10 assets scored",                      timestamp: "2026-03-30T09:28:04" },
  { process: "ONLINE",  level: "INFO",  source: "b4_kelly",     message: "B4: Kelly sizing for primary_user (1 account, 9 eligible)",        timestamp: "2026-03-30T09:28:05" },
  { process: "ONLINE",  level: "INFO",  source: "b5_select",    message: "B5: Trade selection \u2014 5/9 assets selected",                   timestamp: "2026-03-30T09:28:06" },
  { process: "ONLINE",  level: "INFO",  source: "orchestrator", message: "Phase A complete \u2014 5 assets registered for OR tracking",      timestamp: "2026-03-30T09:28:06" },
  { process: "ONLINE",  level: "INFO",  source: "or_tracker",   message: "OR FORMING: ES (6467.75), MES (6467.75), NQ (23509.75)",           timestamp: "2026-03-30T09:30:00" },
  { process: "ONLINE",  level: "INFO",  source: "or_tracker",   message: "OR COMPLETE: 5/5 NY assets (m-values satisfied)",                  timestamp: "2026-03-30T09:35:00" },
  { process: "ONLINE",  level: "WARN",  source: "or_tracker",   message: "BREAKOUT SHORT: MES, ES, MNQ, M2K, MYM (within 5s cluster)",      timestamp: "2026-03-30T09:35:01" },
  { process: "ONLINE",  level: "INFO",  source: "b6_signal",    message: "B6: Signal \u2014 MES SHORT @ 6455.00 (11 cts, conf=0.82)",        timestamp: "2026-03-30T09:35:01" },
  { process: "ONLINE",  level: "INFO",  source: "b6_signal",    message: "B6: Signal \u2014 ES SHORT @ 6454.75 (1 ct, conf=0.78)",           timestamp: "2026-03-30T09:35:01" },
  { process: "COMMAND", level: "INFO",  source: "b1_routing",   message: "Signal batch received \u2014 5 signals for primary_user",          timestamp: "2026-03-30T09:35:02" },
  { process: "COMMAND", level: "INFO",  source: "b3_api",       message: "Bracket order: MES SHORT 11 @ MKT, TP=6443.80, SL=6460.60",       timestamp: "2026-03-30T09:35:02" },
  { process: "COMMAND", level: "ERROR", source: "b3_api",       message: "Direction format error: expected string 'SELL', got integer -1",    timestamp: "2026-03-30T09:35:03" },
  { process: "COMMAND", level: "INFO",  source: "topstep",      message: "Auth token auto-refresh \u2014 new expiry 10:35:03",               timestamp: "2026-03-30T09:35:03" },
  { process: "ONLINE",  level: "INFO",  source: "b7_monitor",   message: "B7: Monitoring 5 positions \u2014 next check in 5s",               timestamp: "2026-03-30T09:35:05" },
  { process: "ONLINE",  level: "INFO",  source: "b7_monitor",   message: "TP HIT: MES @ 6443.80 (+$616.00) \u2014 5 min",                   timestamp: "2026-03-30T09:40:00" },
  { process: "OFFLINE", level: "INFO",  source: "orchestrator", message: "Trade outcome received: MES +$616.00 (regime=TREND)",              timestamp: "2026-03-30T09:40:01" },
  { process: "OFFLINE", level: "INFO",  source: "b1_dma",       message: "B1: DMA meta-weight update \u2014 MES (6 AIMs adjusted)",          timestamp: "2026-03-30T09:40:02" },
  { process: "OFFLINE", level: "INFO",  source: "b2_bocpd",     message: "B2: BOCPD \u2014 no changepoint detected (run_length=47)",         timestamp: "2026-03-30T09:40:02" },
  { process: "OFFLINE", level: "INFO",  source: "b8_kelly",     message: "B8: Kelly update \u2014 MES f*=0.0347 (shrunk: 0.0174)",           timestamp: "2026-03-30T09:40:03" },
];

function injectMockData() {
  const store = useDashboardStore.getState();
  const mockAccount = store.selectedAccount || "LOADING...";
  store.setSnapshot({
    timestamp: "2026-03-30T09:42:00",
    capital_silo: {
      total_capital: 150000,
      daily_pnl: 0,        // No real trades — signals only
      cumulative_pnl: 0,
      status: "LIVE",
    },
    open_positions: [],     // No trades executed (direction bug blocked them)
    pending_signals: MOCK_SIGNALS,
    tsm_status: [
      {
        account_id: 0,
        account_name: mockAccount,
        current_balance: 150000,
        starting_balance: 150000,
        mdd_used_pct: 0,
        mdd_limit: 4500,
        daily_dd_used_pct: 0,
        daily_dd_limit: 2250,
        profit_target: 4500,
        max_lots: 15,
        trading_state: "ACTIVE",
      },
    ],
    live_market: {
      contract_id: "MES",
      last_price: 6384.50,
      best_bid: 6384.25,
      best_ask: 6384.50,
      spread: 0.25,
      change: -70.50,
      change_pct: -1.09,
      open: 6455.00,
      high: 6471.00,
      low: 6378.25,
      volume: 1842367,
      timestamp: "2026-03-30T13:42:00",
    },
    api_status: {
      api_authenticated: true,
      market_stream: true,
      user_stream: true,
      account_name: mockAccount,
    },
    or_status: {
      or_high: 6471.00,
      or_low: 6455.00,
      or_state: "BREAKOUT SHORT",
    },
    pipeline_stage: "EXECUTED",
    daily_trade_stats: {
      trades_today: 5,
      wins: 5,
      losses: 0,
      win_pct: 100.0,
      profit_factor: null,  // No losses, PF undefined
      avg_win: 456.75,
      avg_loss: null,
      total_pnl: 2283.75,  // Simulated — not realised
    },
  });

  // Inject notifications
  const notifStore = useNotificationStore.getState();
  MOCK_NOTIFICATIONS.forEach((n) => notifStore.addNotification(n));

  // Inject terminal log entries
  const termStore = useTerminalStore.getState();
  MOCK_TERMINAL_ENTRIES.forEach((e) => termStore.addEntry(e));

  // Set pipeline to EXECUTED
  store.setPipelineStage("EXECUTED");
  store.setConnected(true);
}
// ── END DEV MOCK DATA ──────────────────────────────────────────────────

const ResizeHandle = ({ orientation = "horizontal" }) => (
  <Separator
    className={`group relative flex items-center justify-center ${
      orientation === "horizontal"
        ? "w-2 cursor-col-resize"
        : "h-2 cursor-row-resize"
    }`}
  >
    <div
      className={`resize-handle-bar transition-colors duration-150 ${
        orientation === "horizontal"
          ? "w-[1px] h-full bg-[#1e293b]"
          : "h-[1px] w-full bg-[#1e293b]"
      }`}
    />
    <div
      className={`absolute flex gap-[2px] opacity-0 group-hover:opacity-100 transition-opacity duration-150 ${
        orientation === "horizontal" ? "flex-col" : "flex-row"
      }`}
    >
      <div className="size-[3px] rounded-full bg-[#475569]" />
      <div className="size-[3px] rounded-full bg-[#475569]" />
      <div className="size-[3px] rounded-full bg-[#475569]" />
    </div>
  </Separator>
);

// Persistence hooks for each PanelGroup — useDefaultLayout reads/writes localStorage
const useMainLayout = () =>
  useDefaultLayout({ id: "captain-main-layout" });

const useCenterLayout = () =>
  useDefaultLayout({ id: "captain-center-layout" });

const useRightLayout = () =>
  useDefaultLayout({ id: "captain-right-layout" });

const useLeftLayout = () =>
  useDefaultLayout({ id: "captain-left-layout-v2" });

const DashboardPage = () => {
  useWebSocket("primary_user");
  const connected = useDashboardStore((s) => s.connected);
  const [initialLoading, setInitialLoading] = useState(!DEV_MOCK_ENABLED);

  const { defaultLayout: mainLayout, onLayoutChanged: onMainChanged } = useMainLayout();
  const { defaultLayout: centerLayout, onLayoutChanged: onCenterChanged } = useCenterLayout();
  const { defaultLayout: rightLayout, onLayoutChanged: onRightChanged } = useRightLayout();
  const { defaultLayout: leftLayout, onLayoutChanged: onLeftChanged } = useLeftLayout();

  useEffect(() => {
    // Load account list from backend (.env-driven, not hardcoded)
    useDashboardStore.getState().fetchAccounts();

    if (DEV_MOCK_ENABLED) {
      injectMockData();
      return;
    }

    api.dashboard("primary_user").then((data) => {
      useDashboardStore.getState().setSnapshot(data);
      setInitialLoading(false);
    }).catch(() => { setInitialLoading(false); });

    if (connected) return;

    const interval = setInterval(() => {
      api.dashboard("primary_user").then((data) => {
        useDashboardStore.getState().setSnapshot(data);
      }).catch(() => {});
    }, 10000);

    return () => clearInterval(interval);
  }, [connected]);

  return (
    <div data-testid="app-shell" className="relative w-full bg-surface overflow-hidden flex flex-col flex-1 min-h-0">
      <h1 className="sr-only">Captain Trading Dashboard</h1>
      {initialLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/80">
          <span className="text-xs text-[#64748b] font-['JetBrains_Mono']">Loading dashboard…</span>
        </div>
      )}
      {/* Resizable 3-column layout fills remaining height */}
      <Group
        orientation="horizontal"
        defaultLayout={mainLayout}
        onLayoutChanged={onMainChanged}
        className="flex-1 min-h-0"
      >
        {/* Left Column — Risk Panel */}
        <Panel id="left" defaultSize={30} minSize={10}>
          <Group
            orientation="vertical"
            defaultLayout={leftLayout}
            onLayoutChanged={onLeftChanged}
            className="h-full"
          >
            <Panel id="risk" defaultSize={40} minSize={10}>
              <div className="h-full overflow-y-auto">
                <RiskPanel />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            <Panel id="aim-registry" defaultSize={30} minSize={8}>
              <div className="h-full overflow-y-auto">
                <AimRegistryPanel />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            <Panel id="terminal" defaultSize={30} minSize={10}>
              <div className="h-full overflow-hidden">
                <LiveTerminal />
              </div>
            </Panel>
          </Group>
        </Panel>

        <ResizeHandle orientation="horizontal" />

        {/* Center Column — MarketTicker + Chart + Position + Signals */}
        <Panel id="center" defaultSize={48} minSize={20}>
          <div className="h-full flex flex-col">
          <div className="shrink-0">
            <MarketTicker />
          </div>
          <Group
            orientation="vertical"
            defaultLayout={centerLayout}
            onLayoutChanged={onCenterChanged}
            className="flex-1 min-h-0"
          >
            {/* Chart + ActivePosition + SignalExecutionBar */}
            <Panel id="chart" defaultSize={60} minSize={10}>
              <div className="h-full flex flex-col overflow-hidden">
                <div className="flex-1 min-h-0 overflow-hidden">
                  <ChartPanel />
                </div>
                <ActivePosition />
                <SignalExecutionBar />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            {/* Signal Cards */}
            <Panel id="signals" defaultSize={40} minSize={15}>
              <div className="h-full overflow-y-auto border-t border-[#1e293b]">
                <SignalCards />
              </div>
            </Panel>
          </Group>
          </div>
        </Panel>

        <ResizeHandle orientation="horizontal" />

        {/* Right Column — Trade Log + System Log */}
        <Panel id="right" defaultSize={22} minSize={10}>
          <Group
            orientation="vertical"
            defaultLayout={rightLayout}
            onLayoutChanged={onRightChanged}
            className="h-full"
          >
            {/* Trade Log */}
            <Panel id="tradelog" defaultSize={35} minSize={15}>
              <div className="h-full overflow-y-auto">
                <TradeLog />
              </div>
            </Panel>

            <ResizeHandle orientation="vertical" />

            {/* System Log */}
            <Panel id="syslog" defaultSize={65} minSize={15}>
              <div className="h-full overflow-y-auto">
                <SystemLog />
              </div>
            </Panel>
          </Group>
        </Panel>
      </Group>
    </div>
  );
};

export default DashboardPage;

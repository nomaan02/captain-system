// Mirrors return shapes from b2_gui_data_server.py

import type {
  AimStatus, CaptainStatus, IncidentSeverity,
  NotificationPriority, CommandType,
} from "@/utils/constants";

// --- Dashboard (build_dashboard_snapshot) ---

export interface CapitalSilo {
  total_capital: number | null;
  daily_pnl: number | null;
  cumulative_pnl: number | null;
  status: string | null;
}

export interface OpenPosition {
  signal_id: string;
  asset: string;
  direction: string;
  entry_price: number;
  contracts: number;
  tp_level: number;
  sl_level: number;
  account_id: string;
  entry_time: string;
  current_pnl: number | null;
}

export interface PendingSignal {
  signal_id: string;
  asset: string;
  timestamp: string;
  direction?: string;
  confidence_tier?: string;
  quality_score?: number;
}

export interface AimState {
  aim_id: string;
  aim_name: string;
  status: AimStatus;
  warmup_pct: number | null;
  meta_weight: number | null;
  modifier: number | null;
}

export interface TsmStatus {
  account_id: string;
  tsm_name: string;
  current_balance: number | null;
  mdd_limit: number;
  mdd_used_pct: number;
  daily_loss_limit: number;
  daily_loss_used: number;
  daily_loss_pct: number;
  pass_probability: number | null;
}

export interface DecayAlert {
  asset: string;
  cp_prob: number;
  cusum_stat: number;
  level: number;
  timestamp: string;
}

export interface WarmupGauge {
  asset_id: string;
  status: CaptainStatus;
  warmup_pct: number | null;
}

export interface Notification {
  notif_id: string;
  priority: NotificationPriority;
  message: string;
  timestamp: string;
  delivered: boolean;
}

export interface PayoutEntry {
  account_id: string;
  tsm_name: string;
  recommended: boolean;
  amount: number;
  net_after_commission: number;
  profit_current: number;
  profit_after: number;
  tier_current: string;
  tier_after: string;
  mdd_pct_current: number;
  mdd_pct_after: number;
  payouts_remaining: number;
  winning_days_current?: number;
  winning_days_required?: number;
  next_eligible_date?: string;
}

export interface ScalingEntry {
  account_id: string;
  active: boolean;
  current_tier: string;
  current_max_micros: number;
  open_positions_micros: number;
  available_slots: number;
  profit_to_next_tier: number;
  next_tier_label: string;
}

export interface LiveMarket {
  connected: boolean;
  contract_id: string;
  last_price: number | null;
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  change: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  timestamp: string | null;
}

export interface ApiStatus {
  api_authenticated: boolean;
  market_stream: string;
  user_stream: string;
  account_id: string | null;
  account_name: string | null;
  token_age_hours?: number;
}

export interface DashboardSnapshot {
  type: "dashboard";
  timestamp: string;
  user_id: string;
  capital_silo: CapitalSilo;
  open_positions: OpenPosition[];
  pending_signals: PendingSignal[];
  aim_states: AimState[];
  tsm_status: TsmStatus[];
  decay_alerts: DecayAlert[];
  warmup_gauges: WarmupGauge[];
  notifications: Notification[];
  payout_panel: PayoutEntry[];
  scaling_display: ScalingEntry[];
  live_market: LiveMarket;
  api_status: ApiStatus;
}

// --- System Overview (build_system_overview) ---

export interface Exposure {
  asset: string;
  direction: string;
  total_contracts: number;
  user_count: number;
}

export interface SignalQuality {
  total_evaluated: number;
  passed: number;
  pass_rate: number;
}

export interface DiagnosticScore {
  dimension: string;
  score: number;
  status: string;
  details: string | null;
  timestamp: string;
}

export interface ActionItem {
  dimension: string;
  status: string;
  details: string | null;
  timestamp: string;
}

export interface Incident {
  incident_id: string;
  type: string;
  severity: IncidentSeverity;
  component: string;
  details: string | null;
  status: string;
  timestamp: string;
}

export interface DataQualityAsset {
  asset_id: string;
  status: string;
  last_data_update: string | null;
}

export interface SystemOverview {
  type: "system_overview";
  timestamp: string;
  network_concentration: { exposures: Exposure[] };
  signal_quality: SignalQuality;
  capacity_state: Record<string, unknown>;
  diagnostic_health: DiagnosticScore[];
  action_queue: ActionItem[];
  system_params: Record<string, string>;
  data_quality: { assets: DataQualityAsset[] };
  incident_log: Incident[];
  compliance_gate: { execution_mode: string; requirements: Record<string, unknown> };
}

// --- Health endpoint ---

export interface HealthResponse {
  status: string;
  uptime_seconds: number;
  last_signal_time: string | null;
  active_users: number;
  circuit_breaker: string;
  api_connections: { connected: number; total: number };
  last_heartbeat: string | null;
}

// --- WebSocket message types ---

export interface WsSignalMessage {
  type: "signal";
  signal: {
    signal_id: string;
    asset: string;
    direction: string;
    contracts: number;
    tp_level: number;
    sl_level: number;
    entry_price: number;
    quality_score: number;
    confidence_tier: string;
    combined_modifier: number;
    regime_state: string;
    session: string;
    aim_breakdown: Record<string, number>;
    per_account: Record<string, { contracts: number; risk_amount: number }>;
    timestamp: string;
  };
}

export interface WsCommandAck {
  type: "command_ack";
  command: CommandType;
  action?: string;
  signal_id?: string;
  account_id?: string;
  tsm_name?: string;
}

export interface WsNotification {
  type: "notification";
  notif_id: string;
  priority: NotificationPriority;
  message: string;
  timestamp: string;
  source: string;
}

export interface WsBelowThreshold {
  type: "below_threshold";
  items: Array<{ asset: string; reason: string }>;
}

export type WsInbound =
  | { type: "connected"; user_id: string }
  | { type: "dashboard" } & DashboardSnapshot
  | { type: "live_market" } & LiveMarket
  | WsSignalMessage
  | WsCommandAck
  | WsNotification
  | WsBelowThreshold
  | { type: "system_overview" } & SystemOverview
  | { type: "error"; message: string }
  | { type: "validation_result"; valid: boolean; message?: string }
  | { type: "echo"; data: unknown };

// --- Report types ---

export interface ReportType {
  id: string;
  name: string;
  description: string;
}

export interface ReportResult {
  report_type: string;
  generated_at: string;
  data: Record<string, unknown>;
}

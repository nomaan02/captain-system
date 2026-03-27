// Mirrors shared/constants.py — keep in sync

export const CAPTAIN_STATUS = [
  "ACTIVE", "WARM_UP", "TRAINING_ONLY", "INACTIVE",
  "DATA_HOLD", "ROLL_PENDING", "PAUSED", "DECAYED",
] as const;
export type CaptainStatus = typeof CAPTAIN_STATUS[number];

export const AIM_STATUS = [
  "INSTALLED", "COLLECTING", "WARM_UP", "BOOTSTRAPPED",
  "ELIGIBLE", "ACTIVE", "SUPPRESSED",
] as const;
export type AimStatus = typeof AIM_STATUS[number];

export const TRADE_OUTCOME = [
  "TP_HIT", "SL_HIT", "MANUAL_CLOSE", "TIME_EXIT",
] as const;
export type TradeOutcome = typeof TRADE_OUTCOME[number];

export const INJECTION_RECOMMENDATION = [
  "ADOPT", "PARALLEL_TRACK", "REJECT",
] as const;
export type InjectionRecommendation = typeof INJECTION_RECOMMENDATION[number];

export const INCIDENT_SEVERITY = [
  "P1_CRITICAL", "P2_HIGH", "P3_MEDIUM", "P4_LOW",
] as const;
export type IncidentSeverity = typeof INCIDENT_SEVERITY[number];

export const NOTIFICATION_PRIORITY = [
  "CRITICAL", "HIGH", "MEDIUM", "LOW",
] as const;
export type NotificationPriority = typeof NOTIFICATION_PRIORITY[number];

export const REGIME = ["LOW_VOL", "HIGH_VOL"] as const;
export type Regime = typeof REGIME[number];

export const COMMAND_TYPES = [
  "TAKEN_SKIPPED", "ADOPT_STRATEGY", "REJECT_STRATEGY",
  "PARALLEL_TRACK", "SELECT_TSM", "ACTIVATE_AIM",
  "DEACTIVATE_AIM", "CONCENTRATION_PROCEED", "CONCENTRATION_PAUSE",
  "CONFIRM_ROLL", "UPDATE_ACTION_ITEM", "TRIGGER_DIAGNOSTIC",
  "MANUAL_PAUSE", "MANUAL_RESUME",
] as const;
export type CommandType = typeof COMMAND_TYPES[number];

export const SESSIONS: Record<number, string> = { 1: "NY", 2: "LON", 3: "APAC" };

export const SYSTEM_TIMEZONE = "America/New_York";

# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Function constants — code-level enum enforcement.

QuestDB doesn't support native enums, so we enforce valid values in code.
"""

# P3-D00: captain_status valid values
CAPTAIN_STATUS_VALUES = {
    "ACTIVE",
    "WARM_UP",
    "TRAINING_ONLY",
    "INACTIVE",
    "DATA_HOLD",
    "ROLL_PENDING",
    "PAUSED",
    "DECAYED",
}

# P3-D01: AIM lifecycle states
AIM_STATUS_VALUES = {
    "INSTALLED",
    "COLLECTING",
    "WARM_UP",
    "BOOTSTRAPPED",
    "ELIGIBLE",
    "ACTIVE",
    "SUPPRESSED",
}

# P3-D03: trade outcome types
TRADE_OUTCOME_VALUES = {
    "TP_HIT",
    "SL_HIT",
    "MANUAL_CLOSE",
    "TIME_EXIT",
}

# P3-D06: injection recommendation
INJECTION_RECOMMENDATION_VALUES = {
    "ADOPT",
    "PARALLEL_TRACK",
    "REJECT",
}

# P3-D21: incident severity
INCIDENT_SEVERITY_VALUES = {
    "P1_CRITICAL",
    "P2_HIGH",
    "P3_MEDIUM",
    "P4_LOW",
}

# Notification priority
NOTIFICATION_PRIORITY_VALUES = {
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
}

# Sessions
SESSION_IDS = {
    1: "NY",
    2: "LON",
    3: "APAC",
}

# Regime labels
REGIME_VALUES = {
    "LOW_VOL",
    "HIGH_VOL",
}

# System timezone
SYSTEM_TIMEZONE = "America/New_York"

# Command types (CMD-B1 routing)
COMMAND_TYPE_VALUES = {
    "TAKEN_SKIPPED",
    "ADOPT_STRATEGY",
    "REJECT_STRATEGY",
    "PARALLEL_TRACK",
    "SELECT_TSM",
    "ACTIVATE_AIM",
    "DEACTIVATE_AIM",
    "CONCENTRATION_PROCEED",
    "CONCENTRATION_PAUSE",
    "CONFIRM_ROLL",
    "UPDATE_ACTION_ITEM",
    "TRIGGER_DIAGNOSTIC",
    "MANUAL_PAUSE",
    "MANUAL_RESUME",
}

# Sanitised signal fields — ONLY these go to external API adapters
SANITISED_SIGNAL_FIELDS = {"asset", "direction", "size", "tp", "sl", "timestamp"}

# Prohibited fields — NEVER sent externally
PROHIBITED_EXTERNAL_FIELDS = {
    "aim_breakdown", "combined_modifier", "regime_probs",
    "kelly_params", "aim_weights", "strategy_logic",
    "ewma_states", "decay_states", "sensitivity_results",
}

# SOD reset time (19:00 EST)
SOD_RESET_HOUR = 19
SOD_RESET_MINUTE = 0

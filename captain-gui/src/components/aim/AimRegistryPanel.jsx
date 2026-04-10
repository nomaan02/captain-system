import { useState, useMemo, useCallback } from "react";
import useDashboardStore from "../../stores/dashboardStore";
import CollapsiblePanel from "../shared/CollapsiblePanel";
import AimDetailModal from "./AimDetailModal";
import api from "../../api/client";

// All 16 AIMs in order — always show all regardless of backend data
const ALL_AIMS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];

const AIM_NAMES = {
  1: "VRP", 2: "Opts Skew", 3: "GEX", 4: "IVTS",
  5: "Order Book", 6: "Econ Cal", 7: "COT", 8: "Cross Corr",
  9: "Cross Mom", 10: "Calendar", 11: "Regime Warn", 12: "Dyn Costs",
  13: "Sensitivity", 14: "Auto-Exp", 15: "Open Vol", 16: "HMM Opp",
};

const AIM_TIERS = {
  1: 2, 2: 2, 3: 2, 4: 1, 5: 0, 6: 1, 7: 2,
  8: 1, 9: 2, 10: 2, 11: 1, 12: 1, 13: 3, 14: 3, 15: 1, 16: 0,
};

const TIER_COLORS = {
  1: "text-[#10b981] border-[rgba(16,185,129,0.3)]",
  2: "text-[#3b82f6] border-[rgba(59,130,246,0.3)]",
  3: "text-[#f59e0b] border-[rgba(245,158,11,0.3)]",
};

const STATUS_COLORS = {
  ACTIVE:       { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  WARM_UP:      { bg: "bg-[rgba(245,158,11,0.1)]",  border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  ELIGIBLE:     { bg: "bg-[rgba(6,182,212,0.1)]",   border: "border-[rgba(6,182,212,0.3)]",  text: "text-[#06b6d4]" },
  BOOTSTRAPPED: { bg: "bg-[rgba(59,130,246,0.1)]",  border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  INACTIVE:     { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]",              text: "text-[#64748b]" },
  DEFERRED:     { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]",              text: "text-[#64748b]" },
  BLOCKED:      { bg: "bg-[rgba(239,68,68,0.1)]",   border: "border-[rgba(239,68,68,0.3)]",  text: "text-[#ef4444]" },
};

const DEFAULT_STATUS = STATUS_COLORS.INACTIVE;

// Priority for "worst status" aggregation (lower = worse)
const STATUS_PRIORITY = {
  BLOCKED: 0, INACTIVE: 1, DEFERRED: 1, WARM_UP: 2,
  BOOTSTRAPPED: 3, ELIGIBLE: 4, ACTIVE: 5,
};

function aggregateAim(aimId, rows) {
  if (!rows || rows.length === 0) {
    return { status: aimId === 5 ? "DEFERRED" : "INACTIVE", modMin: null, modMax: null, warmupMin: null, weightAvg: null };
  }

  // Worst status across assets
  let worstPriority = 99;
  let worstStatus = "ACTIVE";
  let modifiers = [];
  let warmups = [];
  let weights = [];

  for (const r of rows) {
    const s = (r.status || "INACTIVE").toUpperCase();
    const p = STATUS_PRIORITY[s] ?? 5;
    if (p < worstPriority) {
      worstPriority = p;
      worstStatus = s;
    }
    // Parse modifier (comes as string or number)
    const mod = typeof r.modifier === "string" ? parseFloat(r.modifier) : r.modifier;
    if (mod != null && !isNaN(mod)) modifiers.push(mod);
    if (r.warmup_pct != null) warmups.push(r.warmup_pct);
    if (r.meta_weight != null) weights.push(r.meta_weight);
  }

  return {
    status: worstStatus,
    modMin: modifiers.length > 0 ? Math.min(...modifiers) : null,
    modMax: modifiers.length > 0 ? Math.max(...modifiers) : null,
    warmupMin: warmups.length > 0 ? Math.min(...warmups) : null,
    weightAvg: weights.length > 0 ? weights.reduce((a, b) => a + b, 0) / weights.length : null,
  };
}

function formatModRange(min, max) {
  if (min == null) return "\u2014";
  if (min === max || Math.abs(min - max) < 0.005) return min.toFixed(2);
  return `${min.toFixed(2)}\u2013${max.toFixed(2)}`;
}

function modColor(min, max) {
  if (min == null) return "text-[#64748b]";
  // If entire range is above 1.0 → green, below 1.0 → red, mixed or exactly 1.0 → white
  if (min > 1.0) return "text-[#10b981]";
  if (max < 1.0) return "text-[#ef4444]";
  if (min === 1.0 && max === 1.0) return "text-white";
  return "text-white";
}

// Statuses where activation is possible
const CAN_ACTIVATE = new Set(["INACTIVE", "BOOTSTRAPPED", "ELIGIBLE", "SUPPRESSED"]);

const AimCard = ({ aimId, agg, onClick, onToggle, toggling }) => {
  const isDeferred = aimId === 5;
  const isHmm = aimId === 16;
  const tier = AIM_TIERS[aimId];
  const tierStyle = TIER_COLORS[tier];
  const statusStyle = STATUS_COLORS[agg.status] || DEFAULT_STATUS;
  const isActive = agg.status === "ACTIVE";
  const canToggle = !isDeferred && (isActive || CAN_ACTIVATE.has(agg.status));

  const handleToggle = (e) => {
    e.stopPropagation();
    if (!toggling && canToggle) onToggle(aimId, isActive);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      className={`bg-surface-card border ${isDeferred ? "border-dashed border-[#374151]" : "border-border-subtle"} p-3 text-left cursor-pointer hover:border-border-accent transition-colors duration-100 relative ${isDeferred ? "opacity-60" : ""}`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1">
          <span className={`text-[11px] font-mono ${isDeferred ? "text-[#64748b]" : "text-white"}`}>
            AIM-{String(aimId).padStart(2, "0")}
          </span>
          {tier > 0 && tierStyle && (
            <span className={`text-[10px] font-mono border px-0.5 ${tierStyle}`}>
              T{tier}
            </span>
          )}
        </div>
        <span className={`px-1.5 py-0 text-[9px] font-mono border border-solid uppercase ${statusStyle.bg} ${statusStyle.border} ${statusStyle.text}`}>
          {agg.status}
        </span>
      </div>

      {/* Name */}
      <div className={`text-[11px] font-mono mb-1.5 ${isDeferred ? "text-[#475569]" : "text-[#94a3b8]"}`}>
        {AIM_NAMES[aimId]}
      </div>

      {/* Modifier or SESSION BUDGET for AIM-16 */}
      {isHmm ? (
        <div className="text-[11px] font-mono text-[#06b6d4] mb-1">SESSION BUDGET</div>
      ) : (
        <div className={`text-xs font-mono mb-1 ${modColor(agg.modMin, agg.modMax)}`}>
          {formatModRange(agg.modMin, agg.modMax)}
        </div>
      )}

      {/* Weight bar */}
      {agg.weightAvg != null && (
        <div
          role="progressbar"
          aria-valuenow={Math.round(agg.weightAvg * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="AIM weight"
          className="h-[3px] w-full bg-[rgba(226,232,240,0.06)] mb-1"
        >
          <div
            className="h-full bg-captain-green"
            style={{ width: `${Math.min(agg.weightAvg * 100, 100)}%` }}
          />
        </div>
      )}

      {/* Warmup indicator */}
      {agg.status === "WARM_UP" && agg.warmupMin != null && (
        <div
          role="progressbar"
          aria-valuenow={Math.round(agg.warmupMin)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="AIM warmup progress"
          className="h-[2px] w-full bg-[rgba(245,158,11,0.15)]"
        >
          <div
            className="h-full bg-[#f59e0b]"
            style={{ width: `${Math.min(agg.warmupMin, 100)}%` }}
          />
        </div>
      )}
      {agg.status === "ELIGIBLE" && (
        <div className="text-[9px] font-mono text-[#06b6d4]">Features ready</div>
      )}

      {/* Activate / Deactivate button */}
      {canToggle && (
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`mt-1.5 w-full min-h-[32px] py-1 text-[11px] font-mono uppercase tracking-wider border border-solid cursor-pointer transition-colors duration-100 flex items-center justify-center ${
            toggling
              ? "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#475569] cursor-wait"
              : isActive
                ? "bg-[rgba(239,68,68,0.08)] border-[rgba(239,68,68,0.25)] text-[#ef4444] hover:bg-[rgba(239,68,68,0.15)]"
                : "bg-[rgba(16,185,129,0.08)] border-[rgba(16,185,129,0.25)] text-[#10b981] hover:bg-[rgba(16,185,129,0.15)]"
          }`}
        >
          {toggling ? "..." : isActive ? "Deactivate" : "Activate"}
        </button>
      )}

    </div>
  );
};

const AimRegistryPanel = () => {
  const aimStates = useDashboardStore((s) => s.aimStates);
  const [selectedAim, setSelectedAim] = useState(null);
  const [togglingAim, setTogglingAim] = useState(null);

  // Group aimStates by aim_id
  const byAim = useMemo(() => {
    const map = {};
    for (const row of aimStates) {
      const id = row.aim_id;
      if (!map[id]) map[id] = [];
      map[id].push(row);
    }
    return map;
  }, [aimStates]);

  // Aggregate each AIM
  const aggregated = useMemo(() => {
    const result = {};
    for (const id of ALL_AIMS) {
      result[id] = aggregateAim(id, byAim[id]);
    }
    return result;
  }, [byAim]);

  // Count active
  const activeCount = ALL_AIMS.filter((id) => aggregated[id].status === "ACTIVE").length;

  const handleToggle = useCallback(async (aimId, isCurrentlyActive) => {
    setTogglingAim(aimId);
    try {
      if (isCurrentlyActive) {
        await api.aimDeactivate(aimId);
      } else {
        await api.aimActivate(aimId);
      }
    } catch (err) {
      console.error("AIM toggle failed:", err);
    } finally {
      // Brief delay to let Offline process the command before next dashboard refresh
      setTimeout(() => setTogglingAim(null), 1500);
    }
  }, []);

  return (
    <>
      <CollapsiblePanel
        title="AIM Registry"
        storageKey="captain-aim-registry-open"
        defaultOpen={true}
        headerRight={
          <span className="text-[10px] font-mono text-[#94a3b8]">
            {activeCount}/{ALL_AIMS.length} active
          </span>
        }
      >
        <div className="grid grid-cols-2 gap-1.5 md:grid-cols-3 lg:grid-cols-4">
          {ALL_AIMS.map((id) => (
            <AimCard
              key={id}
              aimId={id}
              agg={aggregated[id]}
              onClick={() => setSelectedAim(id)}
              onToggle={handleToggle}
              toggling={togglingAim === id}
            />
          ))}
        </div>
      </CollapsiblePanel>

      {selectedAim != null && (
        <AimDetailModal
          aimId={selectedAim}
          aimName={AIM_NAMES[selectedAim]}
          onClose={() => setSelectedAim(null)}
        />
      )}
    </>
  );
};

export default AimRegistryPanel;

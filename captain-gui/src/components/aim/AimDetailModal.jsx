import { useState, useEffect, useRef } from "react";
import api from "../../api/client";
import StatusBadge from "../shared/StatusBadge";

// Static AIM configuration data from reconciliation matrix
const AIM_CONFIG = {
  1:  { tier: 2, retrain: "Monthly", warmupFeature: "120d", warmupTrades: 50, feed: "STUB_NONE", thresholds: "z>1.5\u21920.70, z>0.5\u21920.85, z<-1.0\u21921.10" },
  2:  { tier: 2, retrain: "Monthly", warmupFeature: "120d", warmupTrades: 50, feed: "STUB_NONE", thresholds: "combined>1.5\u21920.75, >0.5\u21920.90, <-1.0\u21921.10" },
  3:  { tier: 2, retrain: "Monthly", warmupFeature: "250d", warmupTrades: 50, feed: "STUB_NONE", thresholds: "GEX_z<-1.0\u21920.85, GEX_z>1.0\u21921.10" },
  4:  { tier: 1, retrain: "Weekly",  warmupFeature: "60d",  warmupTrades: 50, feed: "CONNECTED",  thresholds: ">1.10\u21920.65, (1.0,1.10]\u21920.80, [0.93,1.0]\u21921.10, [0.85,0.93)\u21920.90, <0.85\u21920.80" },
  5:  { tier: 0, retrain: "N/A",     warmupFeature: "N/A",  warmupTrades: 0,  feed: "N/A",        thresholds: "N/A (deferred)" },
  6:  { tier: 1, retrain: "Weekly",  warmupFeature: "~2yr", warmupTrades: 50, feed: "CONNECTED",  thresholds: "T1 \u226430min\u21920.70, >30min\u21921.05" },
  7:  { tier: 2, retrain: "Monthly", warmupFeature: "52w",  warmupTrades: 50, feed: "STUB_NONE", thresholds: "z>1.5\u21920.95, z<-1.5\u21921.10" },
  8:  { tier: 1, retrain: "Weekly",  warmupFeature: "120d", warmupTrades: 50, feed: "CONNECTED",  thresholds: "corr_z>1.5\u21920.80, >0.5\u21920.90, <-0.5\u21921.05" },
  9:  { tier: 2, retrain: "Monthly", warmupFeature: "63d",  warmupTrades: 50, feed: "CONNECTED",  thresholds: "mom>0.5\u21921.10, <-0.5\u21920.90" },
  10: { tier: 2, retrain: "Monthly", warmupFeature: "120d", warmupTrades: 50, feed: "CONNECTED",  thresholds: "OPEX\u21920.95" },
  11: { tier: 1, retrain: "Weekly",  warmupFeature: "120d", warmupTrades: 50, feed: "CONNECTED",  thresholds: "VIX_z>1.5\u21920.75, >0.5\u21920.90, <-0.5\u21921.05" },
  12: { tier: 1, retrain: "Weekly",  warmupFeature: "50d",  warmupTrades: 50, feed: "CONNECTED",  thresholds: "spread_z>1.5 OR vol_z>1.5\u21920.85" },
  13: { tier: 3, retrain: "Quarterly", warmupFeature: "100d+", warmupTrades: 50, feed: "Internal", thresholds: "PBO/DSR-based" },
  14: { tier: 3, retrain: "Quarterly", warmupFeature: "252d",  warmupTrades: 50, feed: "Internal", thresholds: "Always 1.0" },
  15: { tier: 1, retrain: "Weekly",  warmupFeature: "60d",  warmupTrades: 50, feed: "CONNECTED",  thresholds: "vol_z>1.5\u21921.15, >1.0\u21921.05, <0.7\u21920.80" },
  16: { tier: 0, retrain: "N/A",     warmupFeature: "60d",  warmupTrades: 0,  feed: "P3-D26",     thresholds: "HMM session weights (Block 5)" },
};

const TIER_LABELS = { 0: "N/A", 1: "T1 \u2014 Weekly", 2: "T2 \u2014 Monthly", 3: "T3 \u2014 Quarterly" };

const CheckIcon = ({ ok }) => (
  <span
    role="img"
    aria-label={ok ? "Passed" : "Failed"}
    className={`font-mono text-[11px] ${ok ? "text-[#10b981]" : "text-[#ef4444]"}`}
  >
    {ok ? "\u2713" : "\u2717"}
  </span>
);

const AimDetailModal = ({ aimId, aimName, onClose }) => {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const modalRef = useRef(null);
  const closeRef = useRef(null);
  const triggerRef = useRef(document.activeElement);

  // Fetch detail on mount
  useEffect(() => {
    setLoading(true);
    setError(null);
    api.aimDetail(aimId)
      .then((data) => { setDetail(data); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, [aimId]);

  // Click outside to close
  useEffect(() => {
    const handleClick = (e) => {
      if (modalRef.current && !modalRef.current.contains(e.target)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  // Escape to close
  useEffect(() => {
    const handleKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Focus trap: cycle Tab within modal, auto-focus close button
  useEffect(() => {
    closeRef.current?.focus();
    const handleTab = (e) => {
      if (e.key !== "Tab" || !modalRef.current) return;
      const els = modalRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!els.length) return;
      const first = els[0];
      const last = els[els.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleTab);
    return () => {
      document.removeEventListener("keydown", handleTab);
      triggerRef.current?.focus();
    };
  }, []);

  const config = AIM_CONFIG[aimId] || {};
  const tierLabel = TIER_LABELS[config.tier] || "Unknown";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="aim-modal-title"
        className="bg-surface-elevated border border-border-accent max-w-[640px] w-[95vw] max-h-[80vh] overflow-y-auto font-mono"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <div className="flex items-center gap-3">
            <span id="aim-modal-title" className="text-white text-sm tracking-[1px]">
              AIM-{String(aimId).padStart(2, "0")}: {aimName}
            </span>
            {detail && (
              <StatusBadge status={detail.per_asset?.[0]?.d01_status || "UNKNOWN"} />
            )}
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            className="text-[#64748b] hover:text-white text-sm bg-transparent border-none cursor-pointer min-w-[32px] min-h-[32px] flex items-center justify-center"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="px-4 py-3">
          {loading && (
            <div className="text-[#64748b] text-xs py-8 text-center">Loading...</div>
          )}
          {error && (
            <div className="text-[#ef4444] text-xs py-8 text-center">{error}</div>
          )}
          {detail && !loading && (
            <>
              {/* Section A: Per-Asset Breakdown */}
              <div className="mb-4">
                <div className="text-[11px] text-captain-green tracking-[1.5px] uppercase mb-2">
                  Per-Asset Breakdown
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] border-collapse">
                    <thead>
                      <tr className="text-[rgba(226,232,240,0.5)] uppercase tracking-wider">
                        <th className="text-left py-1 pr-2">Asset</th>
                        <th className="text-left py-1 pr-2">Status</th>
                        <th className="text-right py-1 pr-2">Modifier</th>
                        <th className="text-right py-1 pr-2">Weight</th>
                        <th className="text-right py-1 pr-2">Warmup</th>
                        <th className="text-right py-1">Retrained</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.per_asset.length > 0 ? (
                        detail.per_asset.map((row) => {
                          const mod = row.d01_modifier;
                          const modColor = mod == null ? "text-[#64748b]"
                            : mod > 1.0 ? "text-[#10b981]"
                            : mod < 1.0 ? "text-[#ef4444]"
                            : "text-white";
                          return (
                            <tr key={row.asset_id} className="border-t border-[#1e293b]">
                              <td className="py-1.5 pr-2 text-white">{row.asset_id}</td>
                              <td className="py-1.5 pr-2">
                                <StatusBadge status={row.d01_status || "UNKNOWN"} />
                              </td>
                              <td className={`py-1.5 pr-2 text-right ${modColor}`}>
                                {mod != null ? mod.toFixed(2) : <CheckIcon ok={false} />}
                              </td>
                              <td className="py-1.5 pr-2 text-right text-[#94a3b8]">
                                {row.d02_inclusion_probability != null
                                  ? row.d02_inclusion_probability.toFixed(3)
                                  : <CheckIcon ok={false} />}
                              </td>
                              <td className="py-1.5 pr-2 text-right text-[#94a3b8]">
                                {row.d01_warmup_progress != null
                                  ? `${Math.round(row.d01_warmup_progress)}%`
                                  : <CheckIcon ok={false} />}
                              </td>
                              <td className="py-1.5 text-right text-[#64748b]">
                                {row.d01_last_retrained
                                  ? new Date(row.d01_last_retrained).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                                  : <CheckIcon ok={false} />}
                              </td>
                            </tr>
                          );
                        })
                      ) : (
                        <tr>
                          <td colSpan={6} className="py-4 text-center text-[#64748b]">
                            No asset data for this AIM
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Section B: QuestDB Data Validation */}
              <div className="mb-4">
                <div className="text-[11px] text-captain-green tracking-[1.5px] uppercase mb-2">
                  Data Validation
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                  <div className="flex items-center justify-between text-[#94a3b8]">
                    <span>P3-D01 (model states)</span>
                    <CheckIcon ok={detail.validation.d01_populated} />
                  </div>
                  <div className="flex items-center justify-between text-[#94a3b8]">
                    <span>P3-D02 (meta weights)</span>
                    <CheckIcon ok={detail.validation.d02_populated} />
                  </div>
                  <div className="flex items-center justify-between text-[#94a3b8]">
                    <span>Feature data feed</span>
                    <CheckIcon ok={detail.validation.feature_data_connected} />
                  </div>
                  {detail.validation.d26_populated != null && (
                    <div className="flex items-center justify-between text-[#94a3b8]">
                      <span>P3-D26 (HMM state)</span>
                      <CheckIcon ok={detail.validation.d26_populated} />
                    </div>
                  )}
                </div>
                <div className={`mt-2 text-[11px] px-2 py-1 border ${
                  detail.validation.all_checks_pass
                    ? "bg-[rgba(16,185,129,0.1)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                    : "bg-[rgba(239,68,68,0.1)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"
                }`}>
                  {detail.validation.all_checks_pass ? "ALL CHECKS PASS" : "VALIDATION INCOMPLETE"}
                </div>
              </div>

              {/* Section C: AIM Configuration */}
              <div>
                <div className="text-[11px] text-captain-green tracking-[1.5px] uppercase mb-2">
                  Configuration
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
                  <div>
                    <span className="text-[rgba(226,232,240,0.5)]">Tier: </span>
                    <span className="text-white">{tierLabel}</span>
                  </div>
                  <div>
                    <span className="text-[rgba(226,232,240,0.5)]">Feed: </span>
                    <span className={config.feed === "CONNECTED" ? "text-[#10b981]" : config.feed === "STUB_NONE" ? "text-[#ef4444]" : "text-[#64748b]"}>
                      {config.feed || "Unknown"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[rgba(226,232,240,0.5)]">Feature gate: </span>
                    <span className="text-[#94a3b8]">{config.warmupFeature || "—"}</span>
                  </div>
                  <div>
                    <span className="text-[rgba(226,232,240,0.5)]">Learning gate: </span>
                    <span className="text-[#94a3b8]">{config.warmupTrades ? `${config.warmupTrades} trades` : "—"}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-[rgba(226,232,240,0.5)]">Thresholds: </span>
                    <span className="text-[#94a3b8]">{config.thresholds || "—"}</span>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-border-subtle text-[11px] text-[rgba(226,232,240,0.25)] flex justify-between">
          <span>SYS:AIM_REGISTRY</span>
          <span>SRC:P3-D01+D02</span>
        </div>
      </div>
    </div>
  );
};

export default AimDetailModal;

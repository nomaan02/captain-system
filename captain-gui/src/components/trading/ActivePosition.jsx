import { useState, useEffect } from "react";
import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPrice } from "../../utils/formatting";
import { POINT_VALUES } from "../../constants/pointValues";

const TICK_SIZES = {
  MES: 0.25, ES: 0.25, MNQ: 0.25, NQ: 0.25,
  MYM: 1.0, M2K: 0.10, MGC: 0.10, MCL: 0.01,
  NKD: 5.0, ZB: 1 / 32, ZN: 1 / 64,
};

function formatElapsed(entryTime, now) {
  const ms = now - new Date(entryTime).getTime();
  if (ms <= 0) return "00:00:00";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

const ActivePosition = ({ className = "" }) => {
  const openPositions = useDashboardStore((s) => s.openPositions);
  const pendingSignals = useDashboardStore((s) => s.pendingSignals);
  const selectedSignalId = useDashboardStore((s) => s.selectedSignalId);
  const allMarket = useDashboardStore((s) => s.liveMarket);
  const [now, setNow] = useState(Date.now());

  // --- Resolve display source: real position > selected signal > pending ---
  const selectedSignal = selectedSignalId
    ? pendingSignals.find((s) => s.signal_id === selectedSignalId)
    : null;

  let pos = null;
  let isPreview = false;

  if (selectedSignal) {
    const sigAsset = selectedSignal.asset_id ?? selectedSignal.asset;
    const matching = openPositions.find((p) => (p.asset_id ?? p.asset) === sigAsset);
    if (matching) {
      pos = matching;
    } else {
      pos = {
        direction: selectedSignal.direction,
        asset_id: sigAsset,
        entry_price: selectedSignal.entry_price,
        sl_level: selectedSignal.sl_level,
        tp_level: selectedSignal.tp_level,
        contracts: selectedSignal.contracts ?? 1,
        order_id: selectedSignal.signal_id,
        entry_time: selectedSignal.timestamp,
        current_pnl: selectedSignal.pnl ?? null,
      };
      isPreview = true;
    }
  } else if (openPositions.length > 0) {
    pos = openPositions[0];
  }

  const isPending = !pos;

  // --- Derived values ---
  const direction = pos?.direction ?? null;
  const asset = pos?.asset_id ?? pos?.asset ?? "—";
  const contracts = pos?.contracts ?? null;
  const entryPrice = pos?.entry_price ?? null;
  const slLevel = pos?.sl_level ?? null;
  const tpLevel = pos?.tp_level ?? null;
  const orderId = pos?.order_id ?? null;
  const entryTime = pos?.entry_time ?? null;

  const currentPrice = allMarket?.[asset]?.last_price ?? null;
  const pointValue = POINT_VALUES[asset] ?? 5;
  const tickSize = TICK_SIZES[asset] ?? 0.25;

  // PnL: compute from market data for responsiveness, fallback to stored value
  const computedPnl =
    !isPending && currentPrice != null && entryPrice != null && direction
      ? (currentPrice - entryPrice) *
        (direction === "LONG" ? 1 : -1) *
        (contracts ?? 1) *
        pointValue
      : null;
  const pnl = isPending ? 0 : computedPnl ?? pos?.current_pnl ?? 0;

  const ticks =
    !isPending && currentPrice != null && entryPrice != null
      ? Math.round(
          ((currentPrice - entryPrice) * (direction === "LONG" ? 1 : -1)) /
            tickSize
        )
      : 0;

  // SL/TP distances from entry
  const slDist =
    slLevel != null && entryPrice != null ? Math.abs(entryPrice - slLevel) : null;
  const tpDist =
    tpLevel != null && entryPrice != null ? Math.abs(tpLevel - entryPrice) : null;
  const slDistVal = slDist != null ? slDist * (contracts ?? 1) * pointValue : null;
  const tpDistVal = tpDist != null ? tpDist * (contracts ?? 1) * pointValue : null;

  // Gradient bar: (price - SL) / (TP - SL) works for both LONG and SHORT
  const barDenom =
    tpLevel != null && slLevel != null ? tpLevel - slLevel : 0;
  const calcBarPct = (price) => {
    if (!barDenom || price == null || slLevel == null) return null;
    return Math.max(0, Math.min(100, ((price - slLevel) / barDenom) * 100));
  };
  const currentPct = calcBarPct(currentPrice);

  // Elapsed timer - ticks every second when active
  useEffect(() => {
    if (!entryTime) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [entryTime]);

  const elapsedStr = entryTime ? formatElapsed(entryTime, now) : "—";
  const isProfit = pnl >= 0;
  const pnlColor = isPending
    ? "text-[#64748b]"
    : isProfit
      ? "text-[#10b981]"
      : "text-[#ef4444]";
  const curColor =
    isPending || currentPrice == null
      ? "text-[#64748b]"
      : isProfit
        ? "text-[#10b981]"
        : "text-[#ef4444]";

  return (
    <section
      data-testid="active-position"
      className={`self-stretch font-['JetBrains_Mono'] text-[10px] text-[#64748b] ${className}`}
    >
      <div
        className={`w-full border-b border-[#1e293b] flex flex-col gap-[5px] pb-1 transition-opacity duration-300 ${
          isPending ? "opacity-50" : ""
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-2 pt-[3px] pb-[3px] border-b border-[#1e293b]">
          <div className="flex items-center gap-1.5">
            <div
              className={`w-[5px] h-[5px] rounded-full ${
                isPending
                  ? "bg-[rgba(100,116,139,0.5)]"
                  : "bg-[rgba(16,185,129,0.54)]"
              }`}
            />
            <span className="text-[9px] tracking-[1px] leading-[14px] uppercase">
              Active Position
            </span>
          </div>
          <div className="flex items-center gap-[5px]">
            {direction ? (
              <>
                <span
                  data-testid="position-direction"
                  className={`px-1 py-[0.5px] text-[10px] leading-[13px] border border-solid ${
                    direction === "LONG"
                      ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                      : "bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"
                  }`}
                >
                  {direction}
                </span>
                <span
                  data-testid="position-asset"
                  className="text-[9px] text-[#06b6d4]"
                >
                  {asset}
                </span>
                <span className="text-[9px] leading-[12px]">
                  x{contracts ?? "—"}
                </span>
                <span className="text-[9px] leading-[12px]">
                  {orderId ?? "—"}
                </span>
              </>
            ) : (
              <span className="text-[9px]">—</span>
            )}
          </div>
        </div>

        {/* Entry + Current + PnL */}
        <div className="flex items-start justify-between px-2">
          <div className="flex items-start gap-[10px]">
            <div className="flex flex-col gap-[2px]">
              <span className="text-[10px] leading-tight">ENTRY</span>
              <span
                data-testid="position-entry"
                className="text-[11px] leading-[11px] text-[#e2e8f0]"
              >
                {entryPrice != null ? formatPrice(entryPrice) : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-[2px]">
              <span className="text-[10px] leading-tight">CURRENT</span>
              <span
                data-testid="position-current"
                className={`text-[11px] leading-[11px] ${curColor}`}
              >
                {currentPrice != null ? formatPrice(currentPrice) : "—"}
              </span>
            </div>
          </div>
          <div
            data-testid="position-pnl"
            className={`text-right ${pnlColor}`}
          >
            <span className="text-lg leading-[18px]">
              {isPending
                ? "$0.00"
                : formatCurrency(pnl, { showSign: true })}
            </span>
            {!isPending && (
              <span
                className={`text-[9px] ${
                  isProfit
                    ? "text-[rgba(16,185,129,0.7)]"
                    : "text-[rgba(239,68,68,0.7)]"
                }`}
              >
                ({ticks >= 0 ? "+" : ""}
                {ticks}t)
              </span>
            )}
          </div>
        </div>

        {/* SL / TP */}
        <div className="flex items-center justify-between px-2">
          {isPending ? (
            <>
              <span className="text-[rgba(239,68,68,0.4)] leading-tight">
                PENDING
              </span>
              <span className="text-[rgba(16,185,129,0.4)] leading-tight">
                PENDING
              </span>
            </>
          ) : (
            <>
              <span className="text-[#ef4444] leading-tight">
                SL {slLevel != null ? formatPrice(slLevel) : "—"}
              </span>
              <span className="text-[#10b981] leading-tight">
                TP {tpLevel != null ? formatPrice(tpLevel) : "—"}
              </span>
            </>
          )}
        </div>

        {/* Gradient bar */}
        <div className="px-2">
          <div
            className={`w-full h-1.5 relative ${isPending ? "opacity-30" : ""}`}
            style={{
              background:
                "linear-gradient(90deg, #ef4444, #1e293b 50%, #10b981)",
            }}
          >
            {currentPct != null && !isPending && (
              <div
                className="absolute top-0 h-full w-[2px] bg-[#06b6d4]"
                style={{
                  left: `${currentPct}%`,
                  transition: "left 300ms ease-out",
                  boxShadow: "0 0 4px rgba(6,182,212,0.6)",
                }}
              />
            )}
          </div>
        </div>

        {/* Distance to SL / TP */}
        <div className="flex items-center justify-between px-2">
          <span className="text-[#10b981] leading-tight">
            {slDist != null
              ? `${slDist.toFixed(2)}pts (${formatCurrency(slDistVal)})`
              : "—"}
          </span>
          <span className="text-[#10b981] leading-tight">
            {tpDist != null
              ? `${tpDist.toFixed(2)}pts (${formatCurrency(tpDistVal)})`
              : "—"}
          </span>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-[10px] px-2 text-[10px]">
          <span>
            Time:{" "}
            <span className="text-[#e2e8f0]">{elapsedStr}</span>
          </span>
          <span>
            Lots:{" "}
            <span className="text-[#e2e8f0]">{contracts ?? "—"}</span>
          </span>
          <span>
            Fill:{" "}
            <span className="text-[#e2e8f0]">{orderId ?? "—"}</span>
          </span>
        </div>
      </div>
    </section>
  );
};

ActivePosition.propTypes = {
  className: PropTypes.string,
};

export default ActivePosition;

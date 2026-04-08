import useReplayStore from "../../stores/replayStore";
import { formatPrice } from "../../utils/formatting";

const SimulatedPosition = () => {
  const pos = useReplayStore((s) => s.activeSimPosition);

  if (!pos) {
    return (
      <section
        data-testid="simulated-position"
        className="flex items-center justify-center py-3 text-[10px] text-[#64748b] font-mono border-b border-[#1e293b]"
      >
        <span data-testid="sim-position-empty">No active position</span>
      </section>
    );
  }

  const direction = pos.direction;
  const asset = pos.asset_id ?? "---";
  const contracts = pos.contracts;

  return (
    <section
      data-testid="simulated-position"
      className="border-b border-[#1e293b] px-3 py-2 font-mono"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5">
          <div className="w-[5px] h-[5px] rounded-full bg-[rgba(245,158,11,0.54)]" />
          <span className="text-[9px] tracking-[1px] leading-[13px] uppercase text-[#f59e0b]">
            Simulated Position
          </span>
        </div>
        <div className="flex items-center gap-[5px]">
          <span
            className={`px-1 py-[1px] text-[8px] leading-[12px] border border-solid ${
              direction === "LONG"
                ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                : "bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"
            }`}
          >
            {direction}
          </span>
          <span data-testid="sim-position-asset" className="text-[9px] text-[#06b6d4]">{asset}</span>
          {contracts != null && (
            <span className="text-[8px] text-[#64748b]">{`x${contracts}`}</span>
          )}
        </div>
      </div>

      {/* Price levels */}
      <div className="flex items-center gap-4 text-[8px]">
        <span>
          <span className="text-[#64748b]">Entry </span>
          <span data-testid="sim-position-entry" className="text-[11px] text-[#e2e8f0]">{formatPrice(pos.entry_price)}</span>
        </span>
        <span>
          <span className="text-[#64748b]">TP </span>
          <span className="text-[#10b981]">{formatPrice(pos.tp_level)}</span>
        </span>
        <span>
          <span className="text-[#64748b]">SL </span>
          <span className="text-[#ef4444]">{formatPrice(pos.sl_level)}</span>
        </span>
      </div>
    </section>
  );
};

export default SimulatedPosition;

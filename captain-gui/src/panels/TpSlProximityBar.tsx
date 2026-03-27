import { clamp } from "@/utils/formatters";

interface Props {
  entry: number;
  tp: number;
  sl: number;
  current: number;
}

export function TpSlProximityBar({ entry, tp, sl, current }: Props) {
  const range = Math.abs(tp - sl) || 1;
  // Normalize: SL = 0%, TP = 100%
  const entryPct = clamp(((entry - sl) / range) * 100, 0, 100);
  const currentPct = clamp(((current - sl) / range) * 100, 0, 100);

  return (
    <div className="relative h-3 w-full rounded-full bg-gradient-to-r from-red-500/20 via-gray-300/20 to-green-500/20 dark:from-red-500/30 dark:via-gray-600/30 dark:to-green-500/30">
      {/* Entry marker */}
      <div
        className="absolute top-0 h-full w-px bg-gray-400"
        style={{ left: `${entryPct}%` }}
        title={`Entry: ${entry.toFixed(2)}`}
      />
      {/* Current price marker */}
      <div
        className="absolute -top-0.5 h-4 w-2 rounded-sm bg-captain-blue shadow"
        style={{ left: `${currentPct}%`, transform: "translateX(-50%)" }}
        title={`Current: ${current.toFixed(2)}`}
      />
      {/* Labels */}
      <span className="absolute -bottom-4 left-0 text-[9px] text-red-500">SL</span>
      <span className="absolute -bottom-4 right-0 text-[9px] text-green-500">TP</span>
    </div>
  );
}

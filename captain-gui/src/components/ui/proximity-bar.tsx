import { cn } from "@/lib/utils";

interface ProximityBarProps {
  entry: number;
  tp: number;
  sl: number;
  current: number;
  className?: string;
}

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max);
}

export function ProximityBar({ entry, tp, sl, current, className }: ProximityBarProps) {
  const range = tp - sl;
  const pct = range !== 0 ? clamp(((current - sl) / range) * 100, 0, 100) : 50;

  const riskReward =
    entry - sl !== 0 ? ((tp - entry) / (entry - sl)).toFixed(1) : "—";

  return (
    <div className={cn("space-y-1", className)}>
      {/* Bar */}
      <div className="relative h-1.5 overflow-hidden rounded-[3px] bg-muted">
        {/* SL zone — left 35% */}
        <div
          className="absolute inset-y-0 left-0 rounded-l-[3px]"
          style={{ width: "35%", backgroundColor: "rgba(248, 113, 113, 0.2)" }}
        />
        {/* Safe zone — middle 30% */}
        <div
          className="absolute inset-y-0"
          style={{ left: "35%", width: "30%", backgroundColor: "rgba(74, 222, 128, 0.15)" }}
        />
        {/* TP zone — right 35% */}
        <div
          className="absolute inset-y-0 right-0 rounded-r-[3px]"
          style={{ width: "35%", backgroundColor: "rgba(74, 222, 128, 0.2)" }}
        />
        {/* Current price marker */}
        <div
          className="absolute inset-y-0 w-0.5 rounded-[1px] bg-foreground"
          style={{ left: `${pct}%`, transform: "translateX(-50%)" }}
        />
      </div>

      {/* Labels */}
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-dim">SL</span>
        <span className="text-muted-foreground">R:R {riskReward}:1</span>
        <span className="text-dim">TP</span>
      </div>
    </div>
  );
}

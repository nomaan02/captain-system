import { cn } from "@/lib/utils";

interface ProgressBarProps {
  /** Current value (0 to max) */
  value: number;
  /** Maximum value (default 100) */
  max?: number;
  /** Invert threshold colors (high % = good, e.g., warmup progress) */
  invertThresholds?: boolean;
  /** Override fill color entirely */
  color?: string;
  /** Optional label shown left of bar */
  label?: string;
  /** Show percentage text right of bar */
  showValue?: boolean;
  className?: string;
}

function getAutoColor(pct: number, invert: boolean): string {
  if (invert) {
    if (pct < 30) return "#f87171";
    if (pct < 60) return "#facc15";
    return "#4ade80";
  }
  if (pct < 30) return "#4ade80";
  if (pct < 60) return "#facc15";
  return "#f87171";
}

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), max);
}

export function ProgressBar({
  value,
  max = 100,
  invertThresholds = false,
  color,
  label,
  showValue = false,
  className,
}: ProgressBarProps) {
  const pct = clamp((value / max) * 100, 0, 100);
  const fillColor = color ?? getAutoColor(pct, invertThresholds);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {label && (
        <span className="shrink-0 text-[11px] text-dim">{label}</span>
      )}
      <div className="h-1 flex-1 overflow-hidden rounded-sm bg-muted">
        <div
          className="h-full rounded-sm transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%`, backgroundColor: fillColor }}
        />
      </div>
      {showValue && (
        <span className="shrink-0 text-[11px] font-semibold text-foreground">
          {pct.toFixed(0)}%
        </span>
      )}
    </div>
  );
}

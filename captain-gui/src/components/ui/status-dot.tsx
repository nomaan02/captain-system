import { cn } from "@/lib/utils";

const dotColors = {
  ok: "#4ade80",
  warning: "#facc15",
  danger: "#f87171",
  info: "#3b82f6",
  off: "#3f3f46",
} as const;

type DotStatus = keyof typeof dotColors;

interface StatusDotProps {
  status: DotStatus;
  label?: string;
  pulse?: boolean;
  className?: string;
}

export function StatusDot({ status, label, pulse, className }: StatusDotProps) {
  const color = dotColors[status];

  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span className="relative flex" style={{ width: 6, height: 6 }}>
        {pulse && (
          <span
            className="absolute inset-0 animate-ping rounded-full opacity-75"
            style={{ backgroundColor: color }}
          />
        )}
        <span
          className="relative inline-flex rounded-full"
          style={{ width: 6, height: 6, backgroundColor: color }}
        />
      </span>
      {label && (
        <span className="text-[11px] text-dim">{label}</span>
      )}
    </span>
  );
}

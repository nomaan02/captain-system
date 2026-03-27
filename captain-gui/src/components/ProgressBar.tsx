import { clamp } from "@/utils/formatters";

interface Props {
  value: number;
  max?: number;
  color?: string;
  bgColor?: string;
  height?: string;
  showLabel?: boolean;
  label?: string;
}

export function ProgressBar({
  value,
  max = 100,
  color = "bg-captain-blue",
  bgColor = "bg-gray-200 dark:bg-gray-700",
  height = "h-2",
  showLabel = false,
  label,
}: Props) {
  const pct = clamp((value / max) * 100, 0, 100);
  return (
    <div className="w-full">
      {(showLabel || label) && (
        <div className="mb-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>{label ?? ""}</span>
          <span>{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className={`w-full overflow-hidden rounded-full ${bgColor} ${height}`}>
        <div
          className={`${height} rounded-full transition-all duration-300 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

import * as React from "react";
import { cn } from "@/lib/utils";

interface DataCellProps {
  label: string;
  value: React.ReactNode;
  /** Override value color (e.g., "text-green" or a hex var) */
  valueColor?: string;
  className?: string;
}

export function DataCell({ label, value, valueColor, className }: DataCellProps) {
  return (
    <div className={cn("rounded-[3px] bg-card-elevated px-2 py-1.5", className)}>
      <div className="mb-0.5 text-[11px] text-dim">{label}</div>
      <div
        className={cn("text-sm font-semibold text-foreground", valueColor)}
      >
        {value}
      </div>
    </div>
  );
}

/**
 * Wrapper for DataCell rows that handles shared border-radius:
 * first child rounded-l, last child rounded-r, middle children square.
 */
export function DataCellRow({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "grid gap-px",
        "[&>*]:rounded-none",
        "[&>*:first-child]:rounded-l-[3px]",
        "[&>*:last-child]:rounded-r-[3px]",
        className,
      )}
    >
      {children}
    </div>
  );
}

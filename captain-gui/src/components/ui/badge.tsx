import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-[3px] text-[11px] font-semibold",
  {
    variants: {
      variant: {
        go: "border bg-green-tint border-green-border text-green",
        danger: "border bg-red-tint border-red-border text-red",
        warning: "border bg-amber-tint border-amber-border text-amber",
        info: "border bg-blue-tint border-blue-border text-blue",
        neutral: "bg-neutral-badge-bg text-neutral-badge-text",
      },
      size: {
        default: "px-2 py-px",
        sm: "px-1.5 py-0",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "default",
    },
  },
);

interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size }), className)} {...props} />
  );
}

export { Badge, badgeVariants };

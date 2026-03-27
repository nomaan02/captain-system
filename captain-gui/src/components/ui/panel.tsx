import * as React from "react";
import { ChevronDown } from "lucide-react";
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";
import { cn } from "@/lib/utils";

/* ─── Accent bar color mapping ─── */
const accentColors = {
  green: "#4ade80",
  blue: "#3b82f6",
  gray: "#71717a",
} as const;

type PanelAccent = keyof typeof accentColors;

interface PanelProps {
  /** Title text — rendered at 11px, tracking 0.05em */
  title: string;
  /** 3px accent bar color */
  accent?: PanelAccent;
  /** Right side of title bar (badges, dots, filter tabs) */
  headerRight?: React.ReactNode;
  /** Enable collapse toggle */
  collapsible?: boolean;
  /** Initial collapsed state */
  defaultCollapsed?: boolean;
  /** localStorage key for persisting collapse state */
  storageKey?: string;
  /** Additional classes on outer container */
  className?: string;
  children: React.ReactNode;
}

function getPersistedState(key: string | undefined, fallback: boolean): boolean {
  if (!key) return fallback;
  try {
    const stored = localStorage.getItem(`panel-${key}`);
    if (stored === "true") return true;
    if (stored === "false") return false;
  } catch {
    /* ignore */
  }
  return fallback;
}

function persistState(key: string | undefined, open: boolean) {
  if (!key) return;
  try {
    localStorage.setItem(`panel-${key}`, String(open));
  } catch {
    /* ignore */
  }
}

export function Panel({
  title,
  accent = "gray",
  headerRight,
  collapsible = false,
  defaultCollapsed = false,
  storageKey,
  className,
  children,
}: PanelProps) {
  const [open, setOpen] = React.useState(
    () => !getPersistedState(storageKey, defaultCollapsed),
  );

  const handleOpenChange = React.useCallback(
    (next: boolean) => {
      setOpen(next);
      persistState(storageKey, !next);
    },
    [storageKey],
  );

  const header = (
    <div className="mb-1.5 flex items-center gap-2">
      {/* Accent bar */}
      <span
        className="shrink-0 rounded-[1px]"
        style={{
          width: 3,
          height: 12,
          backgroundColor: accentColors[accent],
        }}
      />

      {/* Title */}
      <span className="text-[11px] tracking-[0.05em] text-muted-foreground">
        {title}
      </span>

      {/* Spacer */}
      <span className="flex-1" />

      {/* Right slot */}
      {headerRight}

      {/* Collapse chevron */}
      {collapsible && (
        <CollapsiblePrimitive.CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex h-4 w-4 items-center justify-center rounded-sm text-ghost transition-colors hover:text-muted-foreground"
          >
            <ChevronDown
              className={cn(
                "h-3 w-3 transition-transform duration-150 ease-out",
                open && "rotate-180",
              )}
            />
          </button>
        </CollapsiblePrimitive.CollapsibleTrigger>
      )}
    </div>
  );

  if (!collapsible) {
    return (
      <div className={className}>
        {header}
        {children}
      </div>
    );
  }

  return (
    <CollapsiblePrimitive.Root open={open} onOpenChange={handleOpenChange} className={className}>
      {header}
      <CollapsiblePrimitive.CollapsibleContent className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
        {children}
      </CollapsiblePrimitive.CollapsibleContent>
    </CollapsiblePrimitive.Root>
  );
}

import { useState, useEffect, useId } from "react";

const ACCENT_COLORS = {
  green: "text-captain-green",
  blue: "text-captain-blue",
  gray: "text-[#94a3b8]",
};

const CollapsiblePanel = ({ title, storageKey, defaultOpen = true, headerRight, accentColor = "green", children }) => {
  const [isOpen, setIsOpen] = useState(() => {
    if (storageKey) {
      const stored = localStorage.getItem(storageKey);
      if (stored !== null) return stored === "true";
    }
    return defaultOpen;
  });

  useEffect(() => {
    if (storageKey) {
      localStorage.setItem(storageKey, String(isOpen));
    }
  }, [isOpen, storageKey]);

  const colorClass = ACCENT_COLORS[accentColor] || ACCENT_COLORS.green;
  const panelId = useId();
  const contentId = `${panelId}-content`;

  return (
    <div className="bg-surface-card border border-border-subtle">
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-controls={contentId}
        className="w-full px-3 py-2 flex items-center justify-between cursor-pointer bg-transparent border-none focus-visible:outline-2 focus-visible:outline-[#3b82f6] focus-visible:outline-offset-[-2px]"
      >
        <span className={`text-sm font-mono uppercase tracking-[1.5px] ${colorClass}`}>
          {title}
        </span>
        <div className="flex items-center gap-2">
          {headerRight}
          <span className="text-[#64748b] text-xs font-mono" aria-hidden="true">
            {isOpen ? "\u25BC" : "\u25B6"}
          </span>
        </div>
      </button>
      {isOpen && (
        <div id={contentId} className="px-3 py-2 border-t border-border-subtle">
          {children}
        </div>
      )}
    </div>
  );
};

export default CollapsiblePanel;

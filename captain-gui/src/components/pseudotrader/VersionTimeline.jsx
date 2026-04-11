import { formatTimestamp } from "../../utils/formatting";

const COMPONENT_COLORS = {
  aim: { bg: "bg-[rgba(59,130,246,0.15)]", border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  ewma: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  kelly: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
};

const DEFAULT_STYLE = { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" };

function getComponentStyle(component) {
  if (!component) return DEFAULT_STYLE;
  const key = component.toLowerCase();
  return COMPONENT_COLORS[key] || DEFAULT_STYLE;
}

function formatState(state) {
  if (!state) return null;
  if (typeof state === "object") {
    const count = Object.keys(state).length;
    return `${count} key${count !== 1 ? "s" : ""}`;
  }
  if (typeof state === "string") {
    try {
      const parsed = JSON.parse(state);
      if (typeof parsed === "object" && parsed !== null) {
        const count = Object.keys(parsed).length;
        return `${count} key${count !== 1 ? "s" : ""}`;
      }
    } catch {
      // not JSON, show as-is
    }
    return state;
  }
  return String(state);
}

const VersionTimeline = ({ versions }) => {
  if (versions.length === 0) {
    return (
      <div className="text-[#64748b] text-xs font-mono py-6 text-center">
        No version history available
      </div>
    );
  }

  const sorted = [...versions].sort((a, b) => new Date(b.ts) - new Date(a.ts));

  return (
    <div className="overflow-y-auto" style={{ maxHeight: 400 }}>
      {sorted.map((v, i) => {
        const style = getComponentStyle(v.component);
        const stateLabel = formatState(v.state);

        return (
          <div
            key={v.version_id || i}
            className="flex items-center gap-3 py-1.5 border-b border-border-subtle last:border-b-0"
          >
            {/* Timestamp */}
            <span className="text-[10px] text-[#94a3b8] font-mono whitespace-nowrap shrink-0">
              {formatTimestamp(v.ts)}
            </span>

            {/* Component badge */}
            <span className={`px-2 py-0.5 text-[10px] font-mono border border-solid uppercase whitespace-nowrap shrink-0 ${style.bg} ${style.border} ${style.text}`}>
              {v.component || "unknown"}
            </span>

            {/* Trigger */}
            <span className="text-[10px] text-white font-mono truncate">
              {v.trigger || "\u2014"}
            </span>

            {/* State */}
            {stateLabel && (
              <span className="text-[10px] text-[#475569] font-mono whitespace-nowrap shrink-0">
                {stateLabel}
              </span>
            )}

            {/* Spacer */}
            <div className="flex-1" />

            {/* Version ID + hash */}
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[9px] text-[#475569] font-mono">
                {v.version_id || "\u2014"}
              </span>
              {v.model_hash && (
                <span className="text-[9px] text-[#374151] font-mono">
                  {v.model_hash.slice(0, 8)}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default VersionTimeline;

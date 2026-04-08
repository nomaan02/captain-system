const DEFAULT_COLOR_MAP = {
  ok: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  active: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  healthy: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  automated: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  automatic: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  error: { bg: "bg-[rgba(239,68,68,0.15)]", border: "border-[rgba(239,68,68,0.3)]", text: "text-[#ef4444]" },
  critical: { bg: "bg-[rgba(239,68,68,0.15)]", border: "border-[rgba(239,68,68,0.3)]", text: "text-[#ef4444]" },
  halted: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  degraded: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  warm_up: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  "admin review": { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  "admin confirm": { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  stale: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  semi_automatic: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
};

const DEFAULT_STYLE = { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" };

const StatusBadge = ({ status, colorMap }) => {
  if (!status) return null;
  const key = status.toLowerCase();
  const map = colorMap || DEFAULT_COLOR_MAP;
  const colors = map[key] || DEFAULT_STYLE;

  return (
    <span className={`px-2 py-0.5 text-[10px] font-mono border border-solid uppercase whitespace-nowrap ${colors.bg} ${colors.border} ${colors.text}`}>
      {status}
    </span>
  );
};

export default StatusBadge;

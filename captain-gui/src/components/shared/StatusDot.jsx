const STATUS_COLORS = {
  ok: "bg-[#00ad74]",
  error: "bg-[#ef4444]",
  halted: "bg-[#f59e0b]",
  unknown: "bg-[#64748b]",
};

const StatusDot = ({ status = "unknown", size = "5.5px", pulse = true, label }) => {
  const color = STATUS_COLORS[status?.toLowerCase()] || STATUS_COLORS.unknown;
  const shouldPulse = pulse && status?.toLowerCase() === "ok";
  const ariaLabel = label || `Status: ${status}`;

  return (
    <div
      role="status"
      aria-label={ariaLabel}
      className={`rounded-full shrink-0 ${color} ${shouldPulse ? "animate-pulse" : ""}`}
      style={{ width: size, height: size }}
    >
      <span className="sr-only">{ariaLabel}</span>
    </div>
  );
};

export default StatusDot;

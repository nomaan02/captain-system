const STATUS_COLORS = {
  ok: "bg-[#00ad74]",
  error: "bg-[#ef4444]",
  halted: "bg-[#f59e0b]",
  unknown: "bg-[#64748b]",
};

const StatusDot = ({ status = "unknown", size = "5.5px", pulse = true }) => {
  const color = STATUS_COLORS[status?.toLowerCase()] || STATUS_COLORS.unknown;
  const shouldPulse = pulse && status?.toLowerCase() === "ok";

  return (
    <div
      className={`rounded-full shrink-0 ${color} ${shouldPulse ? "animate-pulse" : ""}`}
      style={{ width: size, height: size }}
    />
  );
};

export default StatusDot;

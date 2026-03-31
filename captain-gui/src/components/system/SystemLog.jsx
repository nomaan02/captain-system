import { useState, useMemo } from "react";
import PropTypes from "prop-types";
import useNotificationStore from "../../stores/notificationStore";

/* ── Category assignment ─────────────────────────────────────────────── */

const CATEGORY_COLORS = {
  ERROR:  { text: "#ef4444", bg: "rgba(239,68,68,0.15)",  border: "rgba(239,68,68,0.35)" },
  SIGNAL: { text: "#3b82f6", bg: "rgba(59,130,246,0.15)", border: "rgba(59,130,246,0.35)" },
  ORDER:  { text: "#22c55e", bg: "rgba(34,197,94,0.15)",  border: "rgba(34,197,94,0.35)" },
};

const LABEL_MAP  = { ERROR: "ERR", SIGNAL: "SIG", ORDER: "ORD" };
const FILTER_KEY = { ERRORS: "ERROR", SIGNALS: "SIGNAL", ORDERS: "ORDER" };

function getCategory(n) {
  const msg = (n.message ?? "").toLowerCase();
  const src = (n.source ?? "").toLowerCase();

  // Orders first — TP/SL hits arrive from "signal" source but are trade outcomes
  if (msg.includes("tp hit") || msg.includes("sl hit") || msg.includes("filled"))
    return "ORDER";
  if (msg.includes("order") || msg.includes("bracket")) return "ORDER";

  // Errors — high/critical priority, risk blocks, failures
  if (n.priority === "HIGH" || n.priority === "CRITICAL") return "ERROR";
  if (src === "risk") return "ERROR";
  if (msg.includes("error") || msg.includes("rejected") || msg.includes("failed") || msg.includes("blocked"))
    return "ERROR";

  // Signals — signal generation, OR tracking, breakouts
  if (src === "signal" || src === "or_tracker") return "SIGNAL";
  if (msg.includes("signal") || msg.includes("breakout")) return "SIGNAL";

  return null; // general / system entries — no label
}

/* ── Component ───────────────────────────────────────────────────────── */

const SystemLog = ({ className = "" }) => {
  const notifications = useNotificationStore((s) => s.notifications);
  const [activeFilter, setActiveFilter] = useState("ALL");

  const categorized = useMemo(
    () => notifications.map((n) => ({ ...n, _cat: getCategory(n) })),
    [notifications],
  );

  const filtered =
    activeFilter === "ALL"
      ? categorized
      : categorized.filter((n) => n._cat === FILTER_KEY[activeFilter]);

  const filterBtn = (label, key) => {
    const active = activeFilter === key;
    const colors = CATEGORY_COLORS[FILTER_KEY[key]];
    return (
      <button
        data-testid={`syslog-filter-${key.toLowerCase()}`}
        onClick={() => setActiveFilter(key)}
        style={active ? { backgroundColor: colors.bg, borderColor: colors.border } : undefined}
        className={`cursor-pointer border-[#2e4e5a] border-solid border-[0.9px] pt-0 pb-px pl-[5px] pr-[3px] ${active ? "" : "bg-[transparent]"} self-stretch flex-1 flex items-start hover:bg-[rgba(84,115,128,0.09)] hover:border-[#547380] hover:border-solid hover:border-[0.9px] hover:box-border`}
      >
        <div
          className="relative text-[8.6px] leading-[13px] font-medium font-[Inter] text-center"
          style={{ color: active ? colors.text : "#e2e8f0" }}
        >
          {label}
        </div>
      </button>
    );
  };

  return (
    <div
      className={`w-full flex flex-col h-full items-start gap-[1.3px] text-left text-[9.7px] text-[#fff] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="self-stretch flex items-start pt-0 pb-[3px] pl-0 pr-px font-[Inter]">
        <div className="self-stretch flex-1 border-[#2e4e5a] border-solid border-b-[0.9px] flex items-end pt-[4.3px] px-2 pb-1 gap-[24.2px]">
          <div className="flex items-start gap-[8.1px]">
            <div data-testid="syslog-header" className="relative leading-[14.6px]">SYSTEM LOG</div>
            <div className="relative leading-[14.6px] font-['JetBrains_Mono'] text-[#0065f5]">
              TELEGRAM
            </div>
          </div>
          <div className="flex-1 flex items-start gap-[2.2px]">
            <button data-testid="syslog-filter-all" onClick={() => setActiveFilter("ALL")} className={`cursor-pointer border-[#2e4e5a] border-solid border-[0.9px] pt-0 pb-px pl-[5px] pr-[3px] ${activeFilter === "ALL" ? "bg-[#2e4e5a]" : "bg-[transparent]"} self-stretch flex items-start hover:bg-[#547380] hover:border-[#547380] hover:border-solid hover:border-[0.9px] hover:box-border`}>
              <div className="relative text-[8.6px] leading-[13px] font-medium font-[Inter] text-[#e2e8f0] text-center">
                All
              </div>
            </button>
            {filterBtn("Errors", "ERRORS")}
            {filterBtn("Signals", "SIGNALS")}
            {filterBtn("Orders", "ORDERS")}
          </div>
        </div>
      </div>
      <div className="w-full flex flex-col overflow-y-auto flex-1 min-h-0">
        {filtered.length > 0 ? (
          filtered.map((n) => {
            const time = n.timestamp ? new Date(n.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "America/New_York" }) : "—";
            const msg = n.message ?? "";
            const cat = n._cat;
            const catColor = cat ? CATEGORY_COLORS[cat] : null;
            const msgLower = msg.toLowerCase();
            const isError = n.priority === "HIGH" || n.priority === "CRITICAL" || msgLower.includes("error") || msgLower.includes("rejected");
            const isWarning = n.priority === "MEDIUM" || msgLower.includes("timeout") || msgLower.includes("breach") || msgLower.includes("warning") || msgLower.includes("cache miss");
            const isMetric = msgLower.includes("latency") || msgLower.includes("updated") || msgLower.includes("write");
            const msgColor = isError ? "text-[#ef4444]" : isWarning ? "text-[#f59e0b]" : isMetric ? "text-[#06b6d4]" : "text-[#e2e8f0]";
            return (
              <div data-testid="syslog-entry" key={n.notif_id} className="flex items-start py-0 px-2">
                <div className="relative leading-[13.6px]">
                  <span>{`${time} `}</span>
                  {cat && (
                    <span
                      style={{
                        color: catColor.text,
                        backgroundColor: catColor.bg,
                        borderRadius: "2px",
                        padding: "0 3px",
                        marginRight: "4px",
                        fontSize: "8px",
                        fontWeight: 600,
                      }}
                    >
                      {LABEL_MAP[cat]}
                    </span>
                  )}
                  <span className={msgColor}>{msg}</span>
                </div>
              </div>
            );
          })
        ) : (
          <div className="flex items-center justify-center py-4 px-2 text-[9.7px] text-[#64748b]">
            {activeFilter === "ALL" ? "No log entries" : `No ${activeFilter.toLowerCase()} entries`}
          </div>
        )}
      </div>
    </div>
  );
};

SystemLog.propTypes = {
  className: PropTypes.string,
};

export default SystemLog;

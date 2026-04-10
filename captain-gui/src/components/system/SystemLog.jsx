import { useState, useMemo, useEffect, useCallback } from "react";
import PropTypes from "prop-types";
import useNotificationStore from "../../stores/notificationStore";
import api from "../../api/client";

/* ── Category assignment ─────────────────────────────────────────────── */

const CATEGORY_COLORS = {
  ERROR:  { text: "#ef4444", bg: "rgba(239,68,68,0.15)",  border: "rgba(239,68,68,0.35)" },
  SIGNAL: { text: "#3b82f6", bg: "rgba(59,130,246,0.15)", border: "rgba(59,130,246,0.35)" },
  ORDER:  { text: "#22c55e", bg: "rgba(34,197,94,0.15)",  border: "rgba(34,197,94,0.35)" },
};

const LABEL_MAP  = { ERROR: "ERR", SIGNAL: "SIG", ORDER: "ORD" };
const FILTER_KEY = { ERRORS: "ERROR", SIGNALS: "SIGNAL", ORDERS: "ORDER" };

const PRIORITY_COLORS = {
  CRITICAL: "#ef4444",
  HIGH:     "#f59e0b",
  MEDIUM:   "#3b82f6",
  LOW:      "#64748b",
};

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

/* ── Telegram Feed ──────────────────────────────────────────────────── */

const TelegramFeed = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHistory = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.telegramHistory(100);
      setItems(data.items || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory();
    const interval = setInterval(fetchHistory, 30000);
    return () => clearInterval(interval);
  }, [fetchHistory]);

  if (loading && items.length === 0) {
    return (
      <div className="flex items-center justify-center py-4 px-2 text-[11px] text-[#64748b]">
        Loading Telegram history...
      </div>
    );
  }

  if (error && items.length === 0) {
    return (
      <div className="flex items-center justify-center py-4 px-2 text-[11px] text-[#ef4444]">
        {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-4 px-2 text-[11px] text-[#64748b]">
        No Telegram notifications sent yet
      </div>
    );
  }

  return items.map((item) => {
    const time = item.timestamp
      ? new Date(item.timestamp).toLocaleTimeString("en-US", {
          hour: "2-digit", minute: "2-digit", second: "2-digit",
          hour12: false, timeZone: "America/New_York",
        })
      : "--";
    const prioColor = PRIORITY_COLORS[item.priority] || "#64748b";
    return (
      <div key={item.notif_id} className="flex items-start py-0 px-2">
        <div className="relative leading-relaxed">
          <span>{`${time} `}</span>
          <span
            style={{ color: prioColor, backgroundColor: `${prioColor}22` }}
            className="rounded-sm px-[3px] mr-1 text-[10px] font-semibold"
          >
            {item.priority}
          </span>
          <span className="text-[#e2e8f0]">{item.message}</span>
        </div>
      </div>
    );
  });
};

/* ── Component ───────────────────────────────────────────────────────── */

const SystemLog = ({ className = "" }) => {
  const notifications = useNotificationStore((s) => s.notifications);
  const [activeFilter, setActiveFilter] = useState("ALL");
  const [activeView, setActiveView] = useState("log"); // "log" | "telegram"

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
        aria-pressed={active}
        onClick={() => setActiveFilter(key)}
        style={active ? { backgroundColor: colors.bg, borderColor: colors.border } : undefined}
        className={`cursor-pointer border-[#2e4e5a] border-solid border-[0.9px] pt-0 pb-px pl-[5px] pr-[3px] ${active ? "" : "bg-[transparent]"} self-stretch flex-1 flex items-start hover:bg-[rgba(84,115,128,0.09)] hover:border-[#547380] hover:border-solid hover:border-[0.9px] hover:box-border`}
      >
        <div
          className="relative text-[10px] leading-[13px] font-medium font-[Inter] text-center"
          style={{ color: active ? colors.text : "#e2e8f0" }}
        >
          {label}
        </div>
      </button>
    );
  };

  return (
    <div
      className={`w-full flex flex-col h-full items-start gap-[1.3px] text-left text-[11px] text-[#fff] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="self-stretch flex items-start pt-0 pb-[3px] pl-0 pr-px font-[Inter]">
        <div className="self-stretch flex-1 border-[#2e4e5a] border-solid border-b-[0.9px] flex items-end pt-[4.3px] px-2 pb-1 gap-[24.2px]">
          <div
            className="flex items-start gap-[8.1px]"
            role="tablist"
            onKeyDown={(e) => {
              if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                e.preventDefault();
                const next = activeView === "log" ? "telegram" : "log";
                setActiveView(next);
                document.getElementById(`tab-${next}`)?.focus();
              }
            }}
          >
            <button
              data-testid="syslog-header"
              id="tab-log"
              role="tab"
              aria-selected={activeView === "log"}
              aria-controls="tabpanel-content"
              tabIndex={activeView === "log" ? 0 : -1}
              onClick={() => setActiveView("log")}
              className={`cursor-pointer bg-transparent border-none p-0 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[#e2e8f0] ${activeView === "log" ? "text-[#e2e8f0]" : "text-[#64748b]"}`}
            >
              <div className={`relative leading-[14.6px] ${activeView === "log" ? "border-b border-solid border-b-[#e2e8f0]" : "border-b border-solid border-b-transparent"}`}>
                SYSTEM LOG
              </div>
            </button>
            <button
              data-testid="syslog-telegram-tab"
              id="tab-telegram"
              role="tab"
              aria-selected={activeView === "telegram"}
              aria-controls="tabpanel-content"
              tabIndex={activeView === "telegram" ? 0 : -1}
              onClick={() => setActiveView("telegram")}
              className={`cursor-pointer bg-transparent border-none p-0 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[#e2e8f0] ${activeView === "telegram" ? "text-[#0065f5]" : "text-[#0065f580]"}`}
            >
              <div className={`relative leading-[14.6px] font-['JetBrains_Mono'] ${activeView === "telegram" ? "border-b border-solid border-b-[#0065f5]" : "border-b border-solid border-b-transparent"}`}>
                TELEGRAM
              </div>
            </button>
          </div>
          {activeView === "log" && (
            <div className="flex-1 flex items-start gap-[2.2px]">
              <button data-testid="syslog-filter-all" aria-pressed={activeFilter === "ALL"} onClick={() => setActiveFilter("ALL")} className={`cursor-pointer border-[#2e4e5a] border-solid border-[0.9px] pt-0 pb-px pl-[5px] pr-[3px] ${activeFilter === "ALL" ? "bg-[#2e4e5a]" : "bg-[transparent]"} self-stretch flex items-start hover:bg-[#547380] hover:border-[#547380] hover:border-solid hover:border-[0.9px] hover:box-border`}>
                <div className="relative text-[10px] leading-[13px] font-medium font-[Inter] text-[#e2e8f0] text-center">
                  All
                </div>
              </button>
              {filterBtn("Errors", "ERRORS")}
              {filterBtn("Signals", "SIGNALS")}
              {filterBtn("Orders", "ORDERS")}
            </div>
          )}
        </div>
      </div>
      <div role="tabpanel" id="tabpanel-content" aria-labelledby={`tab-${activeView}`} className="w-full flex flex-col overflow-y-auto flex-1 min-h-0">
        {activeView === "telegram" ? (
          <TelegramFeed />
        ) : filtered.length > 0 ? (
          filtered.map((n) => {
            const time = n.timestamp ? new Date(n.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "America/New_York" }) : "--";
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
                <div className="relative leading-relaxed">
                  <span>{`${time} `}</span>
                  {cat && (
                    <span
                      style={{ color: catColor.text, backgroundColor: catColor.bg }}
                      className="rounded-sm px-[3px] mr-1 text-[10px] font-semibold"
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
          <div className="flex items-center justify-center py-4 px-2 text-[11px] text-[#64748b]">
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

import { useEffect, useRef, useMemo, useCallback, useState } from "react";
import useTerminalStore from "../../stores/terminalStore";

const LEVEL_COLORS = {
  ERROR: "#ef4444",
  WARN:  "#f59e0b",
  INFO:  "#e2e8f0",
  DEBUG: "#64748b",
};

function formatTime(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts).toLocaleTimeString("en-US", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false, timeZone: "America/New_York",
  });
}

const GateActivityFeed = ({ maxHeight = "250px" }) => {
  const entries = useTerminalStore((s) => s.entries);
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef(null);
  const bottomRef = useRef(null);

  const gateEntries = useMemo(
    () => entries.filter((e) => e.source === "b3_pseudotrader"),
    [entries],
  );

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [gateEntries, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom !== autoScroll) setAutoScroll(atBottom);
  }, [autoScroll]);

  // Highlight ADOPT/REJECT/CRASH keywords inline with colored spans
  const renderMessage = (msg) => {
    if (!msg) return null;
    const parts = msg.split(/\b(ADOPT|REJECT|CRASH)\b/);
    return parts.map((part, i) => {
      if (part === "ADOPT") return <span key={i} className="text-[#10b981] font-semibold">{part}</span>;
      if (part === "REJECT") return <span key={i} className="text-[#ef4444] font-semibold">{part}</span>;
      if (part === "CRASH") return <span key={i} className="text-[#f59e0b] font-semibold">{part}</span>;
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="flex flex-col" style={{ maxHeight }}>
      <div className="shrink-0 flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <div className="size-[5px] rounded-full bg-captain-green" style={{ boxShadow: "0 0 4px rgba(15,175,122,0.6)" }} />
          <span className="text-[10px] font-mono text-[#94a3b8] uppercase tracking-wider">Live Gate Events</span>
        </div>
        <span className="text-[10px] text-[#64748b] font-mono">{gateEntries.length} events</span>
      </div>

      <div ref={scrollRef} onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-2 py-1 bg-[#050a09] border border-border-subtle font-['JetBrains_Mono'] text-[11px] leading-relaxed">
        {gateEntries.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#4a5568] py-6">
            Waiting for pseudotrader gate events...
          </div>
        ) : (
          gateEntries.map((entry) => (
            <div key={entry._seq} className="whitespace-nowrap">
              <span className="text-[#4a5568]">{formatTime(entry.timestamp)}</span>
              <span style={{ color: LEVEL_COLORS[entry.level] || "#e2e8f0" }}> {renderMessage(entry.message)}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {!autoScroll && gateEntries.length > 0 && (
        <button
          onClick={() => { setAutoScroll(true); scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); }}
          className="cursor-pointer shrink-0 w-full py-[2px] bg-[rgba(6,182,212,0.1)] border-none border-t border-solid border-t-[rgba(6,182,212,0.3)] text-[10px] text-[#06b6d4] font-['JetBrains_Mono'] text-center hover:bg-[rgba(6,182,212,0.15)]">
          {"\u2193"} New events below {"\u2014"} click to resume auto-scroll
        </button>
      )}
    </div>
  );
};

export default GateActivityFeed;

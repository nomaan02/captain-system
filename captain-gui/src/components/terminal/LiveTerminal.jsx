import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import useTerminalStore from "../../stores/terminalStore";

/* ── Constants ──────────────────────────────────────────────────────── */

const PROCESS_COLORS = {
  COMMAND: "#0faf7a",
  ONLINE:  "#06b6d4",
  OFFLINE: "#f59e0b",
};

const PROCESS_ABBREV = {
  COMMAND: "CMD",
  ONLINE:  "ONL",
  OFFLINE: "OFL",
};

const LEVEL_COLORS = {
  ERROR: "#ef4444",
  WARN:  "#f59e0b",
  INFO:  "#e2e8f0",
  DEBUG: "#64748b",
};

const FILTERS = ["ALL", "ONLINE", "OFFLINE", "COMMAND", "ERRORS"];

function formatTime(ts) {
  if (!ts) return "--:--:--";
  return new Date(ts).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "America/New_York",
  });
}

/* ── Component ──────────────────────────────────────────────────────── */

const LiveTerminal = () => {
  const entries = useTerminalStore((s) => s.entries);
  const [filter, setFilter] = useState("ALL");
  const [autoScroll, setAutoScroll] = useState(true);
  const [copyFeedback, setCopyFeedback] = useState(false);
  const scrollRef = useRef(null);
  const bottomRef = useRef(null);

  const filtered = useMemo(() => {
    if (filter === "ALL") return entries;
    if (filter === "ERRORS")
      return entries.filter((e) => e.level === "ERROR" || e.level === "WARN");
    return entries.filter((e) => e.process === filter);
  }, [entries, filter]);

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [filtered, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (atBottom !== autoScroll) setAutoScroll(atBottom);
  }, [autoScroll]);

  const copyClaudeCmd = async () => {
    try {
      await navigator.clipboard.writeText(
        "cd /home/nomaan/captain-system && claude",
      );
      setCopyFeedback(true);
      setTimeout(() => setCopyFeedback(false), 2000);
    } catch {
      /* clipboard API unavailable */
    }
  };

  const resumeScroll = () => {
    setAutoScroll(true);
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  };

  return (
    <div className="h-full flex flex-col bg-surface-card border border-border-subtle">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="shrink-0 px-3 py-[6px] flex items-center justify-between border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <div
            className="size-[6px] rounded-full bg-captain-green"
            style={{ boxShadow: "0 0 4px rgba(15,175,122,0.6)" }}
          />
          <span className="text-[13px] font-['JetBrains_Mono'] uppercase tracking-[1.5px] text-captain-green">
            Live Terminal
          </span>
        </div>

        <div className="flex items-center gap-[3px]">
          {/* Claude Code launcher */}
          <button
            onClick={copyClaudeCmd}
            title={
              copyFeedback
                ? "Copied! Paste in terminal"
                : "Copy Claude Code launch command"
            }
            className="cursor-pointer border border-border-accent bg-transparent hover:bg-[rgba(84,115,128,0.12)] px-[5px] py-0 flex items-center group focus-visible:outline-1 focus-visible:outline-[#3b82f6]"
          >
            <span className="text-[10px] font-['JetBrains_Mono'] text-[#94a3b8] group-hover:text-[#e2e8f0]">
              {copyFeedback ? "\u2713 Copied" : ">_"}
            </span>
          </button>

          <div className="w-px h-3 bg-border-subtle mx-1" />

          {/* Process filters */}
          {FILTERS.map((f) => {
            const active = filter === f;
            let color;
            if (f === "ERRORS") color = "#ef4444";
            else if (f !== "ALL") color = PROCESS_COLORS[f];
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                aria-pressed={active}
                className={`cursor-pointer border border-border-accent px-[5px] py-0 text-[10px] font-medium font-[Inter] hover:bg-[rgba(84,115,128,0.09)] focus-visible:outline-1 focus-visible:outline-[#3b82f6] ${
                  active ? "bg-[rgba(46,78,90,0.5)]" : "bg-transparent"
                }`}
                style={{ color: active && color ? color : "#e2e8f0" }}
              >
                {f === "ERRORS"
                  ? "ERR"
                  : f === "ALL"
                    ? "All"
                    : PROCESS_ABBREV[f]}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Terminal output ─────────────────────────────────────── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-2 py-1 bg-[#050a09] font-['JetBrains_Mono'] text-[11px] leading-relaxed"
      >
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-[#4a5568]">
            {filter === "ALL"
              ? "Waiting for process logs\u2026"
              : `No ${filter.toLowerCase()} entries`}
          </div>
        ) : (
          filtered.map((entry) => (
            <div key={entry._seq} className="whitespace-nowrap">
              <span className="text-[#4a5568]">
                {formatTime(entry.timestamp)}
              </span>
              <span
                style={{
                  color: PROCESS_COLORS[entry.process] || "#64748b",
                }}
              >
                {` [${PROCESS_ABBREV[entry.process] || entry.process}] `}
              </span>
              <span
                style={{
                  color: LEVEL_COLORS[entry.level] || "#e2e8f0",
                }}
              >
                {entry.message}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Resume scroll indicator ────────────────────────────── */}
      {!autoScroll && filtered.length > 0 && (
        <button
          onClick={resumeScroll}
          className="cursor-pointer shrink-0 w-full py-[2px] bg-[rgba(6,182,212,0.1)] border-none border-t border-solid border-t-[rgba(6,182,212,0.3)] text-[10px] text-[#06b6d4] font-['JetBrains_Mono'] text-center hover:bg-[rgba(6,182,212,0.15)] focus-visible:outline-1 focus-visible:outline-[#3b82f6]"
        >
          \u2193 New entries below \u2014 click to resume auto-scroll
        </button>
      )}
    </div>
  );
};

export default LiveTerminal;

import { useState, useRef, useEffect } from "react";
import PropTypes from "prop-types";
import { NavLink } from "react-router-dom";
import useDashboardStore from "../../stores/dashboardStore";
import { formatTime, formatTimeSince } from "../../utils/formatting";
import api from "../../api/client";

const NAV_BASE =
  "px-[10px] py-[6px] text-[10px] leading-[13.7px] font-extralight font-mono cursor-pointer inline-block no-underline focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#00ad74]";

const navClass = ({ isActive }) =>
  isActive
    ? `${NAV_BASE} bg-[#00ad74] border-[#87f0cf] border-solid border-b-[1.6px] text-[#080e0d]`
    : `${NAV_BASE} bg-[rgba(0,173,116,0.23)] text-[#afafaf]`;

const TopBar = ({ className = "" }) => {
  const timestamp = useDashboardStore((s) => s.timestamp);
  const connected = useDashboardStore((s) => s.connected);
  const apiStatus = useDashboardStore((s) => s.apiStatus);
  const pipelineStage = useDashboardStore((s) => s.pipelineStage);
  const serviceHealth = useDashboardStore((s) => s.serviceHealth);
  const selectedAccount = useDashboardStore((s) => s.selectedAccount);
  const accounts = useDashboardStore((s) => s.accounts);
  const setSelectedAccount = useDashboardStore((s) => s.setSelectedAccount);

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [pullState, setPullState] = useState("idle"); // idle | pulling | success | rebuilding | error
  const [pullMsg, setPullMsg] = useState("");
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const dropdownRef = useRef(null);
  const triggerRef = useRef(null);
  const optionRefs = useRef([]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Focus management for account dropdown
  useEffect(() => {
    if (dropdownOpen && accounts.length > 0) {
      const idx = accounts.findIndex((a) => a.id === selectedAccount);
      const target = idx >= 0 ? idx : 0;
      setFocusedIndex(target);
      requestAnimationFrame(() => optionRefs.current[target]?.focus());
    }
  }, [dropdownOpen, accounts, selectedAccount]);

  const handleDropdownKeyDown = (e) => {
    switch (e.key) {
      case "Escape":
        e.preventDefault();
        setDropdownOpen(false);
        triggerRef.current?.focus();
        break;
      case "ArrowDown":
        e.preventDefault();
        setFocusedIndex((prev) => {
          const next = Math.min(prev + 1, accounts.length - 1);
          requestAnimationFrame(() => optionRefs.current[next]?.focus());
          return next;
        });
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusedIndex((prev) => {
          const next = Math.max(prev - 1, 0);
          requestAnimationFrame(() => optionRefs.current[next]?.focus());
          return next;
        });
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && accounts[focusedIndex]) {
          setSelectedAccount(accounts[focusedIndex].id);
          setDropdownOpen(false);
          triggerRef.current?.focus();
        }
        break;
      default:
        break;
    }
  };

  const handleGitPull = async () => {
    if (pullState === "pulling" || pullState === "rebuilding") return;
    setPullState("pulling");
    setPullMsg("");
    try {
      const res = await api.gitPull();
      if (res.status === "up_to_date") {
        setPullState("success");
        setPullMsg("Already up to date");
        setTimeout(() => setPullState("idle"), 4000);
      } else if (res.status === "success") {
        if (res.rebuild_started) {
          setPullState("rebuilding");
          setPullMsg(`${res.changed_files?.length || 0} files changed — rebuilding...`);
          // Containers will restart; page will reconnect automatically
        } else {
          setPullState("success");
          setPullMsg(`Pulled ${res.changed_files?.length || 0} file(s) — live`);
          setTimeout(() => setPullState("idle"), 5000);
        }
      } else {
        setPullState("error");
        setPullMsg(res.message || "Pull failed");
        setTimeout(() => setPullState("idle"), 6000);
      }
    } catch (err) {
      setPullState("error");
      setPullMsg("Network error");
      setTimeout(() => setPullState("idle"), 5000);
    }
  };

  return (
    <div
      className={`w-full bg-[#080e0d] text-left text-[9.1px] text-[#fff] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="w-full h-9 bg-[#080e0d] border-[#2e4e5a] border-solid border-b flex items-center px-3 gap-2">
        {/* Clock */}
        <div className="flex items-baseline gap-[4px] shrink-0">
          <div data-testid="topbar-clock" className="relative tracking-[0.91px] leading-[19.2px] text-[12.8px] text-[#e2e8f0] font-[Inter]">
            {formatTime(timestamp)}
          </div>
          <div className="text-[10.1px] text-[#fff] leading-[15.1px]">ET</div>
        </div>

        {/* Nav tabs */}
        <div className="flex items-center gap-1 ml-2">
          <NavLink to="/" end className={navClass}>Dashboard</NavLink>
          <NavLink to="/system" className={navClass}>System</NavLink>
          <NavLink to="/processes" className={navClass}>Processes</NavLink>
          <NavLink to="/history" className={navClass}>History</NavLink>
          <NavLink to="/reports" className={navClass}>Reports</NavLink>
          <NavLink to="/replay" className={navClass}>Replay</NavLink>
          <NavLink to="/settings" className={navClass}>Settings</NavLink>
        </div>

        {/* Center spacer */}
        <div className="flex-1" />

        {/* Account selector dropdown — centered between nav and status */}
        <div className="relative shrink-0" ref={dropdownRef}>
          <button
            ref={triggerRef}
            data-testid="topbar-account-selector"
            data-status={dropdownOpen ? "open" : "closed"}
            onClick={() => setDropdownOpen(!dropdownOpen)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown" && !dropdownOpen) {
                e.preventDefault();
                setDropdownOpen(true);
              } else if (e.key === "Escape" && dropdownOpen) {
                e.preventDefault();
                setDropdownOpen(false);
              }
            }}
            aria-haspopup="listbox"
            aria-expanded={dropdownOpen}
            aria-label="Select account"
            className="cursor-pointer bg-[#111827] border-[#2e4e5a] border-solid border flex items-center gap-2 py-[2px] pl-[10px] pr-[7px] h-[32px] hover:bg-[#1a2332] hover:border-[#547380] focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#00ad74]"
          >
            <span className="text-[8.6px] leading-[13.7px] font-extralight text-[#e2e8f0]">
              {selectedAccount}
            </span>
            <span aria-hidden="true" className={`text-[8px] text-white/40 leading-none transition-transform ${dropdownOpen ? "rotate-180" : ""}`}>
              ▼
            </span>
          </button>

          {/* Dropdown menu */}
          {dropdownOpen && (
            <div
              data-testid="topbar-account-dropdown"
              role="listbox"
              aria-label="Accounts"
              onKeyDown={handleDropdownKeyDown}
              className="absolute top-[34px] left-0 z-50 bg-[#111827] border border-solid border-[#2e4e5a] shadow-lg min-w-full"
            >
              {accounts.map((acc, i) => (
                <button
                  key={acc.id}
                  ref={(el) => { optionRefs.current[i] = el; }}
                  role="option"
                  aria-selected={acc.id === selectedAccount}
                  tabIndex={-1}
                  onClick={() => {
                    setSelectedAccount(acc.id);
                    setDropdownOpen(false);
                    triggerRef.current?.focus();
                  }}
                  className={`w-full text-left cursor-pointer border-none px-[10px] py-[5px] text-[8.6px] leading-[13.7px] font-extralight font-mono flex items-center justify-between gap-3 focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#00ad74] ${
                    acc.id === selectedAccount
                      ? "bg-[#0d2818] text-[#10b981]"
                      : "bg-[#111827] text-[#e2e8f0] hover:bg-[#1a2332]"
                  }`}
                >
                  <span>{acc.id}</span>
                  <span className={`text-[7px] uppercase tracking-wider ${
                    acc.type === "live" ? "text-[#f59e0b]" : "text-[#64748b]"
                  }`}>
                    {acc.label}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* TRADING badge */}
        <div data-testid="topbar-trading-badge" className={`shrink-0 border-solid border flex items-center py-0 px-1.5 ${
          !connected ? "border-[#ef4444] bg-[#300b0b]" :
          pipelineStage === "EXECUTED" ? "border-[#55d869] bg-[#11300b]" :
          "border-[#f59e0b] bg-[#302200]"
        }`}>
          <span className={`text-[8.8px] leading-[13.2px] ${
            !connected ? "text-[#ef4444]" :
            pipelineStage === "EXECUTED" ? "text-[#0faf7a]" :
            "text-[#f59e0b]"
          }`}>{!connected ? "OFFLINE" : pipelineStage === "EXECUTED" ? "TRADING" : "MONITORING"}</span>
        </div>

        {/* Git Pull button */}
        <button
          data-testid="topbar-git-pull"
          onClick={handleGitPull}
          disabled={pullState === "pulling" || pullState === "rebuilding"}
          className={`shrink-0 border border-solid flex items-center gap-[4px] py-0 px-[6px] h-[32px] cursor-pointer text-[8.2px] font-mono transition-colors focus-visible:outline focus-visible:outline-1 focus-visible:outline-[#00ad74] ${
            pullState === "pulling" || pullState === "rebuilding"
              ? "bg-[rgba(6,182,212,0.15)] border-[rgba(6,182,212,0.3)] text-[#06b6d4] cursor-wait"
              : pullState === "success"
                ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                : pullState === "error"
                  ? "bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"
                  : "bg-[#111827] border-[#2e4e5a] text-[#94a3b8] hover:text-[#e2e8f0] hover:border-[#547380]"
          }`}
          title={pullMsg || "Pull latest code from GitHub and rebuild"}
        >
          {pullState === "pulling" && <span aria-hidden="true" className="animate-spin">&#8635;</span>}
          {pullState === "rebuilding" && <span aria-hidden="true" className="animate-pulse">&#9881;</span>}
          {pullState === "success" && <span aria-hidden="true">&#10003;</span>}
          {pullState === "error" && <span aria-hidden="true">&#10007;</span>}
          {pullState === "idle" && <span aria-hidden="true">&#8595;</span>}
          <span>
            {pullState === "pulling" ? "Pulling..." :
             pullState === "rebuilding" ? "Rebuilding..." :
             pullState === "success" ? pullMsg :
             pullState === "error" ? pullMsg :
             "Git Pull"}
          </span>
        </button>

        {/* Status dots */}
        <div data-testid="health-bar" className="flex items-center gap-[6px] shrink-0 ml-2">
          <div data-testid="api-status" data-status={apiStatus?.api_authenticated ? "ok" : "error"} className={`w-2 h-2 rounded-full ${apiStatus?.api_authenticated ? "bg-[#00ad74]" : "bg-[#ef4444]"}`}>
            <span className="sr-only">API: {apiStatus?.api_authenticated ? "connected" : "disconnected"}</span>
          </div>
          <span aria-hidden="true" className="text-[9.1px] leading-[13.7px]">API</span>

          <div data-testid="ws-status" data-status={connected ? "connected" : "disconnected"} className={`w-2 h-2 rounded-full ${connected ? "bg-[#00ad74]" : "bg-[#ef4444]"}`}>
            <span className="sr-only">WebSocket: {connected ? "connected" : "disconnected"}</span>
          </div>
          <span aria-hidden="true" className="text-[9.1px] leading-[13.7px]">WS</span>

          <div data-testid="qdb-status" data-status={serviceHealth.questdb} className={`w-2 h-2 rounded-full ${serviceHealth.questdb === "ok" ? "bg-[#00ad74]" : serviceHealth.questdb === "error" ? "bg-[#ef4444]" : "bg-[#64748b]"}`}>
            <span className="sr-only">QuestDB: {serviceHealth.questdb || "unknown"}</span>
          </div>
          <span aria-hidden="true" className="text-[9.1px] leading-[13.7px]">QDB</span>

          <div data-testid="redis-status" data-status={serviceHealth.redis} className={`w-2 h-2 rounded-full ${serviceHealth.redis === "ok" ? "bg-[#00ad74]" : serviceHealth.redis === "error" ? "bg-[#ef4444]" : "bg-[#64748b]"}`}>
            <span className="sr-only">Redis: {serviceHealth.redis || "unknown"}</span>
          </div>
          <span aria-hidden="true" className="text-[9.1px] leading-[13.7px]">Redis</span>

          <span data-testid="last-tick-timestamp" className="text-[10px] leading-[13.7px] ml-1 text-[#64748b]">Last tick: {timestamp ? `${formatTimeSince(timestamp)} ago` : "—"}</span>
        </div>
      </div>
    </div>
  );
};

TopBar.propTypes = {
  className: PropTypes.string,
};

export default TopBar;

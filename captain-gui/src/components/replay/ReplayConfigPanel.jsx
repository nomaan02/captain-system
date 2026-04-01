import { useState } from "react";
import useReplayStore from "../../stores/replayStore";
import api from "../../api/client";

const SESSIONS = ["NY", "LONDON", "APAC", "NY_PRE"];
const RISK_GOALS = ["PASS_EVAL", "GROW_CAPITAL", "PRESERVE_CAPITAL"];
const SPEED_OPTIONS = [1, 10, 50, 100];

const Label = ({ children }) => (
  <label className="text-[8px] uppercase tracking-[0.8px] leading-[10px] text-[#64748b] font-mono">{children}</label>
);

const NumberInput = ({ value, onChange, step = 1, min, max, testId, disabled = false }) => (
  <input
    data-testid={testId}
    type="number"
    value={value}
    step={step}
    min={min}
    max={max}
    disabled={disabled}
    onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
    className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed"
  />
);

const ReplayConfigPanel = () => {
  const config = useReplayStore((s) => s.config);
  const setConfig = useReplayStore((s) => s.setConfig);
  const speed = useReplayStore((s) => s.speed);
  const setSpeed = useReplayStore((s) => s.setSpeed);
  const status = useReplayStore((s) => s.status);
  const presets = useReplayStore((s) => s.presets);
  const reset = useReplayStore((s) => s.reset);

  const [presetName, setPresetName] = useState("");
  const [saving, setSaving] = useState(false);

  const isRunning = status === "running" || status === "paused";

  const handleRun = async () => {
    useReplayStore.getState().reset();
    // Map camelCase frontend keys to snake_case backend keys
    const overrides = {
      user_capital: config.capital,
      budget_divisor: config.budgetDivisor,
      risk_goal: config.riskGoal,
      max_positions: config.maxPositions,
      max_contracts: config.maxContracts,
      tp_multiple: config.tpMultiple,
      sl_multiple: config.slMultiple,
      cb_enabled: config.cbEnabled,
      aim_enabled: config.aimEnabled,
      mdd_limit: config.mddLimit,
      mll_limit: config.mllLimit,
    };
    try {
      if (config.mode === "period") {
        if (!config.dateFrom || !config.dateTo) return;
        if (config.dateFrom > config.dateTo) return;
        const res = await api.replayBatchStart(
          config.dateFrom, config.dateTo, config.sessions, overrides, speed
        );
        if (res?.replay_id) {
          useReplayStore.getState().handleWsMessage({
            type: "batch_started",
            replay_id: res.replay_id,
            total_days: 0,
          });
        }
      } else {
        const res = await api.replayStart(config.date, config.sessions, overrides, speed);
        if (res?.replay_id) {
          useReplayStore.getState().handleWsMessage({ type: "replay_started", replay_id: res.replay_id });
        }
      }
    } catch (err) {
      console.error("Replay start failed:", err);
    }
  };

  const handleResetToLive = () => {
    reset();
    setConfig({
      mode: "single",
      date: new Date().toISOString().slice(0, 10),
      dateFrom: "",
      dateTo: "",
      sessions: ["NY", "LONDON", "APAC", "NY_PRE"],
      capital: 150000,
      budgetDivisor: 20,
      riskGoal: "PASS_EVAL",
      maxPositions: 5,
      maxContracts: 15,
      tpMultiple: 0.70,
      slMultiple: 0.35,
      cbEnabled: true,
      mddLimit: 4500,
      mllLimit: 2250,
    });
  };

  const handleLoadPreset = (preset) => {
    if (preset?.config) {
      setConfig(preset.config);
    }
  };

  const handleSavePreset = async () => {
    if (!presetName.trim()) return;
    setSaving(true);
    try {
      await api.replayPresetSave(presetName.trim(), config);
      const data = await api.replayPresets();
      useReplayStore.getState().setPresets(data.presets || data || []);
      setPresetName("");
    } catch (err) {
      console.error("Preset save failed:", err);
    }
    setSaving(false);
  };

  return (
    <div data-testid="replay-config-panel" className="p-3 space-y-3">
      {/* Section: Replay Mode */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Replay Mode</div>
        <div className="flex gap-1">
          {["single", "period"].map((m) => (
            <button
              key={m}
              data-testid={`replay-mode-${m}`}
              onClick={() => setConfig({ mode: m })}
              disabled={isRunning}
              className={`flex-1 py-[3px] text-[9px] font-mono border border-solid cursor-pointer transition-colors ${
                config.mode === m
                  ? "bg-[rgba(15,175,122,0.2)] border-[rgba(15,175,122,0.4)] text-[#0faf7a]"
                  : "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#94a3b8]"
              }`}
            >
              {m === "single" ? "Single Day" : "Period"}
            </button>
          ))}
        </div>
      </div>

      {/* Section: Date & Sessions */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Session Config</div>

        {config.mode === "single" ? (
          <div>
            <Label>Date</Label>
            <input
              data-testid="replay-config-date"
              type="date"
              value={config.date}
              onChange={(e) => setConfig({ date: e.target.value })}
              disabled={isRunning}
              className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
            />
          </div>
        ) : (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label>From</Label>
                <input
                  data-testid="replay-config-date-from"
                  type="date"
                  value={config.dateFrom}
                  onChange={(e) => setConfig({ dateFrom: e.target.value })}
                  disabled={isRunning}
                  className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
                />
              </div>
              <div>
                <Label>To</Label>
                <input
                  data-testid="replay-config-date-to"
                  type="date"
                  value={config.dateTo}
                  onChange={(e) => setConfig({ dateTo: e.target.value })}
                  disabled={isRunning}
                  className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
                />
              </div>
            </div>
            {config.dateFrom && config.dateTo && config.dateFrom <= config.dateTo && (
              <div className="text-[8px] text-[#64748b] font-mono text-center">
                {(() => {
                  let count = 0;
                  const d = new Date(config.dateFrom);
                  const end = new Date(config.dateTo);
                  while (d <= end) {
                    if (d.getDay() !== 0 && d.getDay() !== 6) count++;
                    d.setDate(d.getDate() + 1);
                  }
                  return `${count} weekday${count !== 1 ? "s" : ""}`;
                })()}
              </div>
            )}
          </div>
        )}

        <div>
          <Label>Sessions</Label>
          <div className="flex gap-2 mt-1">
            {SESSIONS.map((s) => (
              <label key={s} className="flex items-center gap-1 text-[9px] font-mono text-[#e2e8f0] cursor-pointer select-none">
                <input
                  type="checkbox"
                  data-testid={`replay-session-${s}`}
                  checked={(config.sessions || []).includes(s)}
                  disabled={isRunning}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...(config.sessions || []), s]
                      : (config.sessions || []).filter((x) => x !== s);
                    if (next.length > 0) setConfig({ sessions: next });
                  }}
                  className="accent-[#0faf7a]"
                />
                {s}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Section: Capital */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Capital & Risk</div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label>Capital ($)</Label>
            <NumberInput testId="replay-config-capital" value={config.capital} onChange={(v) => setConfig({ capital: v })} step={1000} min={0} disabled={isRunning} />
          </div>
          <div>
            <Label>Budget Divisor</Label>
            <NumberInput testId="replay-config-budget-divisor" value={config.budgetDivisor} onChange={(v) => setConfig({ budgetDivisor: v })} min={1} disabled={isRunning} />
          </div>
          <div>
            <Label>MDD Limit ($)</Label>
            <NumberInput testId="replay-config-mdd" value={config.mddLimit} onChange={(v) => setConfig({ mddLimit: v })} step={100} min={0} disabled={isRunning} />
          </div>
          <div>
            <Label>MLL Limit ($)</Label>
            <NumberInput testId="replay-config-mll" value={config.mllLimit} onChange={(v) => setConfig({ mllLimit: v })} step={100} min={0} disabled={isRunning} />
          </div>
        </div>

        <div>
          <Label>Risk Goal</Label>
          <select
            data-testid="replay-config-risk-goal"
            value={config.riskGoal}
            onChange={(e) => setConfig({ riskGoal: e.target.value })}
            disabled={isRunning}
            className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
          >
            {RISK_GOALS.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
      </div>

      {/* Section: Position Sizing */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Position Sizing</div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label>Max Positions</Label>
            <NumberInput testId="replay-config-max-positions" value={config.maxPositions} onChange={(v) => setConfig({ maxPositions: v })} min={1} max={20} disabled={isRunning} />
          </div>
          <div>
            <Label>Max Contracts</Label>
            <NumberInput testId="replay-config-max-contracts" value={config.maxContracts} onChange={(v) => setConfig({ maxContracts: v })} min={1} max={100} disabled={isRunning} />
          </div>
          <div>
            <Label>TP Multiple</Label>
            <NumberInput testId="replay-config-tp" value={config.tpMultiple} onChange={(v) => setConfig({ tpMultiple: v })} step={0.05} min={0} max={5} disabled={isRunning} />
          </div>
          <div>
            <Label>SL Multiple</Label>
            <NumberInput testId="replay-config-sl" value={config.slMultiple} onChange={(v) => setConfig({ slMultiple: v })} step={0.05} min={0} max={5} disabled={isRunning} />
          </div>
        </div>

        {/* CB Toggle */}
        <div className="flex items-center justify-between">
          <Label>CB L1 Enabled</Label>
          <button
            data-testid="replay-config-cb-toggle"
            onClick={() => setConfig({ cbEnabled: !config.cbEnabled })}
            disabled={isRunning}
            className="cursor-pointer border-none bg-transparent p-0"
            role="switch"
            aria-checked={config.cbEnabled}
          >
            <div className={`h-[16px] w-[32px] relative rounded-full transition-colors ${config.cbEnabled ? "bg-[#10b981]" : "bg-[#374151]"}`}>
              <div className={`absolute top-[2px] rounded-full bg-[#fff] w-[12px] h-[12px] transition-all ${config.cbEnabled ? "left-[18px]" : "left-[2px]"}`} />
            </div>
          </button>
        </div>

        {/* AIM Toggle */}
        <div className="flex items-center justify-between">
          <Label>AIM Scoring</Label>
          <button
            data-testid="replay-config-aim-toggle"
            onClick={() => setConfig({ aimEnabled: !config.aimEnabled })}
            disabled={isRunning}
            className="cursor-pointer border-none bg-transparent p-0"
            role="switch"
            aria-checked={config.aimEnabled}
          >
            <div className={`h-[16px] w-[32px] relative rounded-full transition-colors ${config.aimEnabled ? "bg-[#10b981]" : "bg-[#374151]"}`}>
              <div className={`absolute top-[2px] rounded-full bg-[#fff] w-[12px] h-[12px] transition-all ${config.aimEnabled ? "left-[18px]" : "left-[2px]"}`} />
            </div>
          </button>
        </div>
      </div>

      {/* Section: Speed */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Playback Speed</div>
        <div className="flex gap-1">
          {SPEED_OPTIONS.map((s) => (
            <button
              key={s}
              data-testid={`replay-speed-${s}`}
              onClick={() => setSpeed(s)}
              className={`flex-1 py-[3px] text-[9px] font-mono border border-solid cursor-pointer transition-colors ${
                speed === s
                  ? "bg-[rgba(6,182,212,0.2)] border-[rgba(6,182,212,0.4)] text-[#06b6d4]"
                  : "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#94a3b8]"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      {/* Section: Presets */}
      <div className="space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono border-b border-[#1e293b] pb-1">Presets</div>
        {presets.length > 0 && (
          <select
            data-testid="replay-preset-select"
            onChange={(e) => {
              const p = presets.find((pr) => pr.name === e.target.value);
              if (p) handleLoadPreset(p);
            }}
            className="w-full bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
          >
            <option value="">Load preset...</option>
            {presets.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
        )}
        <div className="flex gap-1">
          <input
            data-testid="replay-preset-name"
            type="text"
            placeholder="Preset name"
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            className="flex-1 bg-[#111827] border border-solid border-[#1e293b] text-[10px] text-[#e2e8f0] font-mono px-2 py-[3px] focus:border-[#0faf7a] focus:outline-none"
          />
          <button
            data-testid="replay-preset-save"
            onClick={handleSavePreset}
            disabled={saving || !presetName.trim()}
            className="px-2 py-[3px] text-[9px] font-mono border border-solid bg-[#111827] border-[#1e293b] text-[#64748b] cursor-pointer hover:text-[#e2e8f0] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? "..." : "Save"}
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="space-y-2 pt-2 border-t border-[#1e293b]">
        <button
          data-testid="replay-run-btn"
          onClick={handleRun}
          disabled={isRunning}
          className={`w-full py-[6px] text-[11px] font-mono font-semibold tracking-[0.5px] border border-solid cursor-pointer transition-colors ${
            isRunning
              ? "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b] cursor-not-allowed"
              : "bg-[#0faf7a] border-[#0faf7a] text-[#080e0d] hover:bg-[#10b981]"
          }`}
        >
          {isRunning ? "RUNNING..." : "RUN REPLAY"}
        </button>
        <button
          data-testid="replay-reset-btn"
          onClick={handleResetToLive}
          disabled={isRunning}
          className="w-full py-[5px] text-[10px] font-mono border border-solid bg-[#111827] border-[#1e293b] text-[#64748b] cursor-pointer hover:text-[#e2e8f0] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Reset to Live
        </button>
      </div>
    </div>
  );
};

export default ReplayConfigPanel;

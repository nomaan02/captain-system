import useReplayStore from "../../stores/replayStore";
import api from "../../api/client";

const SPEED_OPTIONS = [1, 10, 50, 100];

const PlaybackControls = () => {
  const status = useReplayStore((s) => s.status);
  const speed = useReplayStore((s) => s.speed);
  const setSpeed = useReplayStore((s) => s.setSpeed);
  const progress = useReplayStore((s) => s.progress);
  const currentAsset = useReplayStore((s) => s.currentAsset);
  const batchStatus = useReplayStore((s) => s.batchStatus);
  const batchCurrentDay = useReplayStore((s) => s.batchCurrentDay);
  const batchCompletedDays = useReplayStore((s) => s.batchCompletedDays);
  const batchTotalDays = useReplayStore((s) => s.batchTotalDays);
  const batchProgress = useReplayStore((s) => s.batchProgress);

  const isBatch = batchStatus !== "idle";

  const isRunning = status === "running";
  const isPaused = status === "paused";
  const isActive = isRunning || isPaused;

  const handlePlayPause = async () => {
    if (isRunning) {
      try { await api.replayControl("pause"); } catch (e) { console.error(e); }
    } else if (isPaused) {
      try { await api.replayControl("resume"); } catch (e) { console.error(e); }
    }
  };

  const handleSkip = async () => {
    try { await api.replayControl("skip"); } catch (e) { console.error(e); }
  };

  const handleSpeedChange = async (newSpeed) => {
    setSpeed(newSpeed);
    if (isActive) {
      try { await api.replayControl("speed", newSpeed); } catch (e) { console.error(e); }
    }
  };

  if (status === "idle") return null;

  return (
    <div
      data-testid="playback-controls"
      className="flex items-center gap-3 px-3 py-[5px] bg-[#080e0d] border-b border-[#1e293b] font-mono"
    >
      {/* Play/Pause button */}
      <button
        data-testid="playback-play-pause"
        onClick={handlePlayPause}
        disabled={!isActive}
        className={`w-[24px] h-[24px] flex items-center justify-center border border-solid cursor-pointer transition-colors ${
          isActive
            ? "bg-[rgba(6,182,212,0.15)] border-[rgba(6,182,212,0.3)] text-[#06b6d4] hover:bg-[rgba(6,182,212,0.25)]"
            : "bg-[#111827] border-[#1e293b] text-[#374151] cursor-not-allowed"
        }`}
      >
        <span className="text-[12px] leading-none">{isRunning ? "\u23F8" : "\u25B6"}</span>
      </button>

      {/* Skip button */}
      <button
        data-testid="playback-skip"
        onClick={handleSkip}
        disabled={!isActive}
        className={`w-[24px] h-[24px] flex items-center justify-center border border-solid cursor-pointer transition-colors ${
          isActive
            ? "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#e2e8f0]"
            : "bg-[#111827] border-[#1e293b] text-[#374151] cursor-not-allowed"
        }`}
      >
        <span className="text-[10px] leading-none">{"\u23ED"}</span>
      </button>

      {/* Speed pills */}
      <div className="flex gap-[2px]">
        {SPEED_OPTIONS.map((s) => (
          <button
            key={s}
            data-testid={`playback-speed-${s}`}
            onClick={() => handleSpeedChange(s)}
            className={`px-[5px] py-[2px] text-[8px] font-mono border border-solid cursor-pointer transition-colors ${
              speed === s
                ? "bg-[rgba(6,182,212,0.2)] border-[rgba(6,182,212,0.4)] text-[#06b6d4]"
                : "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#94a3b8]"
            }`}
          >
            {s}x
          </button>
        ))}
      </div>

      {/* Progress */}
      <div className="flex-1 flex items-center gap-2">
        <div className="flex-1 h-[3px] bg-[#1e293b] rounded-full overflow-hidden">
          <div
            data-testid="playback-progress-bar"
            className="h-full bg-[#06b6d4] transition-all duration-300"
            style={{ width: `${isBatch ? batchProgress : progress}%` }}
          />
        </div>
        <span data-testid="playback-progress-pct" className="text-[9px] text-[#64748b] min-w-[28px] text-right">
          {isBatch ? batchProgress : progress}%
        </span>
      </div>

      {/* Batch day indicator */}
      {isBatch && batchCurrentDay && (
        <span className="text-[9px] text-[#f59e0b] font-mono">
          Day {batchCompletedDays}/{batchTotalDays}
        </span>
      )}

      {/* Current asset */}
      {currentAsset && (
        <span data-testid="playback-current-asset" className="text-[9px] text-[#06b6d4]">
          {currentAsset}
        </span>
      )}

      {/* Status badge */}
      <span
        data-testid="playback-status"
        className={`px-[5px] py-[1px] text-[7px] uppercase tracking-[0.5px] border border-solid ${
          isRunning
            ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
            : isPaused
              ? "bg-[rgba(245,158,11,0.15)] border-[rgba(245,158,11,0.3)] text-[#f59e0b]"
              : "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]"
        }`}
      >
        {status}
      </span>
    </div>
  );
};

export default PlaybackControls;

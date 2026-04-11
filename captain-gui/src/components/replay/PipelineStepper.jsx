import useReplayStore from "../../stores/replayStore";

const PIPELINE_STAGES = [
  { id: "B1", label: "Data Ingest" },
  { id: "B2", label: "Regime" },
  { id: "B3", label: "AIM Score" },
  { id: "B4", label: "Kelly Size" },
  { id: "B5", label: "Selection" },
  { id: "B5C", label: "Circuit Brk" },
  { id: "B6", label: "Signal" },
];

const STATUS_STYLES = {
  pending: {
    circle: "bg-[#374151] border-[#64748b]",
    text: "text-[#64748b]",
  },
  running: {
    circle: "bg-[rgba(6,182,212,0.3)] border-[#06b6d4] animate-pulse",
    text: "text-[#06b6d4]",
  },
  complete: {
    circle: "bg-[rgba(16,185,129,0.3)] border-[#10b981]",
    text: "text-[#10b981]",
  },
  error: {
    circle: "bg-[rgba(239,68,68,0.3)] border-[#ef4444]",
    text: "text-[#ef4444]",
  },
};

const PipelineStepper = () => {
  const pipelineStages = useReplayStore((s) => s.pipelineStages);
  const expandedStage = useReplayStore((s) => s.expandedStage);
  const setExpandedStage = useReplayStore((s) => s.setExpandedStage);
  const status = useReplayStore((s) => s.status);

  const getStageStatus = (stageId) => {
    // B1 is complete if B1 or B1_AUTH has data
    if (stageId === "B1" && (pipelineStages.B1 || pipelineStages.B1_AUTH)) return "complete";
    const stage = pipelineStages[stageId];
    if (!stage) return status === "running" ? "pending" : "pending";
    return stage.status || "complete";
  };

  const getStageSummary = (stageId) => {
    const stage = pipelineStages[stageId];
    if (!stage) return null;
    if (stage.summary) return stage.summary;
    // Generate summary from data
    const d = stage.data;
    if (!d) return "Done";
    if (stageId === "B1" || stageId === "B1_AUTH") return `${d.contracts_resolved || d.strategies_loaded || "?"} assets`;
    if (stageId === "B4") return `${d.contracts ?? "?"} cts`;
    if (stageId === "B5") {
      const sel = d.selected?.length ?? d.trades_taken ?? "?";
      const exc = d.excluded?.length ?? "0";
      return `${sel} taken, ${exc} excl`;
    }
    return "Done";
  };

  return (
    <div data-testid="pipeline-stepper" className="px-4 py-3">
      <div className="text-[11px] uppercase tracking-[1px] text-[#0faf7a] font-mono mb-3 text-center">Pipeline</div>

      {/* Horizontal stepper — enlarged 50% */}
      <div className="flex items-start justify-center gap-0">
        {PIPELINE_STAGES.map((stage, idx) => {
          const stageStatus = getStageStatus(stage.id);
          const styles = STATUS_STYLES[stageStatus] || STATUS_STYLES.pending;
          const isExpanded = expandedStage === stage.id;
          const hasData = !!pipelineStages[stage.id] || (stage.id === "B1" && pipelineStages.B1_AUTH);
          const summary = getStageSummary(stage.id);

          return (
            <div key={stage.id} className="flex items-start">
              {/* Stage node */}
              <button
                data-testid={`pipeline-stage-${stage.id}`}
                data-status={stageStatus}
                onClick={() => setExpandedStage(stage.id)}
                aria-expanded={isExpanded}
                className={`flex flex-col items-center gap-[4px] px-[10px] py-2 border-none bg-transparent cursor-pointer min-w-[72px] transition-colors ${
                  hasData ? "hover:bg-[rgba(255,255,255,0.05)]" : ""
                } ${isExpanded ? "bg-[rgba(6,182,212,0.1)]" : ""}`}
              >
                {/* Circle indicator */}
                <div className={`size-[20px] rounded-full border-[1.5px] border-solid ${styles.circle} flex items-center justify-center`}>
                  {stageStatus === "complete" && (
                    <span className="text-[10px] text-[#10b981]">&#10003;</span>
                  )}
                  <span className="sr-only">{stage.id} – {stageStatus}</span>
                </div>
                {/* Label */}
                <div className={`text-[10px] font-mono font-semibold leading-[13px] tracking-[0.5px] ${styles.text}`}>
                  {stage.id}
                </div>
                <div className={`text-[8px] font-mono leading-[10px] ${styles.text} opacity-80`}>
                  {stage.label}
                </div>
                {/* One-line summary */}
                {summary && (
                  <div className="text-[8px] font-mono leading-[10px] text-[#94a3b8] max-w-[80px] truncate">
                    {summary}
                  </div>
                )}
              </button>

              {/* Connector line */}
              {idx < PIPELINE_STAGES.length - 1 && (
                <div className="flex items-center pt-[12px]">
                  <div className={`w-[12px] h-[2px] ${
                    getStageStatus(PIPELINE_STAGES[idx + 1].id) !== "pending"
                      ? "bg-[#10b981]"
                      : "bg-[#374151]"
                  }`} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PipelineStepper;

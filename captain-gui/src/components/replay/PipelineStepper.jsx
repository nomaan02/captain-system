import useReplayStore from "../../stores/replayStore";

const PIPELINE_STAGES = [
  { id: "B1", label: "Data Ingest" },
  { id: "B2", label: "Regime" },
  { id: "B3", label: "AIM Score" },
  { id: "B4", label: "Kelly Size" },
  { id: "B5", label: "Selection" },
  { id: "B5C", label: "Compliance" },
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
    const stage = pipelineStages[stageId];
    if (!stage) {
      if (status === "idle") return "pending";
      // If replay is running but this stage has no data yet, it's pending
      return "pending";
    }
    return stage.status || "complete";
  };

  return (
    <div data-testid="pipeline-stepper" className="px-3 py-2">
      <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono mb-2">Pipeline</div>

      {/* Horizontal stepper */}
      <div className="flex items-start gap-0 overflow-x-auto">
        {PIPELINE_STAGES.map((stage, idx) => {
          const stageStatus = getStageStatus(stage.id);
          const styles = STATUS_STYLES[stageStatus];
          const isExpanded = expandedStage === stage.id;
          const hasData = !!pipelineStages[stage.id];
          const summary = pipelineStages[stage.id]?.summary;

          return (
            <div key={stage.id} className="flex items-start">
              {/* Stage node */}
              <button
                data-testid={`pipeline-stage-${stage.id}`}
                data-status={stageStatus}
                onClick={() => hasData && setExpandedStage(stage.id)}
                className={`flex flex-col items-center gap-[3px] px-[6px] py-1 border-none bg-transparent cursor-pointer min-w-[48px] ${
                  hasData ? "hover:bg-[rgba(255,255,255,0.03)]" : "cursor-default"
                } ${isExpanded ? "bg-[rgba(6,182,212,0.08)]" : ""}`}
              >
                {/* Circle indicator */}
                <div className={`w-[10px] h-[10px] rounded-full border border-solid ${styles.circle}`} />
                {/* Label */}
                <div className={`text-[7px] font-mono leading-[9px] tracking-[0.4px] ${styles.text}`}>
                  {stage.id}
                </div>
                <div className={`text-[6px] font-mono leading-[8px] ${styles.text} opacity-70`}>
                  {stage.label}
                </div>
                {/* One-line summary */}
                {summary && (
                  <div className="text-[6px] font-mono leading-[8px] text-[#94a3b8] max-w-[60px] truncate">
                    {summary}
                  </div>
                )}
              </button>

              {/* Connector line */}
              {idx < PIPELINE_STAGES.length - 1 && (
                <div className="flex items-center pt-[6px]">
                  <div className={`w-[8px] h-[1px] ${
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

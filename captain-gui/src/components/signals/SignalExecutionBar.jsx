import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";

const STAGES = ["WAITING", "OR_FORMING", "SIGNAL_GEN", "EXECUTED"];
const STAGE_LABELS = {
  WAITING: "WAITING",
  OR_FORMING: "OR FORMING",
  SIGNAL_GEN: "SIGNAL GEN",
  EXECUTED: "EXECUTED",
};

const SignalExecutionBar = ({ className = "" }) => {
  const pipelineStage = useDashboardStore((s) => s.pipelineStage);

  return (
    <div
      className={`w-full border-[#1e293b] border-solid border-b box-border flex items-end justify-between pt-1.5 px-3 pb-[5px] gap-5 max-w-full text-left text-[15px] text-[#64748b] font-['JetBrains_Mono'] ${className}`}
    >
      {/* Title + pipeline pills */}
      <div className="w-full flex items-start gap-3 max-w-xl flex-nowrap">
        <div className="flex flex-col items-start pt-0.5 px-0 pb-0">
          <div className="relative tracking-[1.5px] leading-6 uppercase">{`Signal & Execution`}</div>
        </div>
        <div data-testid="session-phase" className="flex-1 flex items-start gap-1.5 min-w-[231px] max-w-full text-xs flex-nowrap">
          {STAGES.map((stage) => {
            const isActive = stage === pipelineStage;
            return (
              <div
                key={stage}
                data-testid={`execution-stage-${stage}`}
                data-active={isActive ? "true" : "false"}
                aria-current={isActive ? "step" : undefined}
                className={`border-solid border flex items-center py-0.5 px-2.5 whitespace-nowrap ${
                  isActive
                    ? "bg-[rgba(59,246,62,0.2)] border-[rgba(59,246,74,0.4)] text-[#63f63b]"
                    : "border-[#1e293b] text-[#64748b]"
                }`}
              >
                <div className="relative">{STAGE_LABELS[stage]}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Auto-execute toggle removed — backend reads AUTO_EXECUTE from env var, no runtime toggle support */}
    </div>
  );
};

SignalExecutionBar.propTypes = {
  className: PropTypes.string,
};

export default SignalExecutionBar;

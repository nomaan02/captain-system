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
      className={`w-full border-[#1e293b] border-solid border-b box-border flex items-end justify-between pt-[6.1px] px-3 pb-[5px] gap-5 max-w-full text-left text-[15.2px] text-[#64748b] font-['JetBrains_Mono'] mq750:flex-wrap mq750:gap-5 ${className}`}
    >
      {/* Title + pipeline pills */}
      <div className="w-[558.7px] flex items-start gap-[11.1px] max-w-full mq750:flex-wrap">
        <div className="flex flex-col items-start pt-0.5 px-0 pb-0">
          <div className="relative tracking-[1.52px] leading-[22.7px] uppercase">{`Signal & Execution`}</div>
        </div>
        <div data-testid="session-phase" className="flex-1 flex items-start gap-1.5 min-w-[231px] max-w-full text-[12.1px] mq450:flex-wrap">
          {STAGES.map((stage) => {
            const isActive = stage === pipelineStage;
            return (
              <div
                key={stage}
                data-testid={`execution-stage-${stage}`}
                data-active={isActive ? "true" : "false"}
                className={`border-solid border flex items-start pt-px pb-[3px] pl-2.5 pr-2 min-w-[60px] ${
                  isActive
                    ? "bg-[rgba(59,246,62,0.2)] border-[rgba(59,246,74,0.4)] text-[#63f63b]"
                    : "border-[#1e293b] text-[#64748b]"
                }`}
              >
                <div className="relative leading-[18.2px]">{STAGE_LABELS[stage]}</div>
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

import useDashboardStore from "../stores/dashboardStore";

// TODO: Add independent data fetch — currently relies on DashboardPage WS being mounted first
const ModelsPage = () => {
  const connected = useDashboardStore((s) => s.connected);
  const aimStates = useDashboardStore((s) => s.aimStates);
  const regimePanel = useDashboardStore((s) => s.regimePanel);

  if (!connected && aimStates.length === 0 && !regimePanel) {
    return (
      <div className="h-full bg-surface p-4 flex items-center justify-center">
        <div className="text-[#64748b] text-xs font-mono text-center">
          Connect to the dashboard first to load data
        </div>
      </div>
    );
  }

  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">
        Models
      </h1>

      {/* AIM Registry */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
          AIM Registry
        </h2>
        <div className="grid grid-cols-1 gap-2">
          {aimStates.length > 0 ? (
            aimStates.map((aim, idx) => (
              <div
                key={aim.aim_id ?? idx}
                className="bg-surface-card border border-border-subtle p-3 font-mono text-xs"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-white">
                    AIM #{String(aim.aim_id)}
                  </span>
                  <span
                    className={`px-2 py-0.5 text-[10px] border border-solid ${
                      aim.active
                        ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                        : "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]"
                    }`}
                  >
                    {aim.active ? "ACTIVE" : "INACTIVE"}
                  </span>
                </div>
                <div className="text-[#94a3b8]">
                  {aim.asset_id && <span className="mr-3">Asset: {aim.asset_id}</span>}
                  {aim.meta_weight != null && (
                    <span>Weight: {aim.meta_weight}</span>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4">
              No AIM states available
            </div>
          )}
        </div>
      </section>

      {/* Regime Panel */}
      <section>
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
          Regime Classification
        </h2>
        {regimePanel ? (
          <div className="bg-surface-card border border-border-subtle p-3 font-mono text-xs">
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(regimePanel).map(([key, value]) => (
                <div key={key}>
                  <div className="text-[#64748b] uppercase text-[10px] tracking-wider">
                    {key.replace(/_/g, " ")}
                  </div>
                  <div className="text-white">{String(value ?? "—")}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-[#64748b] text-xs font-mono py-4">
            No regime data available
          </div>
        )}
      </section>
    </div>
  );
};

export default ModelsPage;

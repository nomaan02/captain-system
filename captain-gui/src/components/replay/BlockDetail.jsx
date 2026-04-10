import PropTypes from "prop-types";
import useReplayStore from "../../stores/replayStore";
import { formatCurrency } from "../../utils/formatting";

const TableHeader = ({ children }) => (
  <th className="text-[8px] text-[#64748b] font-mono font-normal uppercase tracking-[0.5px] text-left px-2 py-1 border-b border-solid border-[#1e293b]">
    {children}
  </th>
);

const TableCell = ({ children, className = "", title }) => (
  <td title={title} className={`text-[9px] text-[#e2e8f0] font-mono px-2 py-[3px] border-b border-solid border-[#1e293b] ${className}`}>
    {children}
  </td>
);

// B1: Show config summary from the config_loaded event
const B1Detail = ({ data }) => {
  if (!data) return <Fallback text="Waiting for data load..." />;
  return (
    <div className="p-2 space-y-1 text-[9px] font-mono">
      <Row label="Capital" value={data.user_capital ? formatCurrency(data.user_capital) : data.strategies_loaded ? `${data.strategies_loaded} strategies` : "Loaded"} />
      <Row label="Max Positions" value={data.max_positions ?? data.contracts_resolved ?? "--"} />
      <Row label="Budget Divisor" value={data.budget_divisor ?? "--"} />
      <Row label="Risk Goal" value={data.risk_goal ?? "--"} />
      <Row label="MDD Limit" value={data.mdd_limit ? formatCurrency(data.mdd_limit) : "--"} />
      <Row label="MLL Limit" value={data.mll_limit ? formatCurrency(data.mll_limit) : "--"} />
    </div>
  );
};

// B2: Regime — all neutral for now
const B2Detail = () => (
  <div className="p-2 space-y-1 text-[9px] font-mono">
    <div className="text-[#f59e0b] mb-1">All assets: REGIME_NEUTRAL (50/50 blend)</div>
    <div className="text-[#64748b]">Pettersson classifier not yet trained. B2 outputs p(LOW)=0.5, p(HIGH)=0.5 for all assets. Kelly uses equal-weighted blend of both regime fractions.</div>
  </div>
);

const AIM_NAMES = {
  1: "VRP", 2: "Skew", 3: "GEX", 4: "IVTS", 5: "Deferred",
  6: "Calendar", 7: "COT", 8: "Correlation", 9: "Momentum",
  10: "Calendar Fx", 11: "Regime Warn", 12: "Dyn Costs",
  13: "Sensitivity", 14: "Expansion", 15: "Volume", 16: "HMM",
};

const modColor = (v) => {
  if (v == null) return "text-[#64748b]";
  if (v > 1.0) return "text-[#10b981]";
  if (v < 1.0) return "text-[#ef4444]";
  return "text-[#e2e8f0]";
};

// B3: AIM — full debug panel with per-AIM visibility
const B3Detail = () => {
  const aimBreakdown = useReplayStore((s) => s.aimBreakdown);
  const combinedModifier = useReplayStore((s) => s.combinedModifier);
  const aimDebug = useReplayStore((s) => s.aimDebug);
  const aimEnabled = useReplayStore((s) => s.config.aimEnabled);
  const b3Stage = useReplayStore((s) => s.pipelineStages?.B3);

  if (!aimEnabled) {
    return (
      <div className="p-2 space-y-1 text-[9px] font-mono">
        <div className="text-[#64748b]">AIM scoring disabled. All modifiers = 1.0x (pure Kelly).</div>
      </div>
    );
  }

  // B3 ran but returned empty — show diagnostic
  const b3Complete = b3Stage?.status === "complete";
  const b3Error = b3Stage?.data?.error;
  const assets = Object.keys(aimBreakdown);
  const hasAnyActive = assets.some((a) => aimBreakdown[a] && Object.keys(aimBreakdown[a]).length > 0);

  if (!b3Complete) {
    return (
      <div className="p-2 space-y-1 text-[9px] font-mono">
        <div className="text-[#f59e0b]">AIM scoring in progress...</div>
      </div>
    );
  }

  if (b3Error) {
    return (
      <div className="p-2 space-y-1 text-[9px] font-mono">
        <div className="text-[#ef4444]">AIM scoring failed: {b3Error}</div>
        <div className="text-[#64748b] mt-1">Check console for details. Common causes: missing D01/D02 data, QuestDB column mismatch, import errors.</div>
      </div>
    );
  }

  if (!hasAnyActive) {
    return (
      <div className="p-2 space-y-2 text-[9px] font-mono">
        <div className="text-[#ef4444] font-bold">ALL AIMs SKIPPED — combined modifier = 1.0x (neutral)</div>
        <div className="text-[#94a3b8]">
          No AIMs have status=ACTIVE in D01. This means either:
        </div>
        <ul className="text-[#94a3b8] ml-3 list-disc space-y-0.5">
          <li>The offline lifecycle set them to COLLECTING (most common)</li>
          <li>The loader query picked up stale rows (QuestDB append-only dedup issue)</li>
          <li>Bootstrap was never run or was overwritten</li>
        </ul>
        <div className="text-[#64748b] mt-1">
          Combined modifiers: {Object.entries(combinedModifier).map(([a, m]) => `${a}=${m?.toFixed(3)}`).join(", ") || "none"}
        </div>
      </div>
    );
  }

  return (
    <div className="p-2 space-y-3 text-[9px] font-mono">
      {/* Per-asset combined modifier summary */}
      <div className="flex flex-wrap gap-3 mb-1">
        {Object.entries(combinedModifier).map(([asset, mod]) => (
          <div key={asset} className="flex items-center gap-1">
            <span className="text-[#06b6d4]">{asset}</span>
            <span className={modColor(mod)}>{mod?.toFixed(3) ?? "--"}x</span>
          </div>
        ))}
      </div>

      {/* Full breakdown per asset — each AIM with modifier and reason */}
      {assets.map((asset) => {
        const breakdown = aimBreakdown[asset];
        const activeCount = breakdown ? Object.keys(breakdown).length : 0;
        const mod = combinedModifier[asset];
        return (
          <div key={asset} className="border border-solid border-[#1e293b] rounded p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[#06b6d4] font-bold">{asset}</span>
              <span className={`${modColor(mod)} text-[10px]`}>
                combined = {mod?.toFixed(4) ?? "1.0000"}x ({activeCount}/16 active)
              </span>
            </div>
            {activeCount === 0 ? (
              <div className="text-[#ef4444]">All 16 AIMs skipped (status != ACTIVE)</div>
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <TableHeader>AIM</TableHeader>
                    <TableHeader>Name</TableHeader>
                    <TableHeader>Modifier</TableHeader>
                    <TableHeader>Conf</TableHeader>
                    <TableHeader>DMA Wt</TableHeader>
                    <TableHeader>Reason</TableHeader>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(breakdown)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([aimId, info]) => (
                      <tr key={aimId}>
                        <TableCell className="text-[#06b6d4]">{String(aimId).padStart(2, "0")}</TableCell>
                        <TableCell>{AIM_NAMES[Number(aimId)] || `AIM-${aimId}`}</TableCell>
                        <TableCell className={modColor(info.modifier)}>{info.modifier?.toFixed(4) ?? "--"}</TableCell>
                        <TableCell>{info.confidence?.toFixed(2) ?? "--"}</TableCell>
                        <TableCell>{info.dma_weight?.toFixed(3) ?? "--"}</TableCell>
                        <TableCell className="text-[#94a3b8] max-w-[150px] truncate" title={info.reason_tag || ""}>{info.reason_tag || "--"}</TableCell>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
};

// B4: Show accumulated sizing results from assetResults
const B4Detail = () => {
  const assetResults = useReplayStore((s) => s.assetResults);
  const entries = Object.entries(assetResults).filter(([, v]) => v?.sizing);

  if (entries.length === 0) return <Fallback text="Sizing in progress..." />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse min-w-[500px]">
        <thead>
          <tr>
            <TableHeader>Asset</TableHeader>
            <TableHeader>Kelly</TableHeader>
            <TableHeader>Risk/Ct</TableHeader>
            <TableHeader>Raw</TableHeader>
            <TableHeader>MDD</TableHeader>
            <TableHeader>Daily</TableHeader>
            <TableHeader>Max</TableHeader>
            <TableHeader>CB</TableHeader>
            <TableHeader>Final</TableHeader>
          </tr>
        </thead>
        <tbody>
          {entries.map(([asset, v]) => {
            const s = v.sizing;
            return (
              <tr key={asset}>
                <TableCell className="text-[#06b6d4]">{asset}</TableCell>
                <TableCell>{s.kelly_adjusted?.toFixed(4) ?? s.kelly_blended?.toFixed(4) ?? "--"}</TableCell>
                <TableCell>{s.risk_per_contract?.toFixed(0) ?? "--"}</TableCell>
                <TableCell>{s.raw_contracts ?? "--"}</TableCell>
                <TableCell>{s.mdd_cap ?? "--"}</TableCell>
                <TableCell>{s.daily_cap ?? "--"}</TableCell>
                <TableCell>{s.max_contracts ?? "--"}</TableCell>
                <TableCell>{s.cb_blocked ? "YES" : "--"}</TableCell>
                <TableCell className="text-[#e2e8f0] font-semibold">{s.contracts ?? "--"}</TableCell>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// B5: Position limit — show selected and excluded
const B5Detail = ({ data }) => {
  if (!data) return <Fallback text="Awaiting selection..." />;
  const selected = Array.isArray(data.selected) ? data.selected : [];
  const excluded = Array.isArray(data.excluded) ? data.excluded : [];
  return (
    <div className="p-2 space-y-2 text-[9px] font-mono">
      <div>
        <div className="text-[#10b981] uppercase tracking-[0.5px] mb-1">Selected ({selected.length})</div>
        {selected.map((s, i) => (
          <div key={s.asset || i} className="flex justify-between py-[2px]">
            <span className="text-[#06b6d4]">{s.asset ?? "--"}</span>
            <span>{(s.contracts ?? s.total_pnl) != null ? formatCurrency(s.total_pnl) : "--"}</span>
          </div>
        ))}
        {selected.length === 0 && <div className="text-[#64748b]">None</div>}
      </div>
      {excluded.length > 0 && (
        <div>
          <div className="text-[#ef4444] uppercase tracking-[0.5px] mb-1">Excluded ({excluded.length})</div>
          {excluded.map((e, i) => (
            <div key={e.asset || i} className="flex justify-between py-[2px]">
              <span className="text-[#64748b]">{e.asset ?? "--"}</span>
              <span className="text-[#ef4444]">{e.excluded_reason ?? e.reason ?? "--"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Fallback: raw JSON
const Fallback = ({ text }) => (
  <div className="text-[9px] text-[#64748b] font-mono p-3 text-center">{text}</div>
);

const GenericDetail = ({ data }) => {
  if (!data) return <Fallback text="No data available" />;
  return (
    <pre className="text-[8px] text-[#e2e8f0] font-mono p-2 whitespace-pre-wrap overflow-x-auto">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
};

const BLOCK_RENDERERS = {
  B1: B1Detail,
  B1_AUTH: GenericDetail,
  B2: B2Detail,
  B3: B3Detail,
  B4: B4Detail,
  B5: B5Detail,
  B5C: GenericDetail,
  B6: GenericDetail,
};

const BlockDetail = ({ blockId }) => {
  const stageData = useReplayStore((s) => s.pipelineStages[blockId]);

  const Renderer = BLOCK_RENDERERS[blockId] || GenericDetail;
  const needsData = !["B2", "B3", "B4"].includes(blockId); // These read from store directly

  return (
    <div
      data-testid={`block-detail-${blockId}`}
      className="border border-solid border-[#1e293b] bg-[#080e0d] max-h-[300px] overflow-y-auto"
    >
      <div className="text-[9px] text-[#06b6d4] font-mono uppercase tracking-[0.5px] px-3 py-[6px] border-b border-solid border-[#1e293b] bg-[#0a1614] flex justify-between">
        <span>{blockId} Detail</span>
        {stageData?.status && (
          <span className={stageData.status === "complete" ? "text-[#10b981]" : "text-[#64748b]"}>
            {stageData.status}
          </span>
        )}
      </div>
      {needsData ? <Renderer data={stageData?.data} /> : <Renderer />}
    </div>
  );
};

const Row = ({ label, value }) => (
  <div className="flex justify-between">
    <span className="text-[#64748b]">{label}</span>
    <span className="text-[#e2e8f0]">{value}</span>
  </div>
);

BlockDetail.propTypes = {
  blockId: PropTypes.string.isRequired,
};

export default BlockDetail;

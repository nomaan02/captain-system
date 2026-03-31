import PropTypes from "prop-types";
import useReplayStore from "../../stores/replayStore";
import { formatCurrency } from "../../utils/formatting";

const TableHeader = ({ children }) => (
  <th className="text-[8px] text-[#64748b] font-mono font-normal uppercase tracking-[0.5px] text-left px-2 py-1 border-b border-solid border-[#1e293b]">
    {children}
  </th>
);

const TableCell = ({ children, className = "" }) => (
  <td className={`text-[9px] text-[#e2e8f0] font-mono px-2 py-[3px] border-b border-solid border-[#1e293b] ${className}`}>
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

// B3: AIM — all 1.0x modifier for now
const B3Detail = () => (
  <div className="p-2 space-y-1 text-[9px] font-mono">
    <div className="text-[#f59e0b] mb-1">Combined AIM modifier: 1.0x (cold-start)</div>
    <div className="text-[#64748b]">6 Tier 1 AIMs active with equal inclusion probability (0.167 each). All current_modifier = 0.0 (initial). No sizing adjustment applied.</div>
    <table className="w-full border-collapse mt-2">
      <thead>
        <tr>
          <TableHeader>AIM</TableHeader>
          <TableHeader>Name</TableHeader>
          <TableHeader>Modifier</TableHeader>
          <TableHeader>Vote</TableHeader>
        </tr>
      </thead>
      <tbody>
        {[
          [4, "Trend Strength"], [6, "Mean Reversion"], [8, "Momentum Quality"],
          [11, "Vol Regime"], [12, "Correlation"], [15, "Micro Regime"],
        ].map(([id, name]) => (
          <tr key={id}>
            <TableCell className="text-[#06b6d4]">{id}</TableCell>
            <TableCell>{name}</TableCell>
            <TableCell>1.0000</TableCell>
            <TableCell><span className="text-[#64748b]">&mdash;</span></TableCell>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

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
            <span>{s.contracts ?? s.total_pnl != null ? formatCurrency(s.total_pnl) : "--"}</span>
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
    <pre className="text-[8px] text-[#e2e8f0] font-mono p-2 whitespace-pre-wrap overflow-x-auto max-h-[200px]">
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

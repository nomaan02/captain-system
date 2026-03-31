import PropTypes from "prop-types";
import useReplayStore from "../../stores/replayStore";

const TableHeader = ({ children }) => (
  <th className="text-[7px] text-[#64748b] font-mono font-normal uppercase tracking-[0.5px] text-left px-2 py-1 border-b border-[#1e293b]">
    {children}
  </th>
);

const TableCell = ({ children, className = "" }) => (
  <td className={`text-[9px] text-[#e2e8f0] font-mono px-2 py-[3px] border-b border-[#1e293b] ${className}`}>
    {children}
  </td>
);

const B1Detail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
  const assets = data.assets || [];
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <TableHeader>Asset</TableHeader>
          <TableHeader>Point Value</TableHeader>
          <TableHeader>Tick Size</TableHeader>
          <TableHeader>Session</TableHeader>
        </tr>
      </thead>
      <tbody>
        {assets.map((a) => (
          <tr key={a.asset || a.asset_id}>
            <TableCell className="text-[#06b6d4]">{a.asset || a.asset_id}</TableCell>
            <TableCell>{a.point_value ?? "--"}</TableCell>
            <TableCell>{a.tick_size ?? "--"}</TableCell>
            <TableCell>{a.session ?? "--"}</TableCell>
          </tr>
        ))}
        {assets.length === 0 && (
          <tr>
            <TableCell className="text-[#64748b]">No assets loaded</TableCell>
            <TableCell />
            <TableCell />
            <TableCell />
          </tr>
        )}
      </tbody>
    </table>
  );
};

const B2Detail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
  const regimes = data.regimes || data.probabilities || [];
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <TableHeader>Asset</TableHeader>
          <TableHeader>Bull</TableHeader>
          <TableHeader>Bear</TableHeader>
          <TableHeader>Neutral</TableHeader>
          <TableHeader>Regime</TableHeader>
        </tr>
      </thead>
      <tbody>
        {Array.isArray(regimes) && regimes.map((r) => (
          <tr key={r.asset || r.asset_id}>
            <TableCell className="text-[#06b6d4]">{r.asset || r.asset_id}</TableCell>
            <TableCell className="text-[#10b981]">{r.bull != null ? `${(r.bull * 100).toFixed(0)}%` : "50%"}</TableCell>
            <TableCell className="text-[#ef4444]">{r.bear != null ? `${(r.bear * 100).toFixed(0)}%` : "50%"}</TableCell>
            <TableCell>{r.neutral != null ? `${(r.neutral * 100).toFixed(0)}%` : "50%"}</TableCell>
            <TableCell>{r.regime || "NEUTRAL"}</TableCell>
          </tr>
        ))}
        {(!Array.isArray(regimes) || regimes.length === 0) && (
          <tr>
            <TableCell className="text-[#64748b]">All 50/50 neutral (cold-start)</TableCell>
            <TableCell>50%</TableCell>
            <TableCell>50%</TableCell>
            <TableCell>50%</TableCell>
            <TableCell>NEUTRAL</TableCell>
          </tr>
        )}
      </tbody>
    </table>
  );
};

const B3Detail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
  const aims = data.aims || data.scores || [];
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <TableHeader>Asset</TableHeader>
          <TableHeader>AIM</TableHeader>
          <TableHeader>Modifier</TableHeader>
          <TableHeader>Vote</TableHeader>
          <TableHeader>Weight</TableHeader>
        </tr>
      </thead>
      <tbody>
        {Array.isArray(aims) && aims.map((a, i) => {
          const vote = a.modifier > 0 ? 1 : a.modifier < 0 ? -1 : 0;
          return (
            <tr key={`${a.asset || a.asset_id}-${a.aim_id || i}`}>
              <TableCell className="text-[#06b6d4]">{a.asset || a.asset_id}</TableCell>
              <TableCell>{a.aim_id || a.name || `AIM-${i + 1}`}</TableCell>
              <TableCell className={a.modifier > 0 ? "text-[#10b981]" : a.modifier < 0 ? "text-[#ef4444]" : "text-[#64748b]"}>
                {a.modifier != null ? a.modifier.toFixed(4) : "--"}
              </TableCell>
              <TableCell>
                <span className={`text-[10px] ${vote > 0 ? "text-[#10b981]" : vote < 0 ? "text-[#ef4444]" : "text-[#64748b]"}`}>
                  {vote > 0 ? "\u25B2" : vote < 0 ? "\u25BC" : "\u2014"}
                </span>
              </TableCell>
              <TableCell>{a.weight != null ? a.weight.toFixed(4) : "--"}</TableCell>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
};

const B4Detail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
  const traces = data.traces || data.sizing || [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse min-w-[600px]">
        <thead>
          <tr>
            <TableHeader>Asset</TableHeader>
            <TableHeader>K_lo</TableHeader>
            <TableHeader>K_hi</TableHeader>
            <TableHeader>Blend</TableHeader>
            <TableHeader>xShrk</TableHeader>
            <TableHeader>x0.7</TableHeader>
            <TableHeader>EWMA</TableHeader>
            <TableHeader>Raw</TableHeader>
            <TableHeader>MDD</TableHeader>
            <TableHeader>MLL</TableHeader>
            <TableHeader>Max</TableHeader>
            <TableHeader>CB</TableHeader>
            <TableHeader>Final</TableHeader>
            <TableHeader>Binding</TableHeader>
          </tr>
        </thead>
        <tbody>
          {Array.isArray(traces) && traces.map((t) => (
            <tr key={t.asset || t.asset_id}>
              <TableCell className="text-[#06b6d4]">{t.asset || t.asset_id}</TableCell>
              <TableCell>{t.k_lo?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.k_hi?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.blend?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.shrunk?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.scaled?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.ewma?.toFixed(4) ?? "--"}</TableCell>
              <TableCell>{t.raw ?? "--"}</TableCell>
              <TableCell>{t.mdd ?? "--"}</TableCell>
              <TableCell>{t.mll ?? "--"}</TableCell>
              <TableCell>{t.max ?? "--"}</TableCell>
              <TableCell>{t.cb ?? "--"}</TableCell>
              <TableCell className="text-[#e2e8f0] font-semibold">{t.final ?? "--"}</TableCell>
              <TableCell className="text-[#f59e0b]">{t.binding ?? "--"}</TableCell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const B5Detail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
  const selected = data.selected || [];
  const excluded = data.excluded || [];
  return (
    <div className="space-y-2">
      <div>
        <div className="text-[8px] text-[#10b981] font-mono uppercase tracking-[0.5px] px-2 py-1">Selected ({selected.length})</div>
        {selected.map((s) => (
          <div key={s.asset || s.asset_id} className="flex items-center justify-between px-2 py-[2px] text-[9px] font-mono">
            <span className="text-[#06b6d4]">{s.asset || s.asset_id}</span>
            <span className="text-[#e2e8f0]">{s.contracts ?? s.qty ?? "--"} lots</span>
          </div>
        ))}
      </div>
      {excluded.length > 0 && (
        <div>
          <div className="text-[8px] text-[#ef4444] font-mono uppercase tracking-[0.5px] px-2 py-1">Excluded ({excluded.length})</div>
          {excluded.map((e) => (
            <div key={e.asset || e.asset_id} className="flex items-center justify-between px-2 py-[2px] text-[9px] font-mono">
              <span className="text-[#64748b]">{e.asset || e.asset_id}</span>
              <span className="text-[#ef4444]">{e.reason ?? "--"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const GenericDetail = ({ data }) => {
  if (!data) return <div className="text-[9px] text-[#64748b] font-mono p-2">No data</div>;
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

  if (!stageData) {
    return null;
  }

  const Renderer = BLOCK_RENDERERS[blockId] || GenericDetail;

  return (
    <div
      data-testid={`block-detail-${blockId}`}
      className="border border-[#1e293b] bg-[#080e0d] max-h-[300px] overflow-y-auto mx-3 mb-2"
    >
      <div className="text-[8px] text-[#06b6d4] font-mono uppercase tracking-[0.5px] px-2 py-1 border-b border-[#1e293b] bg-[#0a1614]">
        {blockId} Detail
      </div>
      <Renderer data={stageData.data} />
    </div>
  );
};

BlockDetail.propTypes = {
  blockId: PropTypes.string.isRequired,
};

export default BlockDetail;

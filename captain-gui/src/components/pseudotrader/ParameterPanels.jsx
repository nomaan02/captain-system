import { useMemo } from "react";

/* ── Styling constants (match SystemOverviewPage Governance table) ── */

const TH = "text-left text-[10px] text-[#94a3b8] uppercase tracking-wider font-mono font-normal px-2 py-1";
const TD = "text-[11px] text-white font-mono px-2 py-1";
const TD_MUTED = "text-[11px] text-[#64748b] font-mono px-2 py-1";

/* ── Badge helpers (same pattern as DecisionLog) ─────────────────── */

const BADGE = "px-1.5 py-0.5 text-[9px] font-mono border border-solid";

const BADGE_GREEN = `${BADGE} bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]`;
const BADGE_RED = `${BADGE} bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]`;
const BADGE_AMBER = `${BADGE} bg-[rgba(245,158,11,0.1)] border-[rgba(245,158,11,0.3)] text-[#f59e0b]`;

/* ── Shared table wrapper ────────────────────────────────────────── */

const ParamTable = ({ title, count, headers, rows, renderRow }) => (
  <div className="bg-surface-card border border-border-subtle p-3">
    <div className="flex items-center justify-between mb-2">
      <span className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase">{title}</span>
      <span className="text-[10px] text-[#64748b] font-mono">{count} rows</span>
    </div>
    <div className="overflow-y-auto" style={{ maxHeight: "300px" }}>
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-surface-card z-[1]">
          <tr>
            {headers.map((h) => (
              <th key={h} className={TH}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={headers.length} className={`${TD_MUTED} text-center py-4`}>
                No data available
              </td>
            </tr>
          ) : (
            rows.map(renderRow)
          )}
        </tbody>
      </table>
    </div>
  </div>
);

/* ── D02 AIM Weights ─────────────────────────────────────────────── */

const AimWeightsTable = ({ data }) => {
  const rows = useMemo(() => data || [], [data]);

  return (
    <ParamTable
      title="D02 AIM Weights"
      count={rows.length}
      headers={["AIM", "Asset", "Incl Prob", "Incl", "Effectiveness", "Days Below"]}
      rows={rows}
      renderRow={(row, i) => (
        <tr key={`${row.aim_id}-${row.asset_id}-${i}`} className="border-t border-border-subtle">
          <td className={TD}>{row.aim_id ?? "\u2014"}</td>
          <td className={TD}>{row.asset_id ?? "\u2014"}</td>
          <td className={TD}>
            {row.inclusion_probability != null ? (
              <span className={row.inclusion_probability >= 0.5 ? "text-[#10b981]" : "text-[#f59e0b]"}>
                {row.inclusion_probability.toFixed(4)}
              </span>
            ) : "\u2014"}
          </td>
          <td className={TD}>
            {row.inclusion_flag != null ? (
              <span className={row.inclusion_flag ? BADGE_GREEN : BADGE_RED}>
                {row.inclusion_flag ? "YES" : "NO"}
              </span>
            ) : "\u2014"}
          </td>
          <td className={TD_MUTED}>
            {row.recent_effectiveness != null ? row.recent_effectiveness.toFixed(4) : "\u2014"}
          </td>
          <td className={TD_MUTED}>
            {row.days_below_threshold != null ? row.days_below_threshold : "\u2014"}
          </td>
        </tr>
      )}
    />
  );
};

/* ── D05 EWMA States ─────────────────────────────────────────────── */

const EwmaStatesTable = ({ data }) => {
  const rows = useMemo(() => data || [], [data]);

  return (
    <ParamTable
      title="D05 EWMA States"
      count={rows.length}
      headers={["Asset", "Regime", "Session", "Win Rate", "Avg Win", "Avg Loss", "Trades"]}
      rows={rows}
      renderRow={(row, i) => (
        <tr key={`${row.asset_id}-${row.regime}-${row.session}-${i}`} className="border-t border-border-subtle">
          <td className={TD}>{row.asset_id ?? "\u2014"}</td>
          <td className={TD_MUTED}>{row.regime ?? "\u2014"}</td>
          <td className={TD_MUTED}>{row.session ?? "\u2014"}</td>
          <td className={TD}>
            {row.win_rate != null ? (
              <span className={row.win_rate >= 0.5 ? "text-[#10b981]" : "text-[#ef4444]"}>
                {(row.win_rate * 100).toFixed(1) + "%"}
              </span>
            ) : "\u2014"}
          </td>
          <td className={TD}>
            {row.avg_win != null ? (
              <span className="text-[#10b981]">{"$" + row.avg_win.toFixed(2)}</span>
            ) : "\u2014"}
          </td>
          <td className={TD}>
            {row.avg_loss != null ? (
              <span className="text-[#ef4444]">{"$" + row.avg_loss.toFixed(2)}</span>
            ) : "\u2014"}
          </td>
          <td className={TD_MUTED}>{row.n_trades != null ? row.n_trades : "\u2014"}</td>
        </tr>
      )}
    />
  );
};

/* ── D12 Kelly Fractions ─────────────────────────────────────────── */

const KellyParamsTable = ({ data }) => {
  const rows = useMemo(() => data || [], [data]);

  return (
    <ParamTable
      title="D12 Kelly Fractions"
      count={rows.length}
      headers={["Asset", "Regime", "Session", "Kelly Full", "Shrinkage", "Override"]}
      rows={rows}
      renderRow={(row, i) => (
        <tr key={`${row.asset_id}-${row.regime}-${row.session}-${i}`} className="border-t border-border-subtle">
          <td className={TD}>{row.asset_id ?? "\u2014"}</td>
          <td className={TD_MUTED}>{row.regime ?? "\u2014"}</td>
          <td className={TD_MUTED}>{row.session ?? "\u2014"}</td>
          <td className={TD}>
            {row.kelly_full != null ? (
              <span className={row.kelly_full > 0 ? "text-[#10b981]" : "text-[#f59e0b]"}>
                {row.kelly_full.toFixed(4)}
              </span>
            ) : "\u2014"}
          </td>
          <td className={TD_MUTED}>
            {row.shrinkage_factor != null ? row.shrinkage_factor.toFixed(4) : "\u2014"}
          </td>
          <td className={TD}>
            {row.sizing_override != null ? (
              <span className={BADGE_AMBER}>{row.sizing_override}</span>
            ) : "\u2014"}
          </td>
        </tr>
      )}
    />
  );
};

/* ── Main panel grid ─────────────────────────────────────────────── */

const ParameterPanels = ({ parameters }) => {
  const aim = parameters?.aim_weights;
  const ewma = parameters?.ewma_states;
  const kelly = parameters?.kelly_params;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <AimWeightsTable data={aim} />
      <EwmaStatesTable data={ewma} />
      <KellyParamsTable data={kelly} />
    </div>
  );
};

export default ParameterPanels;

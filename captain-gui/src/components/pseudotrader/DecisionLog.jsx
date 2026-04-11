import { useState, useMemo } from "react";
import DataTable from "../shared/DataTable";
import { formatTimestamp } from "../../utils/formatting";
import { createColumnHelper } from "@tanstack/react-table";

const columnHelper = createColumnHelper();

const REC_COLORS = {
  ADOPT: { bg: "bg-[rgba(16,185,129,0.15)]", border: "border-[rgba(16,185,129,0.3)]", text: "text-[#10b981]" },
  REJECT: { bg: "bg-[rgba(239,68,68,0.15)]", border: "border-[rgba(239,68,68,0.3)]", text: "text-[#ef4444]" },
};
const DEFAULT_REC = { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" };

const TYPE_COLORS = {
  aim_weight: { bg: "bg-[rgba(59,130,246,0.15)]", border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  ewma: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  kelly: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
};
const DEFAULT_TYPE = { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" };

const columns = [
  columnHelper.accessor("ts", {
    header: "Time",
    cell: (info) => (
      <span className="whitespace-nowrap">{formatTimestamp(info.getValue())}</span>
    ),
  }),
  columnHelper.accessor("update_type", {
    header: "Type",
    cell: (info) => {
      const v = info.getValue();
      const c = TYPE_COLORS[v] || DEFAULT_TYPE;
      return (
        <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${c.bg} ${c.border} ${c.text}`}>
          {v}
        </span>
      );
    },
  }),
  columnHelper.accessor("recommendation", {
    header: "Decision",
    cell: (info) => {
      const v = info.getValue();
      const c = REC_COLORS[v] || DEFAULT_REC;
      return (
        <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${c.bg} ${c.border} ${c.text}`}>
          {v}
        </span>
      );
    },
  }),
  columnHelper.accessor("sharpe_improvement", {
    header: "Sharpe \u0394",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return "\u2014";
      const color = v >= 0 ? "text-[#10b981]" : "text-[#ef4444]";
      return <span className={`font-mono ${color}`}>{v >= 0 ? "+" : ""}{v.toFixed(4)}</span>;
    },
  }),
  columnHelper.accessor("drawdown_change", {
    header: "DD \u0394",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return "\u2014";
      const color = v <= 0 ? "text-[#10b981]" : "text-[#ef4444]";
      return <span className={`font-mono ${color}`}>{v >= 0 ? "+" : ""}{v.toFixed(4)}</span>;
    },
  }),
  columnHelper.accessor("winrate_delta", {
    header: "WR \u0394",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return "\u2014";
      const color = v >= 0 ? "text-[#10b981]" : "text-[#ef4444]";
      return <span className={`font-mono ${color}`}>{v >= 0 ? "+" : ""}{v.toFixed(4)}</span>;
    },
  }),
  columnHelper.accessor("pbo", {
    header: "PBO",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return "\u2014";
      return <span className="font-mono">{v.toFixed(3)}</span>;
    },
  }),
  columnHelper.accessor("dsr", {
    header: "DSR",
    cell: (info) => {
      const v = info.getValue();
      if (v == null) return "\u2014";
      return <span className="font-mono">{v.toFixed(3)}</span>;
    },
  }),
  columnHelper.accessor("result_id", {
    header: "ID",
    cell: (info) => (
      <span className="text-[#64748b] text-[9px] font-mono">{info.getValue()}</span>
    ),
  }),
];

const FILTER_BASE =
  "bg-surface-dark border border-border-subtle text-white font-mono text-[10px] px-2 py-1 cursor-pointer focus:outline-none focus:border-border-accent";

const DecisionLog = ({ decisions }) => {
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [recFilter, setRecFilter] = useState("ALL");

  const updateTypes = useMemo(() => {
    const types = new Set(decisions.map((d) => d.update_type).filter(Boolean));
    return ["ALL", ...Array.from(types).sort()];
  }, [decisions]);

  const recTypes = useMemo(() => {
    const types = new Set(decisions.map((d) => d.recommendation).filter(Boolean));
    return ["ALL", ...Array.from(types).sort()];
  }, [decisions]);

  const filtered = useMemo(() => {
    return decisions.filter((d) => {
      if (typeFilter !== "ALL" && d.update_type !== typeFilter) return false;
      if (recFilter !== "ALL" && d.recommendation !== recFilter) return false;
      return true;
    });
  }, [decisions, typeFilter, recFilter]);

  return (
    <div>
      {/* Filter bar */}
      <div className="flex items-center gap-3 mb-3">
        <label className="text-[10px] text-[#94a3b8] font-mono uppercase tracking-wider flex items-center gap-1.5">
          Type
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className={FILTER_BASE}
          >
            {updateTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="text-[10px] text-[#94a3b8] font-mono uppercase tracking-wider flex items-center gap-1.5">
          Decision
          <select
            value={recFilter}
            onChange={(e) => setRecFilter(e.target.value)}
            className={FILTER_BASE}
          >
            {recTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <span className="text-[10px] text-[#64748b] font-mono ml-auto">
          {filtered.length} / {decisions.length}
        </span>
      </div>

      <DataTable
        columns={columns}
        data={filtered}
        searchPlaceholder="Search decisions..."
        emptyMessage="No pseudotrader decisions recorded"
      />
    </div>
  );
};

export default DecisionLog;

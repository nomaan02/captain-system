import type { Incident } from "@/api/types";
import { createColumnHelper } from "@tanstack/react-table";
import { DataTable } from "@/components/DataTable";
import { Badge } from "@/components/Badge";
import { formatTimestamp } from "@/utils/formatters";
import { AlertCircle } from "lucide-react";

const col = createColumnHelper<Incident>();
const columns = [
  col.accessor("timestamp", { header: "Time", cell: (i) => formatTimestamp(i.getValue()) }),
  col.accessor("severity", {
    header: "Severity",
    cell: (i) => {
      const v = i.getValue();
      const cls =
        v === "P1_CRITICAL" ? "bg-red-500/20 text-red-600"
        : v === "P2_HIGH" ? "bg-orange-500/20 text-orange-600"
        : v === "P3_MEDIUM" ? "bg-yellow-500/20 text-yellow-700"
        : "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300";
      return <Badge label={v} className={cls} />;
    },
  }),
  col.accessor("type", { header: "Type" }),
  col.accessor("component", { header: "Component" }),
  col.accessor("status", { header: "Status" }),
  col.accessor("details", { header: "Details", cell: (i) => (
    <span className="max-w-xs truncate text-[10px] text-gray-400">{i.getValue() ?? "—"}</span>
  )}),
];

interface Props {
  incidents: Incident[];
}

export function IncidentLog({ incidents }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <AlertCircle className="h-3.5 w-3.5" /> Incident Log
        </span>
        <span className="text-xs font-normal text-gray-400">{incidents.length} records</span>
      </div>
      <DataTable data={incidents} columns={columns} searchPlaceholder="Search incidents..." />
    </div>
  );
}

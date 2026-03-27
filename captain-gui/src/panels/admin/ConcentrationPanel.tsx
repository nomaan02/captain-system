import type { Exposure } from "@/api/types";
import { DataTable } from "@/components/DataTable";
import { createColumnHelper } from "@tanstack/react-table";
import { Badge } from "@/components/Badge";
import { Layers } from "lucide-react";

const col = createColumnHelper<Exposure>();
const columns = [
  col.accessor("asset", { header: "Asset" }),
  col.accessor("direction", {
    header: "Direction",
    cell: (i) => (
      <Badge
        label={i.getValue()}
        className={i.getValue() === "LONG" ? "bg-green-500/20 text-green-600" : "bg-red-500/20 text-red-600"}
      />
    ),
  }),
  col.accessor("total_contracts", { header: "Contracts" }),
  col.accessor("user_count", { header: "Users" }),
];

interface Props {
  exposures: Exposure[];
}

export function ConcentrationPanel({ exposures }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5" /> Network Concentration
        </span>
        <span className="text-xs font-normal text-gray-400">{exposures.length} positions</span>
      </div>
      <DataTable data={exposures} columns={columns} />
    </div>
  );
}

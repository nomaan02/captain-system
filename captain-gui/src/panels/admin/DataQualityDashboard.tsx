import type { DataQualityAsset } from "@/api/types";
import { StatusDot } from "@/components/StatusDot";
import { formatTimeAgo } from "@/utils/formatters";
import { Database } from "lucide-react";

interface Props {
  data: { assets: DataQualityAsset[] };
}

export function DataQualityDashboard({ data }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Database className="h-3.5 w-3.5" /> Data Quality
        </span>
      </div>
      {data.assets.length === 0 ? (
        <p className="text-sm text-gray-400">No asset data</p>
      ) : (
        <div className="space-y-1">
          {data.assets.map((a) => {
            const fresh = a.last_data_update
              ? Date.now() - new Date(a.last_data_update).getTime() < 300_000
              : false;
            return (
              <div key={a.asset_id} className="flex items-center justify-between rounded px-2 py-1.5 text-xs">
                <div className="flex items-center gap-2">
                  <StatusDot color={fresh ? "bg-green-500" : "bg-red-500"} pulse={!fresh} />
                  <span className="font-medium">{a.asset_id}</span>
                </div>
                <div className="flex items-center gap-3 text-gray-400">
                  <span>{a.status}</span>
                  <span>{formatTimeAgo(a.last_data_update)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

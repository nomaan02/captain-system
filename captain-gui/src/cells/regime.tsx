import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { DataCell, DataCellRow } from "@/components/ui/data-cell";

export function RegimeCell() {
  // Regime is derived from P2 locked result — REGIME_NEUTRAL for current deployment
  // In future: read regime state per-asset from signal payloads or a dedicated store field
  return (
    <Panel title="REGIME" accent="gray">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="info">REGIME_NEUTRAL</Badge>
      </div>

      <DataCellRow className="mb-2 grid-cols-2">
        <DataCell label="Method" value="XGBoost" />
        <DataCell label="Accuracy" value="74%" />
      </DataCellRow>

      <DataCellRow className="grid-cols-2">
        <DataCell label="Tau-b" value="0.06" />
        <DataCell label="p-value" value="0.19" />
      </DataCellRow>

      <div className="mt-2 text-[11px] text-dim">
        Neutral regime — no vol-based allocation adjustment active.
      </div>
    </Panel>
  );
}

import { useEffect } from "react";
import { api } from "@/api/client";
import { useSystemOverviewStore } from "@/stores/systemOverviewStore";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ConcentrationPanel } from "@/panels/admin/ConcentrationPanel";
import { SignalQualityDashboard } from "@/panels/admin/SignalQualityDashboard";
import { CapacityUtilization } from "@/panels/admin/CapacityUtilization";
import { SystemHealthDashboard } from "@/panels/admin/SystemHealthDashboard";
import { ActionQueue } from "@/panels/admin/ActionQueue";
import { DataQualityDashboard } from "@/panels/admin/DataQualityDashboard";
import { IncidentLog } from "@/panels/admin/IncidentLog";
import { ComplianceStatus } from "@/panels/admin/ComplianceStatus";
import { CircuitBreakerStatus } from "@/panels/admin/CircuitBreakerStatus";
import { ActiveConstraints } from "@/panels/admin/ActiveConstraints";
import { PerformancePanel } from "@/panels/admin/PerformancePanel";
import { VersionHistory } from "@/panels/admin/VersionHistory";
import { ReconciliationStatus } from "@/panels/admin/ReconciliationStatus";
import { AdminDecisionLog } from "@/panels/admin/AdminDecisionLog";
import { StressTestReview } from "@/panels/admin/StressTestReview";
import { DeploymentStatus } from "@/panels/admin/DeploymentStatus";
import { ModelValidation } from "@/panels/admin/ModelValidation";
import { GovernanceSchedule } from "@/panels/admin/GovernanceSchedule";
import { CapacityRecommendations } from "@/panels/admin/CapacityRecommendations";

export function SystemOverviewPage() {
  const overview = useSystemOverviewStore((s) => s.overview);
  const setOverview = useSystemOverviewStore((s) => s.setOverview);

  useEffect(() => {
    api.systemOverview().then(setOverview).catch(() => {});
  }, [setOverview]);

  if (!overview) return <LoadingSpinner />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">System Overview</h1>

      {/* Row 1: Health radar + Concentration */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SystemHealthDashboard scores={overview.diagnostic_health} />
        <ConcentrationPanel exposures={overview.network_concentration.exposures} />
      </div>

      {/* Row 2: Signal quality + Capacity + Compliance */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <SignalQualityDashboard quality={overview.signal_quality} />
        <CapacityUtilization capacity={overview.capacity_state} />
        <ComplianceStatus gate={overview.compliance_gate} />
      </div>

      {/* Row 3: Action queue + Data quality */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ActionQueue items={overview.action_queue} />
        <DataQualityDashboard data={overview.data_quality} />
      </div>

      {/* Row 4: Circuit breaker + Deployment */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CircuitBreakerStatus />
        <DeploymentStatus />
      </div>

      {/* Row 5: Constraints + Reconciliation + Performance */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ActiveConstraints />
        <ReconciliationStatus />
        <PerformancePanel />
      </div>

      {/* Row 6: Model + Governance + Capacity Recs */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ModelValidation />
        <GovernanceSchedule />
        <CapacityRecommendations />
      </div>

      {/* Row 7: Incident log (full width) */}
      <IncidentLog incidents={overview.incident_log} />

      {/* Row 8: Admin log + Stress test + Version */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <AdminDecisionLog />
        <StressTestReview />
        <VersionHistory />
      </div>
    </div>
  );
}

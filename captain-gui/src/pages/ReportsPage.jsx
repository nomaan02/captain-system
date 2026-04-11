import { useEffect } from "react";
import useReportsStore from "../stores/reportsStore";
import StatusBadge from "../components/shared/StatusBadge";
import { formatTimestamp } from "../utils/formatting";

const TRIGGER_COLORS = {
  pre_session: { bg: "bg-[rgba(59,130,246,0.15)]", border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  session_open: { bg: "bg-[rgba(59,130,246,0.15)]", border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  scheduled: { bg: "bg-[rgba(59,130,246,0.15)]", border: "border-[rgba(59,130,246,0.3)]", text: "text-[#3b82f6]" },
  per_trade: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  per_session: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  daily: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  monthly: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
  first_of_month: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
  end_of_week: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
  annually: { bg: "bg-[rgba(6,182,212,0.15)]", border: "border-[rgba(6,182,212,0.3)]", text: "text-[#06b6d4]" },
};
const DEFAULT_TRIGGER = { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" };

const ReportsPage = () => {
  const { reportTypes, selectedType, generating, result, error, loading, fetchTypes, selectType, generate } = useReportsStore();

  useEffect(() => { fetchTypes(); }, []);

  const handleGenerate = () => {
    if (selectedType) {
      generate(selectedType.id || selectedType.report_id, "primary_user");
    }
  };

  const downloadFile = (content, filename, mimeType) => {
    const blob = new Blob([typeof content === "string" ? content : JSON.stringify(content, null, 2)], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getDate = () => new Date().toISOString().slice(0, 10);

  const renderTriggerBadge = (trigger) => {
    const colors = TRIGGER_COLORS[trigger] || DEFAULT_TRIGGER;
    return (
      <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${colors.bg} ${colors.border} ${colors.text}`}>
        {trigger}
      </span>
    );
  };

  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">Reports</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Left panel - Report type selector */}
        <div className="col-span-1">
          <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">Report Types</h2>
          {/* 140px = page padding (32px) + title row (52px) + section heading (32px) + breathing room */}
          <div className="bg-surface-card border border-border-subtle overflow-y-auto max-h-[calc(100vh-140px)]">
            {loading ? (
              <div className="p-4 text-[#64748b] text-xs font-mono">Loading report types...</div>
            ) : error && reportTypes.length === 0 ? (
              <div className="p-4 text-[#ef4444] text-xs font-mono">Failed to load report types</div>
            ) : reportTypes.length === 0 ? (
              <div className="p-4 text-[#64748b] text-xs font-mono">No report types available</div>
            ) : (
              reportTypes.map((rt) => {
                const id = rt.id || rt.report_id;
                const isSelected = selectedType && (selectedType.id || selectedType.report_id) === id;
                return (
                  <button
                    key={id}
                    onClick={() => selectType(rt)}
                    aria-current={isSelected ? "true" : undefined}
                    className={`w-full text-left px-3 py-2.5 border-b border-border-subtle cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-[rgba(16,185,129,0.1)] border-l-2 border-l-[#10b981]"
                        : "bg-transparent hover:bg-[rgba(100,116,139,0.05)]"
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-mono text-[#64748b]">{id}</span>
                      <span className="text-xs font-mono text-white">{rt.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {renderTriggerBadge(rt.trigger)}
                      <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${
                        rt.format === "in_app" || rt.render_format === "in_app"
                          ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                          : "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]"
                      }`}>
                        {rt.format || rt.render_format || "csv"}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right panel - Generation area */}
        <div className="col-span-1 md:col-span-2">
          <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">Generate Report</h2>
          <div className="bg-surface-card border border-border-subtle p-4">
            {selectedType ? (
              <>
                <div className="mb-4">
                  <div className="text-white font-mono text-sm mb-1">{selectedType.name}</div>
                  <div className="text-[#64748b] font-mono text-[10px]">{selectedType.id || selectedType.report_id}</div>
                </div>

                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className={`px-4 py-2 text-[11px] font-mono border border-solid cursor-pointer transition-colors mb-4 ${
                    generating
                      ? "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b] cursor-not-allowed"
                      : "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981] hover:bg-[rgba(16,185,129,0.25)]"
                  }`}
                >
                  {generating ? "Generating..." : "Generate"}
                </button>

                {error && (
                  <div className="text-[#ef4444] text-xs font-mono mb-4">{error}</div>
                )}

                {result && (
                  <div>
                    {/* Metadata */}
                    <div className="border-t border-border-subtle pt-3 mb-3">
                      <div className="flex items-center gap-4 mb-2 text-xs font-mono">
                        <span className="text-[#64748b]">Report ID:</span>
                        <span className="text-white">{result.report_id}</span>
                      </div>
                      <div className="flex items-center gap-4 mb-2 text-xs font-mono">
                        <span className="text-[#64748b]">Generated:</span>
                        <span className="text-white">{formatTimestamp(result.generated_at)}</span>
                      </div>
                      <div className="flex items-center gap-4 mb-3 text-xs font-mono">
                        <span className="text-[#64748b]">Format:</span>
                        <StatusBadge status={result.format || "csv"} />
                      </div>
                    </div>

                    {/* Download buttons */}
                    <div className="flex gap-2 mb-4">
                      {(result.format === "csv" || typeof result.data === "string") && (
                        <button
                          onClick={() => downloadFile(result.data, `${result.report_type}_${getDate()}.csv`, "text/csv")}
                          className="px-3 py-1.5 text-[10px] font-mono border border-solid bg-[rgba(59,130,246,0.15)] border-[rgba(59,130,246,0.3)] text-[#3b82f6] cursor-pointer hover:bg-[rgba(59,130,246,0.25)] transition-colors"
                        >
                          Download CSV
                        </button>
                      )}
                      <button
                        onClick={() => downloadFile(
                          typeof result.data === "string" ? result.data : JSON.stringify(result.data, null, 2),
                          `${result.report_type}_${getDate()}.json`,
                          "application/json"
                        )}
                        className="px-3 py-1.5 text-[10px] font-mono border border-solid bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b] cursor-pointer hover:bg-[rgba(100,116,139,0.15)] transition-colors"
                      >
                        Download JSON
                      </button>
                    </div>

                    {/* Preview */}
                    <div className="border-t border-border-subtle pt-3">
                      <div className="text-[10px] font-mono text-[#64748b] uppercase tracking-wider mb-2">Preview</div>
                      <pre className="max-h-[400px] overflow-y-auto bg-surface-dark border border-border-subtle p-3 text-xs font-mono text-[#e2e8f0] whitespace-pre-wrap">
                        {typeof result.data === "string"
                          ? result.data.split("\n").slice(0, 20).join("\n")
                          : JSON.stringify(result.data, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-[#64748b] text-xs font-mono py-4 text-center">
                Select a report type to generate
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ReportsPage;

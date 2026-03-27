import { useState, useEffect, useCallback } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { formatTimestamp } from "@/utils/formatters";
import { Badge } from "@/components/Badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { FileText, Download, Eye } from "lucide-react";

interface ReportMeta {
  id: string;
  name: string;
  description?: string;
  trigger?: string;
  render?: string;
}

interface GeneratedReport {
  report_id: string;
  report_type: string;
  name: string;
  format: string;
  data: unknown;
  generated_at: string;
}

export function ReportsPage() {
  const { user } = useAuth();
  const [reportTypes, setReportTypes] = useState<Record<string, ReportMeta>>({});
  const [selected, setSelected] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GeneratedReport | null>(null);

  useEffect(() => {
    api.reportTypes().then((types) => {
      // types comes as a dict from the backend
      setReportTypes(types as any);
      const keys = Object.keys(types);
      if (keys.length > 0 && !selected) setSelected(keys[0]);
    }).catch(() => {});
  }, []);

  const generate = useCallback(async () => {
    if (!selected) return;
    setGenerating(true);
    setResult(null);
    try {
      const res = await api.generateReport(selected, user.user_id);
      setResult(res as any);
    } catch {
      // ignore
    }
    setGenerating(false);
  }, [selected, user.user_id]);

  const downloadCsv = useCallback(() => {
    if (!result || typeof result.data !== "string") return;
    const blob = new Blob([result.data], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.report_type}_${result.generated_at.slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const downloadJson = useCallback(() => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.report_type}_${result.generated_at.slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [result]);

  const entries = Object.entries(reportTypes);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Reports</h1>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Report selector */}
        <div className="panel xl:col-span-1">
          <div className="panel-header">Report Types</div>
          <div className="space-y-1">
            {entries.map(([id, meta]) => (
              <button
                key={id}
                onClick={() => { setSelected(id); setResult(null); }}
                className={`flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors ${
                  selected === id
                    ? "bg-captain-blue/10 text-captain-blue"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                }`}
              >
                <FileText className="h-3.5 w-3.5 flex-shrink-0" />
                <div>
                  <div className="font-medium">{id}</div>
                  <div className="text-xs opacity-70">{(meta as any).name}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Generate + preview */}
        <div className="panel xl:col-span-2">
          {selected && (
            <>
              <div className="panel-header">
                <span>{selected} — {(reportTypes[selected] as any)?.name}</span>
                <Badge
                  label={(reportTypes[selected] as any)?.render ?? "csv"}
                  className="bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300"
                />
              </div>

              <button
                onClick={generate}
                disabled={generating}
                className="mb-4 rounded bg-captain-blue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:opacity-50"
              >
                {generating ? "Generating..." : "Generate Report"}
              </button>

              {generating && <LoadingSpinner />}

              {result && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                    <span>ID: {result.report_id}</span>
                    <span>Generated: {formatTimestamp(result.generated_at)}</span>
                  </div>

                  {/* Download buttons */}
                  <div className="flex gap-2">
                    {result.format === "csv" || typeof result.data === "string" ? (
                      <button
                        onClick={downloadCsv}
                        className="flex items-center gap-1 rounded border border-gray-300 px-3 py-1.5 text-xs dark:border-gray-600"
                      >
                        <Download className="h-3 w-3" /> CSV
                      </button>
                    ) : null}
                    <button
                      onClick={downloadJson}
                      className="flex items-center gap-1 rounded border border-gray-300 px-3 py-1.5 text-xs dark:border-gray-600"
                    >
                      <Download className="h-3 w-3" /> JSON
                    </button>
                  </div>

                  {/* In-app preview for in_app format */}
                  {result.format === "in_app" && typeof result.data === "object" && (
                    <div className="rounded border border-gray-200 p-3 dark:border-gray-700">
                      <div className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                        <Eye className="h-3 w-3" /> Preview
                      </div>
                      <pre className="mt-2 max-h-96 overflow-auto text-xs">
                        {JSON.stringify(result.data, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* CSV preview */}
                  {typeof result.data === "string" && (
                    <div className="rounded border border-gray-200 p-3 dark:border-gray-700">
                      <div className="flex items-center gap-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                        <Eye className="h-3 w-3" /> CSV Preview (first 20 rows)
                      </div>
                      <pre className="mt-2 max-h-96 overflow-auto text-xs">
                        {result.data.split("\n").slice(0, 21).join("\n")}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

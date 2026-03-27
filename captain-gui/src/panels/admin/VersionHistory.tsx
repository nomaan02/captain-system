import { GitCommit } from "lucide-react";

interface Version {
  version: string;
  date: string;
  changes: string;
}

const VERSIONS: Version[] = [
  { version: "1.0.0", date: "2026-03-14", changes: "Initial Captain Function release — V1+V2+V3 unified build" },
];

export function VersionHistory() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <GitCommit className="h-3.5 w-3.5" /> Version History
        </span>
      </div>
      <div className="space-y-2">
        {VERSIONS.map((v) => (
          <div key={v.version} className="flex items-start gap-3 text-xs">
            <span className="rounded bg-captain-blue/10 px-2 py-0.5 font-mono text-captain-blue">
              v{v.version}
            </span>
            <div>
              <span className="text-gray-400">{v.date}</span>
              <p className="text-gray-600 dark:text-gray-300">{v.changes}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

import { Loader2 } from "lucide-react";

interface Props {
  asset: string;
  level: number;
  startedAt?: string;
}

export function StrategyReviewStatus({ asset, level, startedAt }: Props) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-purple-500/10 px-4 py-2 text-sm text-purple-600 dark:text-purple-400">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>
        <strong>{asset}</strong> — Level {level} rerun in progress
        {startedAt && <span className="text-xs opacity-70"> (started {startedAt})</span>}
      </span>
    </div>
  );
}

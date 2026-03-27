import { useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";

interface Props {
  accountId: string;
  currentTsm: string;
  options?: string[];
}

const DEFAULT_TSMS = ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"];

export function TsmSelector({ accountId, currentTsm, options = DEFAULT_TSMS }: Props) {
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      send({
        type: "command",
        command: "SELECT_TSM",
        account_id: accountId,
        tsm_name: e.target.value,
        user_id: user.user_id,
      });
    },
    [send, accountId, user.user_id],
  );

  return (
    <select
      value={currentTsm}
      onChange={handleChange}
      className="rounded border border-gray-300 bg-transparent px-2 py-1 text-xs dark:border-gray-600"
    >
      {options.map((tsm) => (
        <option key={tsm} value={tsm}>
          {tsm}
        </option>
      ))}
    </select>
  );
}

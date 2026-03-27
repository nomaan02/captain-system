import { useAuth } from "@/auth/AuthContext";
import { useThemeStore } from "@/stores/themeStore";

export function SettingsPage() {
  const { user } = useAuth();
  const { theme, toggle } = useThemeStore();

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Settings</h1>

      <div className="panel max-w-lg">
        <div className="panel-header">User</div>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-gray-500 dark:text-gray-400">User ID</dt>
            <dd className="font-mono">{user.user_id}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-gray-500 dark:text-gray-400">Role</dt>
            <dd>{user.role}</dd>
          </div>
        </dl>
      </div>

      <div className="panel max-w-lg">
        <div className="panel-header">Appearance</div>
        <div className="flex items-center justify-between text-sm">
          <span>Theme</span>
          <button
            onClick={toggle}
            className="rounded border border-gray-300 px-3 py-1 text-xs dark:border-gray-600"
          >
            {theme === "dark" ? "Switch to Light" : "Switch to Dark"}
          </button>
        </div>
      </div>
    </div>
  );
}

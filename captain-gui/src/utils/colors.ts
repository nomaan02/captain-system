import type { NotificationPriority, CaptainStatus, AimStatus } from "./constants";

export const priorityColor: Record<NotificationPriority, string> = {
  CRITICAL: "bg-red-600 text-white",
  HIGH: "bg-orange-500 text-white",
  MEDIUM: "bg-yellow-400 text-gray-900",
  LOW: "bg-gray-300 text-gray-700 dark:bg-gray-700 dark:text-gray-300",
};

export const priorityDot: Record<NotificationPriority, string> = {
  CRITICAL: "bg-red-500",
  HIGH: "bg-orange-500",
  MEDIUM: "bg-yellow-400",
  LOW: "bg-gray-400",
};

export const captainStatusColor: Record<CaptainStatus, string> = {
  ACTIVE: "text-green-500",
  WARM_UP: "text-yellow-500",
  TRAINING_ONLY: "text-blue-500",
  INACTIVE: "text-gray-400",
  DATA_HOLD: "text-orange-400",
  ROLL_PENDING: "text-purple-500",
  PAUSED: "text-red-400",
  DECAYED: "text-red-600",
};

export const aimStatusColor: Record<AimStatus, string> = {
  INSTALLED: "text-gray-400",
  COLLECTING: "text-blue-400",
  WARM_UP: "text-yellow-500",
  BOOTSTRAPPED: "text-cyan-500",
  ELIGIBLE: "text-green-400",
  ACTIVE: "text-green-600",
  SUPPRESSED: "text-red-400",
};

import { useEffect, useRef } from "react";
import { api } from "@/api/client";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useNotificationStore } from "@/stores/notificationStore";

const REST_POLL_MS = 10_000;

export function useDashboardPolling(userId: string, wsConnected: boolean) {
  const setSnapshot = useDashboardStore((s) => s.setSnapshot);
  const setNotifications = useNotificationStore((s) => s.setNotifications);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  useEffect(() => {
    // Initial REST load
    api.dashboard(userId).then((snap) => {
      setSnapshot(snap);
      setNotifications(snap.notifications);
    }).catch(() => {});

    // Poll only when WS is disconnected
    if (!wsConnected) {
      timerRef.current = setInterval(() => {
        api.dashboard(userId).then(setSnapshot).catch(() => {});
      }, REST_POLL_MS);
    }

    return () => clearInterval(timerRef.current);
  }, [userId, wsConnected, setSnapshot, setNotifications]);
}

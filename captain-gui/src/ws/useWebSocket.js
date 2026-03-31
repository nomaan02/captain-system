import { useEffect, useRef, useCallback } from "react";
import useDashboardStore from "../stores/dashboardStore";
import useNotificationStore from "../stores/notificationStore";
import useChartStore from "../stores/chartStore";
import useSystemOverviewStore from "../stores/systemOverviewStore";
import useReplayStore from "../stores/replayStore";

const BASE_DELAY = 2000;
const MAX_DELAY = 30000;
const EVICTION_CODE = 4001;

export default function useWebSocket(userId = "primary_user") {
  const wsRef = useRef(null);
  const retryCount = useRef(0);
  const retryTimer = useRef(null);

  const {
    setConnected,
    setSnapshot,
    setLiveMarket,
    addSignal,
    setCommandAck,
  } = useDashboardStore.getState();

  const { addNotification } = useNotificationStore.getState();
  const { addBar } = useChartStore.getState();

  const getWsUrl = useCallback(() => {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    return `${proto}//${host}/ws/${userId}`;
  }, [userId]);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(getWsUrl());
    wsRef.current = ws;

    ws.onopen = () => {
      retryCount.current = 0;
      setConnected(true);
    };

    ws.onclose = (event) => {
      setConnected(false);
      wsRef.current = null;

      // Don't reconnect if evicted
      if (event.code === EVICTION_CODE) return;

      // Exponential backoff
      const delay = Math.min(BASE_DELAY * Math.pow(2, retryCount.current), MAX_DELAY);
      retryCount.current += 1;
      retryTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror
    };

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.type) {
        case "connected":
          retryCount.current = 0;
          break;

        case "dashboard":
          setSnapshot(data);
          break;

        case "live_market":
          setLiveMarket(data);
          break;

        case "signal":
          if (data.signal) addSignal(data.signal);
          break;

        case "command_ack":
          setCommandAck(data);
          break;

        case "notification":
          addNotification({
            notif_id: data.notif_id,
            priority: data.priority,
            message: data.message,
            timestamp: data.timestamp,
            source: data.source,
          });
          break;

        case "error":
          addNotification({
            notif_id: `error-${Date.now()}`,
            priority: "HIGH",
            message: data.message,
            timestamp: new Date().toISOString(),
            source: "system",
          });
          break;

        case "below_threshold":
          if (data.items) {
            data.items.forEach((item) => {
              addNotification({
                notif_id: `threshold-${Date.now()}-${item.asset}`,
                priority: "MEDIUM",
                message: `${item.asset}: ${item.reason}`,
                timestamp: new Date().toISOString(),
                source: "threshold",
              });
            });
          }
          break;

        case "or_status":
          useDashboardStore.getState().setOrStatus(data);
          break;

        case "pipeline_status":
          if (data.stage) useDashboardStore.getState().setPipelineStage(data.stage);
          break;

        case "bar_update":
          if (data.bar) addBar(data.bar);
          break;

        case "system_overview":
          useSystemOverviewStore.getState().setOverview(data.data || data);
          break;

        case "replay_tick":
        case "replay_started":
        case "replay_complete":
        case "replay_error":
        case "replay_paused":
        case "replay_resumed": {
          const { handleWsMessage } = useReplayStore.getState();
          handleWsMessage(data);
          break;
        }

        default:
          break;
      }
    };
  }, [getWsUrl, setConnected, setSnapshot, setLiveMarket, addSignal, setCommandAck, addNotification, addBar]);

  // Send a command via WebSocket
  const sendCommand = useCallback((command) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", ...command, user_id: userId }));
    }
  }, [userId]);

  useEffect(() => {
    connect();
    return () => {
      if (retryTimer.current) clearTimeout(retryTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { sendCommand };
}

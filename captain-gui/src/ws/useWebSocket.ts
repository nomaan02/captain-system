import { useEffect, useCallback } from "react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useSystemOverviewStore } from "@/stores/systemOverviewStore";
import { useNotificationStore } from "@/stores/notificationStore";
import type { WsInbound } from "@/api/types";

const RECONNECT_BASE_MS = 2000;
const RECONNECT_MAX_MS = 30000;
const DISCONNECT_BANNER_DELAY_MS = 4000;
const MAX_RECONNECT_ATTEMPTS = Infinity;

// ── Singleton WebSocket ─────────────────────────────────────────────────────
// One connection per page, shared by all components that call useWebSocket().
// Prevents the eviction cascade caused by 8+ components each opening their own.

let _ws: WebSocket | null = null;
let _userId: string | null = null;
let _retries = 0;
let _reconnectTimer: ReturnType<typeof setTimeout> | undefined;
let _disconnectBannerTimer: ReturnType<typeof setTimeout> | undefined;
let _refCount = 0; // track how many components are mounted
let _closing = false;
let _connecting = false;

function _connect() {
  if (!_userId || _closing || _connecting) return;
  _connecting = true;

  // Close existing connection cleanly
  if (_ws) {
    try {
      _ws.onclose = null;
      _ws.onerror = null;
      _ws.close();
    } catch { /* ignore */ }
    _ws = null;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;

  let ws: WebSocket;
  try {
    ws = new WebSocket(`${protocol}//${host}/ws/${_userId}`);
  } catch {
    _connecting = false;
    if (_retries < MAX_RECONNECT_ATTEMPTS) {
      const delay = Math.min(RECONNECT_BASE_MS * 2 ** _retries, RECONNECT_MAX_MS);
      _retries++;
      _reconnectTimer = setTimeout(_connect, delay);
    } else {
      useDashboardStore.getState().setConnected(false);
    }
    return;
  }

  ws.onopen = () => {
    _connecting = false;
    useDashboardStore.getState().setConnected(true);
    _retries = 0;
    clearTimeout(_disconnectBannerTimer);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WsInbound;
      _dispatch(msg);
    } catch { /* ignore malformed */ }
  };

  ws.onclose = (event) => {
    _connecting = false;
    if (_ws === ws) _ws = null;

    if (_closing) return;
    if (event.code === 4001) return; // evicted by newer session — don't reconnect

    if (_retries >= MAX_RECONNECT_ATTEMPTS) {
      useDashboardStore.getState().setConnected(false);
      return;
    }

    clearTimeout(_disconnectBannerTimer);
    _disconnectBannerTimer = setTimeout(() => {
      useDashboardStore.getState().setConnected(false);
    }, DISCONNECT_BANNER_DELAY_MS);

    const delay = Math.min(RECONNECT_BASE_MS * 2 ** _retries, RECONNECT_MAX_MS);
    _retries++;
    _reconnectTimer = setTimeout(_connect, delay);
  };

  ws.onerror = () => {
    // Browser fires close automatically after error — don't double-close.
  };

  _ws = ws;
}

function _dispatch(msg: WsInbound) {
  const ds = useDashboardStore.getState();
  const so = useSystemOverviewStore.getState();
  const ns = useNotificationStore.getState();

  switch (msg.type) {
    case "dashboard":
      ds.setSnapshot(msg as any);
      break;
    case "live_market":
      ds.setLiveMarket(msg as any);
      break;
    case "signal":
      ds.addSignal((msg as any).signal);
      break;
    case "command_ack":
      ds.setCommandAck(msg as any);
      break;
    case "notification":
      ns.addNotification({
        notif_id: (msg as any).notif_id,
        priority: (msg as any).priority,
        message: (msg as any).message,
        timestamp: (msg as any).timestamp,
        delivered: true,
      });
      break;
    case "system_overview":
      so.setOverview(msg as any);
      break;
    case "connected":
      _retries = 0;
      break;
  }
}

function _teardown() {
  _closing = true;
  clearTimeout(_reconnectTimer);
  clearTimeout(_disconnectBannerTimer);
  if (_ws) {
    _ws.onclose = null;
    _ws.onerror = null;
    _ws.close();
    _ws = null;
  }
}

// ── Hook ────────────────────────────────────────────────────────────────────
// Multiple components call this; only the first mount opens the connection,
// only the last unmount closes it.

export function useWebSocket(userId: string | null) {
  useEffect(() => {
    if (!userId) return;

    _refCount++;
    if (_refCount === 1) {
      // First component mounted — open the singleton connection
      _userId = userId;
      _closing = false;
      _connecting = false;
      _connect();
    }

    return () => {
      _refCount--;
      if (_refCount <= 0) {
        _refCount = 0;
        _teardown();
      }
    };
  }, [userId]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify(data));
    }
  }, []);

  return { send };
}

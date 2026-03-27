import { create } from "zustand";
import type { Notification } from "@/api/types";

interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (n: Notification) => void;
  setNotifications: (ns: Notification[]) => void;
  markAllRead: () => void;
}

export const useNotificationStore = create<NotificationState>()((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (n) =>
    set((state) => ({
      notifications: [n, ...state.notifications].slice(0, 500),
      unreadCount: state.unreadCount + 1,
    })),

  setNotifications: (notifications) =>
    set({ notifications, unreadCount: 0 }),

  markAllRead: () => set({ unreadCount: 0 }),
}));

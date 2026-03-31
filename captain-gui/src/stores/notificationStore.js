import { create } from "zustand";

const MAX_NOTIFICATIONS = 500;

const useNotificationStore = create((set) => ({
  notifications: [],
  unreadCount: 0,
  filter: "ALL", // ALL | ERRORS | SIGNALS | ORDERS

  addNotification: (notification) =>
    set((state) => ({
      notifications: [notification, ...state.notifications].slice(0, MAX_NOTIFICATIONS),
      unreadCount: state.unreadCount + 1,
    })),

  setNotifications: (notifications) => set({ notifications }),

  markAllRead: () => set({ unreadCount: 0 }),

  setFilter: (filter) => set({ filter }),
}));

export default useNotificationStore;

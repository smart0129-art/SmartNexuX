import { create } from "zustand";

type InspectorPanel = "knowledge" | "agent";

interface DashboardState {
  activePanel: InspectorPanel;
  isSidebarOpen: boolean;
  setActivePanel: (panel: InspectorPanel) => void;
  setSidebarOpen: (isOpen: boolean) => void;
  toggleSidebar: () => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  activePanel: "knowledge",
  isSidebarOpen: true,
  setActivePanel: (activePanel) => set({ activePanel }),
  setSidebarOpen: (isSidebarOpen) => set({ isSidebarOpen }),
  toggleSidebar: () =>
    set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
}));

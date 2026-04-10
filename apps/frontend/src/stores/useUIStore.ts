import { create } from 'zustand'

interface UIState {
  sidebarCollapsed: boolean
  fileExplorerOpen: boolean
  datasetManagerOpen: boolean
  libraryInstallerOpen: boolean
  filePreviewPath: string | null

  // Actions
  setSidebarCollapsed: (collapsed: boolean) => void
  openFileExplorer: () => void
  closeFileExplorer: () => void
  openDatasetManager: () => void
  closeDatasetManager: () => void
  openLibraryInstaller: () => void
  closeLibraryInstaller: () => void
  setFilePreviewPath: (path: string | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  fileExplorerOpen: false,
  datasetManagerOpen: false,
  libraryInstallerOpen: false,
  filePreviewPath: null,

  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  openFileExplorer: () => set({ fileExplorerOpen: true }),
  closeFileExplorer: () => set({ fileExplorerOpen: false, filePreviewPath: null }),
  openDatasetManager: () => set({ datasetManagerOpen: true }),
  closeDatasetManager: () => set({ datasetManagerOpen: false }),
  openLibraryInstaller: () => set({ libraryInstallerOpen: true }),
  closeLibraryInstaller: () => set({ libraryInstallerOpen: false }),
  setFilePreviewPath: (path) => set({ filePreviewPath: path }),
}))

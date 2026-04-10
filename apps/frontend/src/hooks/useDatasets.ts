'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export function useDatasets(enabled: boolean = true) {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: () => apiClient.listDatasets(),
    enabled,
    staleTime: 60000, // Consider fresh for 1 minute
    refetchOnWindowFocus: false, // Don't refetch on window focus
    refetchInterval: false, // Don't auto-poll
    retry: 2,
  })
}

export function useAddDataset() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (url: string) => apiClient.addDataset(url),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useDeleteDataset() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (name: string) => apiClient.deleteDataset(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] })
    },
  })
}

export function useInstallLibraries() {
  return useMutation({
    mutationFn: ({ sessionId, libraries }: { sessionId: string; libraries: string[] }) =>
      apiClient.installLibraries(sessionId, libraries),
  })
}

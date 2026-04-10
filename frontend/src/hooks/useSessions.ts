'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { useSessionStore } from '@/stores/useSessionStore'

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      try {
        const sessions = await apiClient.listSessions()
        // Ensure we always return an array
        return Array.isArray(sessions) ? sessions : []
      } catch (error) {
        console.error('[useSessions] Failed to fetch sessions:', error)
        return []
      }
    },
    staleTime: 30000,
    retry: 2,
    retryDelay: 1000,
  })
}

export function useSession(id: string | null) {
  return useQuery({
    queryKey: ['session', id],
    queryFn: () => (id ? apiClient.getSession(id) : null),
    enabled: !!id,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => apiClient.createSession(),
    onSuccess: (newSession) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      return newSession
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => apiClient.deleteSession(id),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      // Clear current session if it was deleted
      const { currentSessionId, setCurrentSession } = useSessionStore.getState()
      if (currentSessionId === deletedId) {
        setCurrentSession(null)
      }
    },
  })
}

export function useSendMessage() {
  return useMutation({
    mutationFn: ({ sessionId, message }: { sessionId: string; message: string }) =>
      apiClient.sendMessage(sessionId, message),
  })
}

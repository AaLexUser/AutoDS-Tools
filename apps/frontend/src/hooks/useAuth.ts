'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export function useAuthState() {
  return useQuery({
    queryKey: ['auth-state'],
    queryFn: () => apiClient.getAuthState(),
    staleTime: 30_000,
    retry: 1,
  })
}

export function useAdminUsers(enabled: boolean = true) {
  return useQuery({
    queryKey: ['admin-users'],
    queryFn: () => apiClient.listUsers(),
    enabled,
    staleTime: 10_000,
  })
}

export function useApproveUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => apiClient.approveUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      queryClient.invalidateQueries({ queryKey: ['auth-state'] })
    },
  })
}

export function useDisableUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (userId: string) => apiClient.disableUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      queryClient.invalidateQueries({ queryKey: ['auth-state'] })
    },
  })
}

export function useCliTokens(enabled: boolean = true) {
  return useQuery({
    queryKey: ['cli-tokens'],
    queryFn: () => apiClient.listCliTokens(),
    enabled,
    staleTime: 10_000,
  })
}

export function useCreateCliToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (label: string) => apiClient.createCliToken(label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cli-tokens'] })
    },
  })
}

export function useRevokeCliToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (tokenId: string) => apiClient.revokeCliToken(tokenId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cli-tokens'] })
    },
  })
}

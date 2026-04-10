'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export function useArtifacts(sessionId: string | null, pollingEnabled: boolean = false) {
  return useQuery({
    queryKey: ['artifacts', sessionId],
    queryFn: () => (sessionId ? apiClient.getArtifacts(sessionId) : null),
    enabled: !!sessionId,
    staleTime: 30000, // Consider data fresh for 30 seconds
    refetchInterval: pollingEnabled ? 15000 : false, // Poll every 15 seconds only when explicitly enabled
  })
}

export function useFileContent(sessionId: string | null, filePath: string | null) {
  return useQuery({
    queryKey: ['file-content', sessionId, filePath],
    queryFn: () =>
      sessionId && filePath ? apiClient.getFileContent(sessionId, filePath) : null,
    enabled: !!sessionId && !!filePath,
  })
}

export function useUploadFiles() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, files }: { sessionId: string; files: File[] }) =>
      apiClient.uploadFiles(sessionId, files),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['artifacts', variables.sessionId] })
    },
  })
}

export function getFileExtension(filename: string | null | undefined): string {
  if (!filename) return ''
  const parts = filename.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
}

export function isTextFile(filename: string | null | undefined): boolean {
  if (!filename) return false
  const textExtensions = ['txt', 'md', 'py', 'js', 'ts', 'tsx', 'jsx', 'json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'sh', 'bash', 'zsh', 'html', 'css', 'xml', 'sql', 'log', 'gitignore', 'env']
  return textExtensions.includes(getFileExtension(filename))
}

export function isCSVFile(filename: string | null | undefined): boolean {
  if (!filename) return false
  const csvExtensions = ['csv', 'tsv']
  return csvExtensions.includes(getFileExtension(filename))
}

export function isJupyterNotebook(filename: string | null | undefined): boolean {
  if (!filename) return false
  return getFileExtension(filename) === 'ipynb'
}

export function isPythonFile(filename: string | null | undefined): boolean {
  if (!filename) return false
  return getFileExtension(filename) === 'py'
}

export function isImageFile(filename: string | null | undefined): boolean {
  if (!filename) return false
  const imageExtensions = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'ico']
  return imageExtensions.includes(getFileExtension(filename))
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

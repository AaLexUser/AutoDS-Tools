import { getApiBaseUrl } from './base-url'
import {
  CHUNKED_UPLOAD_THRESHOLD_BYTES,
  UPLOAD_CHUNK_BYTES,
} from '@/lib/uploads'

export interface Session {
  id: string
  created_at: string
  updated_at: string
  status: 'idle' | 'running' | 'cancelling' | 'error'
  folder_size: number
}

export interface TranscriptMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
  isStreaming?: boolean
  isTruncated?: boolean
  toolCallId?: string | null
  toolName?: string | null
  toolArgs?: unknown
  toolResult?: string | null
  toolStatus?: 'running' | 'completed' | 'error' | null
  toolStartedAt?: string | null
  toolCompletedAt?: string | null
  toolDurationMs?: number | null
}

export interface TranscriptResponse {
  session_id: string
  status: 'idle' | 'running' | 'cancelling' | 'error'
  messages: TranscriptMessage[]
}

export interface ArtifactNode {
  type: 'directory' | 'file'
  name: string
  path: string
  size?: number
  children?: ArtifactNode[]
}

export interface DatasetEntry {
  id: string
  name: string
  status?: 'queued' | 'running' | 'completed' | 'failed'
  error?: string
}

export type InstallLogEvent =
  | { type: 'command'; phase: string; elapsed_ms: number; command: string[] }
  | { type: 'phase'; phase: string; elapsed_ms: number }
  | { type: 'log'; phase: string; elapsed_ms: number; line: string }
  | { type: 'heartbeat'; phase: string; elapsed_ms?: number }
  | { type: 'error'; phase?: string; elapsed_ms?: number; message?: string; exit_code?: number | null }
  | { type: 'done'; status: string; installed?: string[]; elapsed_ms?: number; message?: string }

function installStreamConnectionError(cause: unknown): Error {
  const message = cause instanceof Error ? cause.message.toLowerCase() : ''
  if (
    message === 'network error' ||
    message === 'failed to fetch' ||
    message.includes('network') ||
    message.includes('load failed')
  ) {
    return new Error(
      'Connection lost while installing. The server may still be working — wait a minute and retry, or check whether the package is already installed.'
    )
  }
  return cause instanceof Error ? cause : new Error('Failed to install libraries. Please try again.')
}

interface ArtifactResponse {
  root: string
  tree: ArtifactNode[]
  files: string[]
  hash: string
}

let bootstrapPromise: Promise<void> | null = null

async function ensureBrowserBootstrap() {
  if (typeof window === 'undefined') return
  if (!bootstrapPromise) {
    bootstrapPromise = fetch(`${getApiBaseUrl()}/api/bootstrap`, {
      method: 'POST',
      credentials: 'include',
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text() || 'Failed to bootstrap browser session')
      }
    }).catch((error) => {
      bootstrapPromise = null
      throw error
    })
  }

  return bootstrapPromise
}

async function fetchJson<T>(input: string, init?: RequestInit, isUnauthorizedRetry = false): Promise<T> {
  await ensureBrowserBootstrap()

  const response = await fetch(`${getApiBaseUrl()}${input}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })

  if (response.status === 401 && !isUnauthorizedRetry) {
    bootstrapPromise = null
    return fetchJson<T>(input, init, true)
  }

  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `Request failed with status ${response.status}`)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

function parseUploadError(responseText: string, status: number): string {
  if (!responseText) {
    return `Upload failed with status ${status}`
  }
  try {
    const payload = JSON.parse(responseText) as { detail?: string | Array<{ msg?: string }> }
    if (typeof payload.detail === 'string') {
      return payload.detail
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail.map(item => item.msg).filter(Boolean).join(', ') || responseText
    }
  } catch {
    // Plain-text error body
  }
  return responseText
}

interface ChunkUploadResponse {
  complete: boolean
  received: number
  total_size?: number
  paths?: string[]
}

async function uploadChunkOnce(
  sessionId: string,
  formData: FormData,
  signal?: AbortSignal,
): Promise<ChunkUploadResponse> {
  await ensureBrowserBootstrap()

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    const abortUpload = () => {
      xhr.abort()
    }

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException('Upload aborted', 'AbortError'))
        return
      }
      signal.addEventListener('abort', abortUpload, { once: true })
    }

    xhr.addEventListener('load', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }

      if (xhr.status === 401) {
        reject(Object.assign(new Error('Unauthorized'), { status: 401 }))
        return
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as ChunkUploadResponse)
        } catch {
          reject(new Error('Invalid upload response'))
        }
        return
      }

      reject(new Error(parseUploadError(xhr.responseText, xhr.status)))
    })

    xhr.addEventListener('error', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }
      reject(new Error('Network error while uploading file'))
    })

    xhr.addEventListener('abort', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }
      reject(new DOMException('Upload aborted', 'AbortError'))
    })

    xhr.open('POST', `${getApiBaseUrl()}/api/sessions/${sessionId}/dataset/chunk`)
    xhr.withCredentials = true
    xhr.send(formData)
  })
}

async function uploadFileChunked(
  sessionId: string,
  file: File,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal,
): Promise<{ paths: string[] }> {
  let offset = 0

  while (offset < file.size) {
    if (signal?.aborted) {
      throw new DOMException('Upload aborted', 'AbortError')
    }

    const chunkBlob = file.slice(offset, offset + UPLOAD_CHUNK_BYTES)
    const formData = new FormData()
    formData.append('filename', file.name)
    formData.append('offset', String(offset))
    formData.append('total_size', String(file.size))
    formData.append('chunk', chunkBlob, file.name)

    const result = await uploadChunkOnce(sessionId, formData, signal)
    offset += chunkBlob.size
    onProgress?.(Math.min(100, Math.round((offset / file.size) * 100)))

    if (result.complete) {
      onProgress?.(100)
      return { paths: result.paths ?? [file.name] }
    }
  }

  throw new Error('Upload ended before file was complete')
}

async function uploadFileOnce(
  sessionId: string,
  file: File,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal,
): Promise<{ paths: string[] }> {
  await ensureBrowserBootstrap()

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const formData = new FormData()
    formData.append('files', file)

    const abortUpload = () => {
      xhr.abort()
    }

    if (signal) {
      if (signal.aborted) {
        reject(new DOMException('Upload aborted', 'AbortError'))
        return
      }
      signal.addEventListener('abort', abortUpload, { once: true })
    }

    xhr.upload.addEventListener('progress', event => {
      if (!onProgress || !event.lengthComputable || event.total <= 0) return
      onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
    })

    xhr.addEventListener('load', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }

      if (xhr.status === 401) {
        reject(Object.assign(new Error('Unauthorized'), { status: 401 }))
        return
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100)
        try {
          resolve(JSON.parse(xhr.responseText) as { paths: string[] })
        } catch {
          reject(new Error('Invalid upload response'))
        }
        return
      }

      reject(new Error(parseUploadError(xhr.responseText, xhr.status)))
    })

    xhr.addEventListener('error', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }
      reject(new Error('Network error while uploading file'))
    })

    xhr.addEventListener('abort', () => {
      if (signal) {
        signal.removeEventListener('abort', abortUpload)
      }
      reject(new DOMException('Upload aborted', 'AbortError'))
    })

    xhr.open('POST', `${getApiBaseUrl()}/api/sessions/${sessionId}/dataset`)
    xhr.withCredentials = true
    xhr.send(formData)
  })
}

function sortSessions(sessions: Session[]) {
  return [...sessions].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  )
}

export const apiClient = {
  async bootstrap() {
    await ensureBrowserBootstrap()
  },

  async createSession() {
    return fetchJson<Session>('/api/sessions', { method: 'POST' })
  },

  async listSessions() {
    const sessions = await fetchJson<Session[]>('/api/sessions')
    return sortSessions(sessions)
  },

  async getSession(sessionId: string) {
    return fetchJson<Session>(`/api/sessions/${sessionId}`)
  },

  async getTranscript(sessionId: string) {
    return fetchJson<TranscriptResponse>(
      `/api/sessions/${sessionId}/transcript`
    )
  },

  async deleteSession(sessionId: string) {
    return fetchJson<{ status: string; session_id: string }>(`/api/sessions/${sessionId}`, {
      method: 'DELETE',
    })
  },

  async sendMessage(sessionId: string, message: string) {
    return fetchJson<{ status: string; session_id: string }>(`/api/sessions/${sessionId}/runs`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    })
  },

  async cancelSession(sessionId: string) {
    return fetchJson<{ status: string; session_id: string }>(`/api/sessions/${sessionId}/cancel`, {
      method: 'POST',
    })
  },

  async uploadFile(
    sessionId: string,
    file: File,
    onProgress?: (percent: number) => void,
    signal?: AbortSignal,
    isUnauthorizedRetry = false,
  ): Promise<{ paths: string[] }> {
    const upload =
      file.size >= CHUNKED_UPLOAD_THRESHOLD_BYTES ? uploadFileChunked : uploadFileOnce
    try {
      return await upload(sessionId, file, onProgress, signal)
    } catch (error) {
      const isUnauthorized =
        error instanceof Error &&
        ('status' in error && error.status === 401)
      if (isUnauthorized && !isUnauthorizedRetry) {
        bootstrapPromise = null
        await ensureBrowserBootstrap()
        return this.uploadFile(sessionId, file, onProgress, signal, true)
      }
      throw error
    }
  },

  async uploadFiles(sessionId: string, files: File[]) {
    const paths: string[] = []
    for (const file of files) {
      const result = await this.uploadFile(sessionId, file)
      paths.push(...result.paths)
    }
    return { paths }
  },

  async installLibraries(sessionId: string, libraries: string[]) {
    return fetchJson<{ status: string; installed?: string[]; output?: string }>(
      `/api/sessions/${sessionId}/install`,
      {
        method: 'POST',
        body: JSON.stringify({ libraries }),
      }
    )
  },

  async installLibrariesStream(
    sessionId: string,
    libraries: string[],
    onEvent: (event: InstallLogEvent) => void
  ) {
    await ensureBrowserBootstrap()

    let response: Response
    try {
      response = await fetch(`${getApiBaseUrl()}/api/sessions/${sessionId}/install/stream`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ libraries }),
      })
    } catch (error) {
      throw installStreamConnectionError(error)
    }

    if (!response.ok || !response.body) {
      throw new Error(await response.text() || `Request failed with status ${response.status}`)
    }

    const decoder = new TextDecoder()
    const reader = response.body.getReader()
    let buffer = ''
    let errorMessage: string | null = null
    const handleEvent = (event: InstallLogEvent) => {
      if (event.type === 'error') {
        errorMessage =
          event.message ?? `Installation failed (exit code ${event.exit_code ?? 'unknown'})`
      }
      onEvent(event)
    }
    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (line.trim()) handleEvent(JSON.parse(line) as InstallLogEvent)
        }
      }
      buffer += decoder.decode()
      if (buffer.trim()) handleEvent(JSON.parse(buffer) as InstallLogEvent)
    } catch (error) {
      throw installStreamConnectionError(error)
    }
    if (errorMessage) {
      throw new Error(errorMessage)
    }
  },

  async getArtifacts(sessionId: string): Promise<ArtifactNode | null> {
    const data = await fetchJson<ArtifactResponse>(`/api/sessions/${sessionId}/artifacts`)
    return {
      type: 'directory',
      name: 'artifacts',
      path: '',
      children: data.tree,
    }
  },

  async getFile(sessionId: string, filePath: string) {
    await ensureBrowserBootstrap()

    const response = await fetch(
      `${getApiBaseUrl()}/api/sessions/${sessionId}/file?file_path=${encodeURIComponent(filePath)}`,
      {
        credentials: 'include',
      }
    )

    if (!response.ok) {
      throw new Error(await response.text())
    }

    return response
  },

  async getFileContent(sessionId: string, filePath: string) {
    const response = await this.getFile(sessionId, filePath)
    return response.text()
  },

  async listDatasets(): Promise<DatasetEntry[]> {
    return fetchJson<DatasetEntry[]>('/api/datasets')
  },

  async addDataset(url: string): Promise<DatasetEntry> {
    return fetchJson<DatasetEntry>('/api/datasets', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
  },

  async deleteDataset(name: string) {
    return fetchJson<void>(`/api/datasets/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
  },

  getArchiveUrl(sessionId: string) {
    return `${getApiBaseUrl()}/api/sessions/${sessionId}/artifacts/archive`
  },

  getWebSocketUrl(sessionId: string) {
    const baseUrl = getApiBaseUrl()
    const url = new URL(baseUrl)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `/api/ws/${sessionId}`
    url.search = ''
    return url.toString()
  },
}

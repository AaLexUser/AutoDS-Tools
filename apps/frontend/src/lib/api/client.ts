import { getApiBaseUrl } from './base-url'

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
}

export type InstallLogEvent =
  | { type: 'command'; phase: string; elapsed_ms: number; command: string[] }
  | { type: 'phase'; phase: string; elapsed_ms: number }
  | { type: 'log'; phase: string; elapsed_ms: number; line: string }
  | { type: 'error'; phase?: string; elapsed_ms?: number; message: string; exit_code?: number | null }
  | { type: 'done'; status: string; installed?: string[]; elapsed_ms?: number; message?: string }

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

  async uploadFiles(sessionId: string, files: File[]) {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    await ensureBrowserBootstrap()

    const response = await fetch(`${getApiBaseUrl()}/api/sessions/${sessionId}/dataset`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    })

    if (!response.ok) {
      throw new Error(await response.text())
    }

    return response.json() as Promise<{ paths: string[] }>
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

    const response = await fetch(`${getApiBaseUrl()}/api/sessions/${sessionId}/install/stream`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ libraries }),
    })

    if (!response.ok || !response.body) {
      throw new Error(await response.text() || `Request failed with status ${response.status}`)
    }

    const decoder = new TextDecoder()
    const reader = response.body.getReader()
    let buffer = ''
    let errorMessage: string | null = null
    const handleEvent = (event: InstallLogEvent) => {
      if (event.type === 'error') errorMessage = event.message
      onEvent(event)
    }
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

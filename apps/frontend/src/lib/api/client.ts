export interface Session {
  id: string
  created_at: string
  updated_at: string
  status: 'idle' | 'running' | 'cancelling' | 'error'
  folder_size: number
}

export interface AuthUser {
  id: string
  email: string
  display_name?: string | null
  status: 'pending' | 'approved' | 'disabled'
  is_admin: boolean
}

export interface AuthState {
  mode: 'disabled' | 'workos'
  authenticated: boolean
  user?: AuthUser | null
}

export interface TranscriptMessage {
  id: string
  role: 'user' | 'assistant' | 'environment'
  content: string
  timestamp: string
  isStreaming?: boolean
  isTruncated?: boolean
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

export interface CliTokenRecord {
  id: string
  label?: string | null
  created_at: string
  last_used_at?: string | null
}

interface ArtifactResponse {
  root: string
  tree: ArtifactNode[]
  files: string[]
  hash: string
}

function getBaseUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL
  }

  if (typeof window !== 'undefined') {
    return `${window.location.protocol}//${window.location.hostname}:8000`
  }

  return 'http://localhost:8000'
}

let bootstrapPromise: Promise<void> | null = null

async function ensureBrowserBootstrap() {
  if (typeof window === 'undefined') return
  if (!bootstrapPromise) {
    bootstrapPromise = fetch(`${getBaseUrl()}/api/auth/me`, {
      credentials: 'include',
    }).then(async (response) => {
      if (!response.ok) {
        throw new Error(await response.text() || 'Failed to load auth state')
      }
      const authState = await response.json() as AuthState
      if (authState.mode === 'disabled') {
        const bootstrapResponse = await fetch(`${getBaseUrl()}/api/bootstrap`, {
          method: 'POST',
          credentials: 'include',
        })
        if (!bootstrapResponse.ok) {
          throw new Error(await bootstrapResponse.text() || 'Failed to bootstrap browser session')
        }
      }
    }).catch((error) => {
      bootstrapPromise = null
      throw error
    })
  }

  return bootstrapPromise
}

async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  await ensureBrowserBootstrap()

  const response = await fetch(`${getBaseUrl()}${input}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })

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
  async getAuthState() {
    const response = await fetch(`${getBaseUrl()}/api/auth/me`, {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error(await response.text() || 'Failed to load auth state')
    }
    return response.json() as Promise<AuthState>
  },

  async bootstrap() {
    await ensureBrowserBootstrap()
  },

  getLoginUrl() {
    return '/api/auth/login'
  },

  async listUsers() {
    return fetchJson<AuthUser[]>('/api/admin/users')
  },

  async approveUser(userId: string) {
    return fetchJson<AuthUser>(`/api/admin/users/${userId}/approve`, {
      method: 'POST',
    })
  },

  async disableUser(userId: string) {
    return fetchJson<AuthUser>(`/api/admin/users/${userId}/disable`, {
      method: 'POST',
    })
  },

  async listCliTokens() {
    return fetchJson<CliTokenRecord[]>('/api/auth/cli/tokens')
  },

  async createCliToken(label: string) {
    return fetchJson<{ id: string; token: string; label?: string | null }>('/api/auth/cli/tokens', {
      method: 'POST',
      body: JSON.stringify({ label }),
    })
  },

  async revokeCliToken(tokenId: string) {
    return fetchJson<{ status: string; id: string }>(`/api/auth/cli/tokens/${tokenId}`, {
      method: 'DELETE',
    })
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

    const response = await fetch(`${getBaseUrl()}/api/sessions/${sessionId}/dataset`, {
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
      `${getBaseUrl()}/api/sessions/${sessionId}/file?file_path=${encodeURIComponent(filePath)}`,
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
    return `${getBaseUrl()}/api/sessions/${sessionId}/artifacts/archive`
  },

  getWebSocketUrl(sessionId: string) {
    const baseUrl = getBaseUrl()
    const url = new URL(baseUrl)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    url.pathname = `/api/ws/${sessionId}`
    url.search = ''
    return url.toString()
  },
}

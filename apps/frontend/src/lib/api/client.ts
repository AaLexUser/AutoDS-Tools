export interface Session {
  id: string
  created_at: string
  updated_at: string
  folder_size: number
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

interface ArtifactResponse {
  root: string
  tree: ArtifactNode[]
  files: string[]
  hash: string
}

function getBaseUrl() {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
}

async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBaseUrl()}${input}`, {
    ...init,
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

  async deleteSession(sessionId: string) {
    return fetchJson<{ status: string; session_id: string }>(`/api/sessions/${sessionId}`, {
      method: 'DELETE',
    })
  },

  async sendMessage(sessionId: string, message: string) {
    return fetchJson<{ status: string; session_id: string }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        message,
      }),
    })
  },

  async cancelSession(sessionId: string) {
    return fetchJson<{ status: string; session_id: string }>(`/api/session/${sessionId}/cancel`, {
      method: 'POST',
    })
  },

  async uploadFiles(sessionId: string, files: File[]) {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }

    const response = await fetch(`${getBaseUrl()}/api/session/${sessionId}/dataset`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error(await response.text())
    }

    return response.json() as Promise<{ paths: string[] }>
  },

  async installLibraries(sessionId: string, libraries: string[]) {
    return fetchJson<{ status: string; installed?: string[]; output?: string }>(
      `/api/session/${sessionId}/install`,
      {
        method: 'POST',
        body: JSON.stringify({ libraries }),
      }
    )
  },

  async getArtifacts(sessionId: string): Promise<ArtifactNode | null> {
    const data = await fetchJson<ArtifactResponse>(`/api/session/${sessionId}/artifacts`)
    return {
      type: 'directory',
      name: 'artifacts',
      path: '',
      children: data.tree,
    }
  },

  async getFile(sessionId: string, filePath: string) {
    const response = await fetch(
      `${getBaseUrl()}/api/session/${sessionId}/file?file_path=${encodeURIComponent(filePath)}`
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
    return `${getBaseUrl()}/api/session/${sessionId}/artifacts/archive`
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

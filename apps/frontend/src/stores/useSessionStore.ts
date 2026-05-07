import { create } from 'zustand'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: Date
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

interface SessionState {
  currentSessionId: string | null
  messages: Message[]
  isStreaming: boolean
  status: 'idle' | 'connecting' | 'streaming' | 'cancelling' | 'error'
  error: string | null

  // Actions
  setCurrentSession: (id: string | null) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  appendToLastMessage: (content: string) => void
  updateLastMessage: (updates: Partial<Message>) => void
  updateMessage: (id: string, updates: Partial<Message>) => void
  setStreaming: (streaming: boolean) => void
  setStatus: (status: SessionState['status'], error?: string | null) => void
  clearMessages: () => void
}

export const useSessionStore = create<SessionState>((set) => ({
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  status: 'idle',
  error: null,

  setCurrentSession: (id) => set({ currentSessionId: id }),

  setMessages: (messages) => set({ messages }),

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),

  appendToLastMessage: (content) =>
    set((state) => {
      const messages = [...state.messages]
      if (messages.length > 0) {
        const lastMessage = messages[messages.length - 1]
        if (lastMessage.role === 'assistant') {
          messages[messages.length - 1] = {
            ...lastMessage,
            content: lastMessage.content + content,
          }
        }
      }
      return { messages }
    }),

  updateLastMessage: (updates) =>
    set((state) => {
      const messages = [...state.messages]
      if (messages.length > 0) {
        messages[messages.length - 1] = {
          ...messages[messages.length - 1],
          ...updates,
        }
      }
      return { messages }
    }),

  updateMessage: (id, updates) =>
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === id ? { ...message, ...updates } : message
      ),
    })),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  setStatus: (status, error = null) => set({ status, error }),

  clearMessages: () => set({ messages: [] }),
}))

// Selectors - prevent unnecessary re-renders
export const useMessages = () => useSessionStore((state) => state.messages)
export const useIsStreaming = () => useSessionStore((state) => state.isStreaming)
export const useCurrentSessionId = () => useSessionStore((state) => state.currentSessionId)
export const useSessionStatus = () => useSessionStore((state) => state.status)

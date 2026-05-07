'use client'

import { useEffect, useRef, useCallback } from 'react'
import { apiClient, type TranscriptResponse } from '@/lib/api/client'
import { useSessionStore, Message } from '@/stores/useSessionStore'

interface WebSocketMessage {
  type:
    | 'run_started'
    | 'assistant_text_delta'
    | 'tool_call_started'
    | 'tool_call_completed'
    | 'run_completed'
    | 'run_failed'
    | 'run_cancelled'
    | 'run_cancelling'
  data?: string | { output_text?: string; is_truncated?: boolean } | Record<string, unknown> | null
  message_id?: string | null
  tool_call_id?: string | null
  tool_name?: string | null
  tool_started_at?: string | null
  tool_completed_at?: string | null
  tool_duration_ms?: number | null
  timestamp: string
}

export function useAgentWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const sessionIdRef = useRef<string | null>(null)
  const isClosingRef = useRef(false)
  const connectRef = useRef<((targetSessionId: string) => void) | null>(null)
  const maxReconnectAttempts = 5

  const applyTranscriptSnapshot = useCallback((transcript: TranscriptResponse) => {
    const messages: Message[] = transcript.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: new Date(message.timestamp),
      isStreaming: message.isStreaming,
      isTruncated: message.isTruncated,
      toolCallId: message.toolCallId,
      toolName: message.toolName,
      toolArgs: message.toolArgs,
      toolResult: message.toolResult,
      toolStatus: message.toolStatus,
      toolStartedAt: message.toolStartedAt,
      toolCompletedAt: message.toolCompletedAt,
      toolDurationMs: message.toolDurationMs,
    }))
    const store = useSessionStore.getState()
    store.setMessages(messages)

    if (transcript.status === 'running') {
      store.setStreaming(true)
      store.setStatus('streaming')
      return
    }
    if (transcript.status === 'cancelling') {
      store.setStreaming(false)
      store.setStatus('cancelling')
      return
    }
    if (transcript.status === 'error') {
      store.setStreaming(false)
      store.setStatus('error', 'Session ended in error')
      return
    }

    store.setStreaming(false)
    store.setStatus('idle')
  }, [])

  const hydrateTranscript = useCallback(async (targetSessionId: string) => {
    const transcript = await apiClient.getTranscript(targetSessionId)
    applyTranscriptSnapshot(transcript)
  }, [applyTranscriptSnapshot])

  const connect = useCallback((targetSessionId: string) => {
    if (!targetSessionId) return

    // Close existing connection if any, marking it as intentional
    if (wsRef.current) {
      isClosingRef.current = true
      wsRef.current.close(1000, 'Reconnecting')
      wsRef.current = null
    }

    // Reset closing flag for new connection
    isClosingRef.current = false

    const wsUrl = apiClient.getWebSocketUrl(targetSessionId)
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('[WS] Connected to session:', targetSessionId)
      const store = useSessionStore.getState()
      reconnectAttemptsRef.current = 0
      if (store.status === 'connecting') {
        store.setStatus(store.isStreaming ? 'streaming' : 'idle')
      }
    }

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data)
        const store = useSessionStore.getState()

        switch (msg.type) {
          case 'assistant_text_delta': {
            // Get fresh state to check last message (avoid stale closure)
            const currentMessages = store.messages
            const lastMsg = currentMessages[currentMessages.length - 1]

            // Determine the message ID to use
            const incomingId = msg.message_id ||
              (lastMsg?.role === 'assistant' && lastMsg.isStreaming ? lastMsg.id : `msg-${Date.now()}`)

            // Check if we need to start a new message
            const isNewMessage =
              !lastMsg ||
              lastMsg.role !== 'assistant' ||
              !lastMsg.isStreaming ||
              lastMsg.id !== incomingId

            if (isNewMessage) {
              // Finalize previous message if streaming
              if (lastMsg?.isStreaming) {
                store.updateLastMessage({ isStreaming: false })
              }
              // Start new message with the LLM's message_id
              const newMessage: Message = {
                id: incomingId,
                role: 'assistant',
                content: typeof msg.data === 'string' ? msg.data : '',
                timestamp: new Date(msg.timestamp),
                isStreaming: true,
              }
              store.addMessage(newMessage)
              store.setStreaming(true)
              store.setStatus('streaming')
            } else {
              // Append to existing streaming message
              store.appendToLastMessage(typeof msg.data === 'string' ? msg.data : '')
            }
            break
          }

          case 'tool_call_started': {
            const id = msg.tool_call_id || `tool-${Date.now()}`
            const existing = store.messages.find(message => message.id === id)
            const updates: Message = {
              id,
              role: 'tool',
              content: msg.tool_name || 'tool',
              timestamp: new Date(msg.timestamp),
              isStreaming: false,
              toolCallId: msg.tool_call_id || id,
              toolName: msg.tool_name || 'tool',
              toolArgs: msg.data,
              toolResult: null,
              toolStatus: 'running',
              toolStartedAt: msg.tool_started_at || existing?.toolStartedAt || msg.timestamp,
              toolCompletedAt: null,
              toolDurationMs: null,
            }
            if (existing) {
              store.updateMessage(id, updates)
            } else {
              store.addMessage(updates)
            }
            break
          }

          case 'tool_call_completed': {
            const payload = typeof msg.data === 'object' && msg.data !== null ? msg.data : {}
            const id = msg.tool_call_id || `tool-${Date.now()}`
            const outputText = typeof payload.output_text === 'string' ? payload.output_text : ''
            const existing = store.messages.find(message => message.id === id)
            const startedAt = msg.tool_started_at || existing?.toolStartedAt || null
            const completedAt = msg.tool_completed_at || msg.timestamp
            const fallbackDuration = startedAt
              ? Math.max(0, new Date(completedAt).getTime() - new Date(startedAt).getTime())
              : null
            const toolStatus = 'tool_status' in payload && payload.tool_status === 'error' ? 'error' : 'completed'
            const updates: Partial<Message> = {
              content: msg.tool_name || existing?.toolName || 'tool',
              timestamp: new Date(msg.timestamp),
              isStreaming: false,
              isTruncated: Boolean(payload.is_truncated),
              toolCallId: msg.tool_call_id || id,
              toolName: msg.tool_name || existing?.toolName || 'tool',
              toolResult: outputText,
              toolStatus,
              toolStartedAt: startedAt,
              toolCompletedAt: completedAt,
              toolDurationMs: typeof msg.tool_duration_ms === 'number' ? msg.tool_duration_ms : fallbackDuration,
            }
            if (existing) {
              store.updateMessage(id, updates)
            } else {
              store.addMessage({
                id,
                role: 'tool',
                ...updates,
                content: updates.content || 'tool',
                timestamp: updates.timestamp || new Date(msg.timestamp),
              })
            }
            break
          }

          case 'run_started': {
            store.setStatus('streaming')
            store.setStreaming(true)
            break
          }

          case 'run_completed': {
            store.updateLastMessage({ isStreaming: false })
            store.setStreaming(false)
            store.setStatus('idle')
            break
          }

          case 'run_cancelled': {
            store.updateLastMessage({ isStreaming: false })
            store.setStreaming(false)
            store.setStatus('idle')
            break
          }

          case 'run_cancelling': {
            store.setStatus('cancelling')
            break
          }

          case 'run_failed': {
            const errorText = typeof msg.data === 'string' ? msg.data : 'Session ended in error'
            const errorMessage: Message = {
              id: `run-failed-${Date.now()}`,
              role: 'tool',
              content: 'run_failed',
              timestamp: new Date(msg.timestamp),
              isStreaming: false,
              toolName: 'run_failed',
              toolResult: errorText,
              toolStatus: 'error',
            }
            store.addMessage(errorMessage)
            store.updateLastMessage({ isStreaming: false })
            store.setStreaming(false)
            store.setStatus('error', errorText)
            break
          }
        }
      } catch (e) {
        console.error('[WS] Failed to parse message:', e)
      }
    }

    ws.onclose = (event) => {
      console.log('[WS] Connection closed:', event.code, event.reason)

      // Skip reconnect if this was an intentional close or session changed
      if (isClosingRef.current || sessionIdRef.current !== targetSessionId) {
        return
      }

      const shouldReconnect = event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts
      if (shouldReconnect) {
        reconnectAttemptsRef.current++
        const delay = Math.min(1000 * 2 ** reconnectAttemptsRef.current, 10000)
        useSessionStore.getState().setStatus('connecting')
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`)
        reconnectTimeoutRef.current = setTimeout(() => {
          hydrateTranscript(targetSessionId)
            .catch(() => {
              useSessionStore.getState().setStatus('connecting')
            })
            .finally(() => {
              connectRef.current?.(targetSessionId)
            })
        }, delay)
        return
      }

      useSessionStore.getState().setStreaming(false)
      useSessionStore.getState().setStatus('error', 'Disconnected from server')
    }

    ws.onerror = () => {
      console.warn('[WS] Transport error')
    }

    wsRef.current = ws
  }, [hydrateTranscript])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    // Only reconnect if sessionId actually changed
    if (sessionIdRef.current !== sessionId) {
      const previousSessionId = sessionIdRef.current
      sessionIdRef.current = sessionId

      if (previousSessionId !== null && sessionId !== null) {
        useSessionStore.getState().clearMessages()
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        isClosingRef.current = true
        wsRef.current.close(1000, 'Session changed')
        wsRef.current = null
      }

      if (sessionId) {
        useSessionStore.getState().setStatus('connecting')
        hydrateTranscript(sessionId)
          .catch((error) => {
            console.error('[WS] Failed to hydrate transcript:', error)
            useSessionStore.getState().setStatus('error', 'Failed to load transcript')
          })
          .finally(() => connect(sessionId))
      }
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        isClosingRef.current = true
        wsRef.current.close(1000, 'Component unmounting')
      }
    }
  }, [sessionId, connect, hydrateTranscript])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      isClosingRef.current = true
      wsRef.current.close(1000, 'User disconnect')
    }
  }, [])

  return { disconnect, reconnect: connect }
}

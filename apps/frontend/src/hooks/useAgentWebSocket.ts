'use client'

import { useEffect, useRef, useCallback } from 'react'
import { apiClient, type TranscriptResponse } from '@/lib/api/client'
import { useSessionStore, Message } from '@/stores/useSessionStore'

interface WebSocketMessage {
  type: 'token' | 'tool' | 'status' | 'environment'
  data?: string
  message_id?: string
  timestamp: string
  truncated?: boolean
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
          case 'token': {
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
                content: msg.data || '',
                timestamp: new Date(msg.timestamp),
                isStreaming: true,
              }
              store.addMessage(newMessage)
              store.setStreaming(true)
              store.setStatus('streaming')
            } else {
              // Append to existing streaming message
              store.appendToLastMessage(msg.data || '')
            }
            break
          }

          case 'environment': {
            // Environment output (tool results, bash output, code execution results)
            const envMessage: Message = {
              id: `${msg.type}-${Date.now()}`,
              role: 'environment',
              content: msg.data || '',
              timestamp: new Date(msg.timestamp),
              isStreaming: false,
              isTruncated: msg.truncated,
            }
            store.addMessage(envMessage)
            break
          }

          case 'status': {
            const status = msg.data

            if (status === 'completed' || status === 'done' || status === 'cancelled') {
              store.updateLastMessage({ isStreaming: false })
              store.setStreaming(false)
              store.setStatus('idle')
            } else if (status === 'cancelling') {
              store.setStatus('cancelling')
            } else if (status?.startsWith('Error:') || status?.startsWith('error')) {
              store.updateLastMessage({ isStreaming: false })
              store.setStreaming(false)
              store.setStatus('error', status)
            } else if (status === 'started' || status === 'running') {
              store.setStatus('streaming')
            }
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

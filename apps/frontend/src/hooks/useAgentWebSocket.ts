'use client'

import { useEffect, useRef, useCallback } from 'react'
import { apiClient } from '@/lib/api/client'
import { useSessionStore, Message } from '@/stores/useSessionStore'

interface WebSocketMessage {
  type: 'token' | 'tool' | 'status' | 'environment' | 'history_batch'
  data?: string
  messages?: Array<{
    id: string
    role: 'user' | 'assistant' | 'environment'
    content: string
    timestamp: string
    isStreaming?: boolean
    isTruncated?: boolean
  }>
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
      store.setStatus('idle')
      reconnectAttemptsRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data)
        const store = useSessionStore.getState()

        switch (msg.type) {
          case 'history_batch': {
            // Handle batch history replay - render all messages instantly
            if (msg.messages && msg.messages.length > 0) {
              const messages: Message[] = msg.messages.map((m) => ({
                id: m.id,
                role: m.role,
                content: m.content,
                timestamp: new Date(m.timestamp),
                isStreaming: false,
                isTruncated: m.isTruncated,
              }))
              store.setMessages(messages)
              console.log('[WS] Restored', messages.length, 'messages from history')
            }
            break
          }

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

          case 'tool':
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
        console.log(`[WS] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`)
        reconnectTimeoutRef.current = setTimeout(() => {
          connectRef.current?.(targetSessionId)
        }, delay)
      }
    }

    ws.onerror = (error) => {
      console.error('[WS] Error:', error)
      useSessionStore.getState().setStatus('error', 'WebSocket connection error')
    }

    wsRef.current = ws
  }, [])

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
        connect(sessionId)
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
  }, [sessionId, connect])

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

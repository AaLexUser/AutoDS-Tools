'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { Message } from './Message'
import { InputArea } from './InputArea'
import { WelcomeScreen } from './WelcomeScreen'
import {
  useMessages,
  useIsStreaming,
  useCurrentSessionId,
  useSessionStore,
} from '@/stores/useSessionStore'
import { useAgentWebSocket } from '@/hooks/useAgentWebSocket'
import { ChevronDown } from 'lucide-react'

export function ChatContainer() {
  const currentSessionId = useCurrentSessionId()
  const messages = useMessages()
  const isStreaming = useIsStreaming()
  const sessionError = useSessionStore(state => state.error)

  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [atBottom, setAtBottom] = useState(true)
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({})
  const [nowMs, setNowMs] = useState(() => Date.now())
  const hasRunningTool = useMemo(
    () => messages.some(message => message.role === 'tool' && message.toolStatus === 'running'),
    [messages],
  )

  useEffect(() => {
    if (!hasRunningTool) return
    const interval = window.setInterval(() => setNowMs(Date.now()), 250)
    return () => window.clearInterval(interval)
  }, [hasRunningTool])

  useAgentWebSocket(currentSessionId)

  const handleAtBottomStateChange = useCallback((bottom: boolean) => {
    setAtBottom(bottom)
  }, [])

  const showScrollButton = !atBottom && messages.length > 0

  const scrollToBottom = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({
      index: 'LAST',
      align: 'end',
      behavior: 'smooth',
    })
  }, [])

  const handleToggleExpanded = useCallback((messageId: string) => {
    setExpandedIds(prev => ({ ...prev, [messageId]: !prev[messageId] }))
  }, [])

  if (!currentSessionId) {
    return <WelcomeScreen />
  }

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <div className="relative flex-1 overflow-hidden">
        {sessionError && (
          <div className="absolute left-1/2 top-4 z-10 w-[min(48rem,calc(100%-2rem))] -translate-x-1/2 rounded-lg border border-status-error/30 bg-status-error/10 px-3 py-2 text-sm text-status-error shadow-lg backdrop-blur-sm">
            {sessionError}
          </div>
        )}
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-text-muted">
              Send a message to begin.
            </p>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={messages}
            computeItemKey={(_, item) => item.id}
            className="h-full"
            followOutput={
              isStreaming ? 'smooth' : atBottom ? 'smooth' : false
            }
            atBottomStateChange={handleAtBottomStateChange}
            atBottomThreshold={100}
            initialTopMostItemIndex={messages.length - 1}
            itemContent={(index, item) => (
              <div className="mx-auto max-w-3xl px-5">
                <div className={index === 0 ? 'pt-8' : 'pt-5'}>
                  <Message
                    message={item}
                    isLast={index === messages.length - 1}
                    expanded={Boolean(expandedIds[item.id])}
                    nowMs={nowMs}
                    onToggleExpanded={handleToggleExpanded}
                  />
                </div>
              </div>
            )}
            components={{
              Footer: () => <div className="h-8" />,
            }}
          />
        )}

        {showScrollButton && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-background-secondary px-3 py-1.5 text-xs font-medium text-text-secondary shadow-lg backdrop-blur-sm transition-colors hover:text-text-primary"
          >
            <ChevronDown className="h-3.5 w-3.5" />
            Scroll to bottom
          </button>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border bg-background-secondary/50 backdrop-blur-sm">
        <div className="mx-auto max-w-3xl p-4">
          <InputArea />
        </div>
      </div>
    </div>
  )
}

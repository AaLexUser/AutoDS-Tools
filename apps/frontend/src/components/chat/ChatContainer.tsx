'use client'

import { useCallback, useMemo, useRef, useState } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { Message } from './Message'
import { InputArea } from './InputArea'
import { WelcomeScreen } from './WelcomeScreen'
import {
  useMessages,
  useIsStreaming,
  useCurrentSessionId,
} from '@/stores/useSessionStore'
import { useAgentWebSocket } from '@/hooks/useAgentWebSocket'
import { ChevronDown } from 'lucide-react'
import { buildChatRenderItems } from '@/lib/utils/chat-render-items'

export function ChatContainer() {
  const currentSessionId = useCurrentSessionId()
  const messages = useMessages()
  const isStreaming = useIsStreaming()

  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [atBottom, setAtBottom] = useState(true)
  const [expandedIds, setExpandedIds] = useState<Record<string, boolean>>({})
  const renderItems = useMemo(() => buildChatRenderItems(messages), [messages])

  useAgentWebSocket(currentSessionId)

  const handleAtBottomStateChange = useCallback((bottom: boolean) => {
    setAtBottom(bottom)
  }, [])

  const showScrollButton = !atBottom && renderItems.length > 0

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
        {renderItems.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-text-muted">
              Send a message to begin.
            </p>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={renderItems}
            computeItemKey={(_, item) =>
              item.attachedEnvironment
                ? `${item.message.id}:${item.attachedEnvironment.id}`
                : item.message.id
            }
            className="h-full"
            followOutput={
              isStreaming ? 'smooth' : atBottom ? 'smooth' : false
            }
            atBottomStateChange={handleAtBottomStateChange}
            atBottomThreshold={100}
            initialTopMostItemIndex={renderItems.length - 1}
            itemContent={(index, item) => (
              <div className="mx-auto max-w-3xl px-5">
                <div className={index === 0 ? 'pt-8' : 'pt-5'}>
                  <Message
                    message={item.message}
                    assistantContent={item.assistantContent}
                    isLast={index === renderItems.length - 1}
                    expanded={Boolean(expandedIds[item.message.id])}
                    onToggleExpanded={handleToggleExpanded}
                    attachedEnvironment={item.attachedEnvironment}
                    attachedEnvironmentExpanded={
                      item.attachedEnvironment
                        ? Boolean(
                            expandedIds[item.attachedEnvironment.id],
                          )
                        : false
                    }
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

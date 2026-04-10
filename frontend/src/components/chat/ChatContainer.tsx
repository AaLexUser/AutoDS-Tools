'use client'

import { useCallback, useRef, useState } from 'react'
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso'
import { Message } from './Message'
import { InputArea } from './InputArea'
import { WelcomeScreen } from './WelcomeScreen'
import { useMessages, useIsStreaming, useCurrentSessionId } from '@/stores/useSessionStore'
import { useAgentWebSocket } from '@/hooks/useAgentWebSocket'
import { ChevronDown } from 'lucide-react'

export function ChatContainer() {
  const currentSessionId = useCurrentSessionId()
  const messages = useMessages()
  const isStreaming = useIsStreaming()

  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [atBottom, setAtBottom] = useState(true)

  // Connect WebSocket when session is active
  useAgentWebSocket(currentSessionId)

  // Handle scroll state changes from Virtuoso
  const handleAtBottomStateChange = useCallback((bottom: boolean) => {
    setAtBottom(bottom)
  }, [])

  const showScrollButton = !atBottom && messages.length > 0

  // Scroll to bottom handler - align 'end' ensures we see the end of the last message
  const scrollToBottom = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({
      index: 'LAST',
      align: 'end',
      behavior: 'smooth',
    })
  }, [])

  if (!currentSessionId) {
    return <WelcomeScreen />
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-hidden relative">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/20 flex items-center justify-center mb-4">
                <span className="text-2xl">🤖</span>
              </div>
              <h2 className="text-lg font-medium text-text-primary mb-2">
                Ready to assist
              </h2>
              <p className="text-text-secondary max-w-md">
                Send a message to start your data science task. I can help with
                data exploration, feature engineering, model training, and more.
              </p>
            </div>
          </div>
        ) : (
          <Virtuoso
            ref={virtuosoRef}
            data={messages}
            className="h-full"
            // Auto-scroll to bottom when streaming or when new messages arrive (if user is at bottom)
            followOutput={isStreaming ? 'smooth' : atBottom ? 'smooth' : false}
            atBottomStateChange={handleAtBottomStateChange}
            atBottomThreshold={100}
            // Initial scroll position
            initialTopMostItemIndex={messages.length - 1}
            // Item renderer
            itemContent={(index, message) => (
              <div className="max-w-4xl mx-auto px-4">
                <div className={index === 0 ? 'pt-6' : 'pt-6'}>
                  <Message
                    message={message}
                    isLast={index === messages.length - 1}
                  />
                </div>
              </div>
            )}
            // Bottom padding
            components={{
              Footer: () => <div className="h-6" />,
            }}
          />
        )}

        {/* Scroll to Bottom Button */}
        {showScrollButton && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-full shadow-lg hover:bg-accent/90 transition-all animate-in fade-in slide-in-from-bottom-2 duration-200"
          >
            <ChevronDown className="h-4 w-4" />
            <span className="text-sm font-medium">Scroll to bottom</span>
          </button>
        )}
      </div>

      {/* Input Area */}
      <div className="border-t border-border bg-background-secondary/50 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto p-4">
          <InputArea />
        </div>
      </div>
    </div>
  )
}

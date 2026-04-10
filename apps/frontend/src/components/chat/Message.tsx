'use client'

import { useState, memo, useMemo } from 'react'
import { User, Bot, Loader2, Terminal, ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { MarkdownRenderer } from './MarkdownRenderer'
import { type Message as MessageType } from '@/stores/useSessionStore'

interface MessageProps {
  message: MessageType
  isLast: boolean
}

const PREVIEW_LENGTH = 500

// Avatar components - defined outside to avoid recreation
const UserAvatar = <User className="h-4 w-4 text-text-secondary" />
const BotAvatar = <Bot className="h-4 w-4 text-accent" />
const TerminalAvatar = <Terminal className="h-4 w-4 text-emerald-500" />

// Role labels lookup
const ROLE_LABELS: Record<MessageType['role'], string> = {
  user: 'You',
  assistant: 'AutoDS',
  environment: 'Environment',
  tool: 'Tool',
}

function MessageComponent({ message, isLast }: MessageProps) {
  const [expanded, setExpanded] = useState(false)

  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'
  const isEnvironment = message.role === 'environment'

  // Check if content is truncatable (environment message with truncated flag)
  const isTruncatable = isEnvironment && message.isTruncated

  // Memoize display content to avoid recalculation
  const displayContent = useMemo(() => {
    if (!isTruncatable || expanded) {
      return message.content
    }
    return message.content.slice(0, PREVIEW_LENGTH) + '...'
  }, [message.content, isTruncatable, expanded])

  // Determine avatar icon based on message role
  function getAvatarContent() {
    if (isUser) return UserAvatar
    if (isEnvironment) return TerminalAvatar
    return BotAvatar
  }
  const avatarContent = getAvatarContent()

  // Get role label
  const roleLabel = ROLE_LABELS[message.role]

  return (
    <div
      className={cn(
        'flex gap-4 animate-slide-up',
        isUser && 'flex-row-reverse'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 h-8 w-8 rounded-lg flex items-center justify-center',
          isUser && 'bg-surface-elevated border border-border',
          isAssistant && 'bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/20',
          isEnvironment && 'bg-emerald-500/10 border border-emerald-500/20'
        )}
      >
        {avatarContent}
      </div>

      {/* Content */}
      <div
        className={cn(
          'flex-1 min-w-0',
          isUser && 'flex flex-col items-end'
        )}
      >
        {/* Role Label */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-2xs font-medium text-text-muted uppercase tracking-wider">
            {roleLabel}
          </span>
          {message.isStreaming && isLast && (
            <Loader2 className="h-3 w-3 text-accent animate-spin" />
          )}
        </div>

        {/* Message Bubble */}
        <div
          className={cn(
            'rounded-xl px-4 py-3',
            isUser && 'bg-accent text-background max-w-[85%]',
            isAssistant && 'bg-surface border border-border-subtle w-full',
            isEnvironment && 'bg-zinc-900 border border-emerald-500/20 w-full font-mono text-sm'
          )}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : isEnvironment ? (
            <div>
              {/* Expand/Collapse Header for truncatable content */}
              {isTruncatable && (
                <div
                  className="flex items-center gap-2 mb-2 cursor-pointer select-none text-emerald-400/70 hover:text-emerald-400 transition-colors"
                  onClick={() => setExpanded(!expanded)}
                >
                  {expanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  <span className="text-xs">
                    {expanded ? 'Collapse' : 'Expand full output'}
                  </span>
                </div>
              )}
              <pre className="text-emerald-400 whitespace-pre-wrap overflow-x-auto">
                {displayContent}
              </pre>
            </div>
          ) : (
            <div className="prose-terminal">
              <MarkdownRenderer content={message.content} />
              {message.isStreaming && isLast && (
                <span className="inline-block w-2 h-4 bg-accent ml-0.5 animate-typing" />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// Custom comparison function for React.memo
// Only re-render if message content/state changes
function arePropsEqual(prevProps: MessageProps, nextProps: MessageProps): boolean {
  const prevMsg = prevProps.message
  const nextMsg = nextProps.message

  // Always re-render if isLast changed (affects streaming indicator)
  if (prevProps.isLast !== nextProps.isLast) {
    return false
  }

  // Compare message properties that affect rendering
  return (
    prevMsg.id === nextMsg.id &&
    prevMsg.content === nextMsg.content &&
    prevMsg.role === nextMsg.role &&
    prevMsg.isStreaming === nextMsg.isStreaming &&
    prevMsg.isTruncated === nextMsg.isTruncated
  )
}

export const Message = memo(MessageComponent, arePropsEqual)

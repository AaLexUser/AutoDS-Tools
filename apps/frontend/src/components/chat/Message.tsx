'use client'

import { memo } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { type ParsedAssistantContent } from '@/lib/utils/assistant-segments'
import { MarkdownRenderer } from './MarkdownRenderer'
import { FunStatus } from './FunStatus'
import { stripAnsiCodes, looksLikeErrorOutput } from '@/lib/utils/terminal-output'
import { type Message as MessageType } from '@/stores/useSessionStore'

interface MessageProps {
  message: MessageType
  assistantContent?: ParsedAssistantContent
  isLast: boolean
  expanded: boolean
  onToggleExpanded: (messageId: string) => void
  attachedEnvironment?: MessageType
  attachedEnvironmentExpanded?: boolean
}

function MessageComponent({
  message,
  assistantContent,
  isLast,
  expanded,
  onToggleExpanded,
  attachedEnvironment,
  attachedEnvironmentExpanded = false,
}: MessageProps) {
  const isUser = message.role === 'user'
  const isEnvironment = message.role === 'environment'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm border border-accent/15 bg-accent/8 px-4 py-3">
          <p className="text-sm leading-relaxed whitespace-pre-wrap text-text-primary">
            {message.content}
          </p>
        </div>
      </div>
    )
  }

  if (isEnvironment) {
    const isTruncatable = message.isTruncated
    const cleaned = stripAnsiCodes(message.content).trimEnd()
    const isError = looksLikeErrorOutput(cleaned)

    return (
      <div className="overflow-hidden rounded-lg border border-border-subtle bg-background-secondary/40">
        {isTruncatable && (
          <button
            type="button"
            aria-expanded={expanded}
            className="flex w-full items-center gap-2 px-3 py-2 text-xs text-text-muted transition-colors hover:text-text-primary"
            onClick={() => onToggleExpanded(message.id)}
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            <span>{expanded ? 'Collapse output' : 'Expand full output'}</span>
          </button>
        )}
        <div className="relative px-3 pb-3 pt-2">
          <pre
            className={cn(
              'font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-all overflow-x-auto',
              isError ? 'text-status-error' : 'text-text-secondary',
              isTruncatable && !expanded && 'max-h-48 overflow-hidden',
            )}
          >
            {cleaned}
          </pre>
          {isTruncatable && !expanded && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background-secondary/40 to-transparent" />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="min-w-0 overflow-hidden">
      <div className="prose-terminal">
        <MarkdownRenderer
          content={message.content}
          assistantContent={assistantContent}
          attachedEnvironment={attachedEnvironment}
          attachedEnvironmentExpanded={attachedEnvironmentExpanded}
          onToggleAttachedEnvironment={onToggleExpanded}
        />
        <FunStatus active={message.isStreaming && isLast} className="mt-3" />
      </div>
    </div>
  )
}

function arePropsEqual(prev: MessageProps, next: MessageProps): boolean {
  const p = prev.message
  const n = next.message
  if (prev.isLast !== next.isLast) return false
  return (
    p.id === n.id &&
    p.content === n.content &&
    p.role === n.role &&
    p.isStreaming === n.isStreaming &&
    p.isTruncated === n.isTruncated &&
    prev.expanded === next.expanded &&
    prev.assistantContent === next.assistantContent &&
    prev.attachedEnvironment?.id === next.attachedEnvironment?.id &&
    prev.attachedEnvironment?.content === next.attachedEnvironment?.content &&
    prev.attachedEnvironment?.isTruncated === next.attachedEnvironment?.isTruncated &&
    prev.attachedEnvironmentExpanded === next.attachedEnvironmentExpanded
  )
}

export const Message = memo(MessageComponent, arePropsEqual)

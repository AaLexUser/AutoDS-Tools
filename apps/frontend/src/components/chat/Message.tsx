'use client'

import { memo } from 'react'
import { MarkdownRenderer } from './MarkdownRenderer'
import { FunStatus } from './FunStatus'
import { ToolCallMessage } from './ToolCallMessage'
import { type Message as MessageType } from '@/stores/useSessionStore'

interface MessageProps {
  message: MessageType
  isLast: boolean
  expanded: boolean
  nowMs: number
  onToggleExpanded: (messageId: string) => void
}

function MessageComponent({
  message,
  isLast,
  expanded,
  nowMs,
  onToggleExpanded,
}: MessageProps) {
  const isUser = message.role === 'user'
  const isTool = message.role === 'tool'

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

  if (isTool) {
    return (
      <ToolCallMessage
        message={message}
        expanded={expanded}
        nowMs={nowMs}
        onToggleExpanded={onToggleExpanded}
      />
    )
  }

  return (
    <div className="min-w-0 overflow-hidden">
      <div className="prose-terminal">
        <MarkdownRenderer content={message.content} />
        <FunStatus active={message.isStreaming && isLast} className="mt-3" />
      </div>
    </div>
  )
}

function arePropsEqual(prev: MessageProps, next: MessageProps): boolean {
  const p = prev.message
  const n = next.message
  if (prev.isLast !== next.isLast) return false
  if (p.role === 'tool' && p.toolStatus === 'running' && prev.nowMs !== next.nowMs) return false
  return (
    p.id === n.id &&
    p.content === n.content &&
    p.role === n.role &&
    p.isStreaming === n.isStreaming &&
    p.isTruncated === n.isTruncated &&
    p.toolName === n.toolName &&
    p.toolResult === n.toolResult &&
    p.toolStatus === n.toolStatus &&
    p.toolStartedAt === n.toolStartedAt &&
    p.toolCompletedAt === n.toolCompletedAt &&
    p.toolDurationMs === n.toolDurationMs &&
    prev.expanded === next.expanded
  )
}

export const Message = memo(MessageComponent, arePropsEqual)

'use client'

import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { type Message } from '@/stores/useSessionStore'
import { CodeBlock } from './CodeBlock'
import { stripAnsiCodes } from '@/lib/utils/terminal-output'

interface ToolCallMessageProps {
  message: Message
  expanded: boolean
  nowMs: number
  onToggleExpanded: (messageId: string) => void
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)}s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.floor((ms % 60_000) / 1000)
  return `${minutes}m ${String(seconds).padStart(2, '0')}s`
}

function getArgValue(args: unknown, key: string): string | null {
  if (!args || typeof args !== 'object' || Array.isArray(args)) return null
  const value = (args as Record<string, unknown>)[key]
  return typeof value === 'string' ? value : null
}

function renderArgs(message: Message) {
  const toolName = message.toolName || message.content || 'tool'
  const args = message.toolArgs

  if (toolName === 'run_python') {
    const code = getArgValue(args, 'code') || (typeof args === 'string' ? args : '')
    return <CodeBlock language="python" code={code} showToolbar={false} preClassName="p-3 text-[13px]" />
  }

  if (toolName === 'run_shell') {
    const command = getArgValue(args, 'command') || (typeof args === 'string' ? args : '')
    return <CodeBlock language="bash" code={command} showToolbar={false} preClassName="p-3 text-[13px]" />
  }

  const json = typeof args === 'string' ? args : JSON.stringify(args ?? {}, null, 2)
  return <CodeBlock language="json" code={json} showToolbar={false} preClassName="p-3 text-[13px]" />
}

export function ToolCallMessage({ message, expanded, nowMs, onToggleExpanded }: ToolCallMessageProps) {
  const toolName = message.toolName || message.content || 'tool'
  const status = message.toolStatus || (message.toolResult ? 'completed' : 'running')
  const result = stripAnsiCodes(message.toolResult || '').trimEnd()
  const isError = status === 'error'
  const isTruncatable = message.isTruncated
  const startedMs = message.toolStartedAt ? new Date(message.toolStartedAt).getTime() : null
  const elapsedMs = status === 'running' && startedMs ? nowMs - startedMs : message.toolDurationMs

  return (
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface/50">
      <button
        type="button"
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-surface-hover/40"
        onClick={() => onToggleExpanded(message.id)}
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-text-muted" />}
        <span
          className={cn(
            'h-2 w-2 rounded-full',
            status === 'running' && 'animate-pulse bg-text-muted',
            status === 'completed' && !isError && 'bg-status-success',
            isError && 'bg-status-error',
          )}
        />
        <span className="font-mono text-[13px] text-text-secondary">{toolName}</span>
        {typeof elapsedMs === 'number' && Number.isFinite(elapsedMs) && (
          <span className="ml-auto font-mono text-xs text-text-muted">{formatDuration(elapsedMs)}</span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-border-subtle">
          <div className="border-b border-border-subtle">
            <div className="px-3 pt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-text-muted">Args</div>
            <div className="px-3 py-2">{renderArgs(message)}</div>
          </div>

          <div>
            <div className="px-3 pt-3 text-[11px] font-medium uppercase tracking-[0.16em] text-text-muted">Result</div>
            {status === 'running' && !result ? (
              <div className="px-3 py-3 text-sm text-text-muted">Waiting for result…</div>
            ) : (
              <div className="relative px-3 pb-3 pt-2">
                <pre
                  className={cn(
                    'font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-all overflow-x-auto',
                    isError ? 'text-status-error' : 'text-text-secondary',
                    isTruncatable && !expanded && 'max-h-48 overflow-hidden',
                  )}
                >
                  {result}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

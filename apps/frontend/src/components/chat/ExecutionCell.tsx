'use client'

import { useState, useCallback, useMemo, memo } from 'react'
import { Check, ChevronDown, ChevronRight, Code, Copy, Terminal } from 'lucide-react'
import { CodeBlock } from './CodeBlock'
import { cn } from '@/lib/utils/cn'
import { stripAnsiCodes, looksLikeErrorOutput } from '@/lib/utils/terminal-output'

interface CellOutput {
  id: string
  content: string
  isTruncated?: boolean
  expanded: boolean
  onToggleExpanded: (id: string) => void
}

export interface ExecutionCellProps {
  title: string
  language: string
  code: string
  icon?: React.ReactNode
  defaultExpanded?: boolean
  output?: CellOutput
}

function getPreview(code: string) {
  const lines = code.split('\n').map(l => l.trim()).filter(Boolean)
  if (!lines.length) return { text: '', extra: 0 }
  return {
    text: lines.slice(0, 2).join(' · '),
    extra: Math.max(lines.length - 2, 0),
  }
}

function ExecutionCellInner({
  title,
  language,
  code,
  icon,
  defaultExpanded = false,
  output,
}: ExecutionCellProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [copied, setCopied] = useState(false)

  const preview = useMemo(() => getPreview(code), [code])
  const cleanOutput = useMemo(
    () => (output ? stripAnsiCodes(output.content).trimEnd() : ''),
    [output],
  )
  const isError = useMemo(
    () => (cleanOutput ? looksLikeErrorOutput(cleanOutput) : false),
    [cleanOutput],
  )
  const hasOutput = Boolean(output && cleanOutput)

  const toggle = useCallback(() => setExpanded(v => !v), [])

  const handleCopy = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation()
      try {
        await navigator.clipboard.writeText(code)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      } catch {
        /* clipboard unavailable */
      }
    },
    [code],
  )

  const Chevron = expanded ? ChevronDown : ChevronRight

  return (
    <div
      className={cn(
        'group/cell overflow-hidden rounded-lg border transition-all duration-150',
        expanded
          ? 'border-border'
          : 'border-border-subtle bg-transparent hover:border-border hover:bg-surface/20',
      )}
    >
      {/* Header — always visible */}
      <div
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            toggle()
          }
        }}
        className="flex items-center gap-2.5 px-3 py-2.5 select-none cursor-pointer"
      >
        <Chevron className="h-3.5 w-3.5 flex-shrink-0 text-text-muted" />

        <span className="flex-shrink-0 text-text-muted">
          {icon || <Code className="h-3.5 w-3.5" />}
        </span>

        <span className="font-mono text-xs font-medium text-text-secondary">
          {title}
        </span>

        {!expanded && hasOutput && (
          <span className="h-1.5 w-1.5 rounded-full bg-status-success flex-shrink-0" />
        )}

        {!expanded && preview.text && (
          <>
            <span className="text-border select-none">·</span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-text-muted">
              {preview.text}
            </span>
          </>
        )}

        {!expanded && preview.extra > 0 && (
          <span className="flex-shrink-0 tabular-nums text-[10px] text-text-muted">
            +{preview.extra}
          </span>
        )}

        <button
          type="button"
          onClick={handleCopy}
          className="ml-auto flex-shrink-0 rounded p-1 text-text-muted opacity-0 transition-all hover:bg-surface-hover hover:text-text-primary group-hover/cell:opacity-100"
          aria-label="Copy code"
        >
          {copied ? (
            <Check className="h-3 w-3 text-status-success" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* Expanded body — flat, no inner cards */}
      {expanded && (
        <div className="min-w-0 overflow-hidden border-t border-border-subtle px-4 py-4">
          {/* Code */}
          <CodeBlock
            language={language}
            code={code}
            showToolbar={false}
            preClassName="px-3 py-2"
          />

          {/* Output — inline separator, no card wrapper */}
          {hasOutput && (
            <>
              <div className="flex items-center gap-2 py-3">
                <div className="h-px flex-1 bg-border-subtle" />
                <Terminal className="h-3 w-3 flex-shrink-0 text-text-muted" />
                <span className="text-[10px] font-medium uppercase tracking-widest text-text-muted">
                  Output
                </span>
                {output?.isTruncated && (
                  <button
                    type="button"
                    onClick={e => {
                      e.stopPropagation()
                      output.onToggleExpanded(output.id)
                    }}
                    className="text-[10px] text-accent transition-colors hover:text-accent-muted"
                  >
                    {output.expanded ? 'Collapse' : 'Expand'}
                  </button>
                )}
                <div className="h-px flex-1 bg-border-subtle" />
              </div>

              <div className="relative">
                <pre
                  className={cn(
                    'font-mono text-[13px] leading-relaxed whitespace-pre-wrap break-all',
                    isError ? 'text-status-error' : 'text-text-secondary',
                    output?.isTruncated &&
                      !output.expanded &&
                      'max-h-48 overflow-hidden',
                  )}
                >
                  {cleanOutput}
                </pre>
                {output?.isTruncated && !output.expanded && (
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-background to-transparent" />
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

export const ExecutionCell = memo(ExecutionCellInner)

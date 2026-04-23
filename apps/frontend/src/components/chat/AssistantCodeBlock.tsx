'use client'

import { memo, useCallback, useMemo, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Code, Copy } from 'lucide-react'
import { CodeBlock } from './CodeBlock'
import { cn } from '@/lib/utils/cn'
import { looksLikeErrorOutput, stripAnsiCodes } from '@/lib/utils/terminal-output'

interface AssistantCodeBlockProps {
  language: string
  code: string
  output?: {
    id: string
    content: string
    isTruncated?: boolean
    expanded: boolean
    onToggleExpanded: (messageId: string) => void
  }
}

function formatLabel(value: string): string {
  return value
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase())
}

function summarizeCodePreview(code: string): { preview: string; extraLines: number } {
  const lines = code
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
  if (lines.length === 0) {
    return { preview: '', extraLines: 0 }
  }

  const previewLines = lines.slice(0, 2)
  const preview = previewLines.join('  ')
  return {
    preview,
    extraLines: Math.max(lines.length - previewLines.length, 0),
  }
}

function AssistantCodeBlockComponent({ language, code, output }: AssistantCodeBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const [copied, setCopied] = useState(false)

  const title = useMemo(() => formatLabel(language), [language])
  const cleanedOutput = useMemo(
    () => (output ? stripAnsiCodes(output.content).trimEnd() : ''),
    [output]
  )
  const outputIsError = useMemo(
    () => cleanedOutput ? looksLikeErrorOutput(cleanedOutput) : false,
    [cleanedOutput]
  )
  const showOutput = Boolean(output && cleanedOutput)
  const { preview, extraLines } = useMemo(() => summarizeCodePreview(code), [code])

  const toggleExpanded = useCallback(() => {
    setExpanded(value => !value)
  }, [])

  const handleHeaderKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleExpanded()
    }
  }, [toggleExpanded])

  const handleCopy = useCallback(async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()

    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }, [code])

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface/60 shadow-[0_12px_30px_-28px_rgba(0,0,0,0.9)]">
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={toggleExpanded}
        onKeyDown={handleHeaderKeyDown}
        className="group px-4 py-3 text-left transition-colors hover:bg-surface-hover/60"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2">
              {expanded ? (
                <ChevronDown className="h-4 w-4 flex-shrink-0 text-text-muted" />
              ) : (
                <ChevronRight className="h-4 w-4 flex-shrink-0 text-text-muted" />
              )}
              <Code className="h-3.5 w-3.5 flex-shrink-0 text-text-muted" />
              <span className="font-mono text-sm font-medium text-text-primary">
                {title}
              </span>
              {showOutput && (
                <span className="rounded-full border border-border bg-background-secondary px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.18em] text-text-muted">
                  Output
                </span>
              )}
            </div>
            <div className="mt-2 flex min-w-0 items-center gap-2">
              <span className="min-w-0 truncate font-mono text-xs text-text-secondary">
                {preview || 'No code content'}
              </span>
              {extraLines > 0 && (
                <span className="flex-shrink-0 text-[10px] uppercase tracking-[0.18em] text-text-muted">
                  +{extraLines} lines
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-[10px] uppercase tracking-[0.18em] text-text-muted md:inline">
              {expanded ? 'Collapse' : 'Expand'}
            </span>
          </div>
        </div>
      </div>

      <div className="absolute right-3 top-3">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded p-1 text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
          aria-label="Copy code"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-status-success" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {expanded && (
        <>
          <div className="border-t border-border bg-surface">
            <CodeBlock language={language} code={code} showToolbar={false} />
          </div>

          {showOutput && (
            <div className="border-t border-border bg-background-secondary p-3">
              {output?.isTruncated && (
                <button
                  type="button"
                  aria-expanded={output.expanded}
                  className="mb-2 flex items-center gap-2 text-xs text-text-muted transition-colors hover:text-text-primary"
                  onClick={() => output.onToggleExpanded(output.id)}
                >
                  {output.expanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  <span>{output.expanded ? 'Collapse output' : 'Expand full output'}</span>
                </button>
              )}
              <div className="relative">
                <pre
                  className={cn(
                    'text-sm font-mono whitespace-pre-wrap overflow-x-auto',
                    outputIsError ? 'text-status-error' : 'text-text-secondary',
                    output?.isTruncated && !output.expanded && 'max-h-64 overflow-hidden'
                  )}
                >
                  {cleanedOutput}
                </pre>
                {output?.isTruncated && !output.expanded && (
                  <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-background-secondary via-background-secondary/90 to-transparent" />
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export const AssistantCodeBlock = memo(AssistantCodeBlockComponent)

'use client'

import { useMemo } from 'react'
import { Download, Code, FileText } from 'lucide-react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

hljs.registerLanguage('python', python)

interface CellOutput {
  output_type: string
  text?: string | string[]
  data?: Record<string, string | string[]>
  traceback?: string[]
}

interface NotebookCell {
  cell_type: 'code' | 'markdown' | 'raw'
  source: string | string[]
  outputs?: CellOutput[]
  execution_count?: number | null
}

interface NotebookJSON {
  cells: NotebookCell[]
  metadata?: Record<string, unknown>
}

interface JupyterPreviewProps {
  content: string
  filename: string
  onDownload: () => void
}

function getSource(source: string | string[]): string {
  return Array.isArray(source) ? source.join('') : source
}

function CellOutputComponent({ output }: { output: CellOutput }) {
  if (output.output_type === 'stream' || output.output_type === 'execute_result') {
    const text = output.text || output.data?.['text/plain']
    if (text) {
      return (
        <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm font-mono text-text-secondary">
          {getSource(text)}
        </pre>
      )
    }
  }

  if (output.output_type === 'display_data' && output.data?.['image/png']) {
    const base64 = getSource(output.data['image/png'])
    return (
      <>
        {/* Notebook outputs are dynamic base64 payloads, so using a plain img keeps rendering simple. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`data:image/png;base64,${base64}`}
        alt="Output"
        className="max-w-full"
      />
      </>
    )
  }

  if (output.output_type === 'error' && output.traceback) {
    return (
      <pre className="overflow-x-auto whitespace-pre-wrap break-all text-sm font-mono text-status-error">
        {output.traceback.join('\n')}
      </pre>
    )
  }

  return null
}

function NotebookCellComponent({ cell }: { cell: NotebookCell }) {
  const source = getSource(cell.source)

  if (cell.cell_type === 'markdown') {
    return (
      <div className="px-4 py-3 prose-terminal text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{source}</ReactMarkdown>
      </div>
    )
  }

  if (cell.cell_type === 'code') {
    return (
      <div className="min-w-0 overflow-hidden rounded-lg border border-border">
        {/* Cell header */}
        <div className="px-3 py-1.5 bg-surface-elevated border-b border-border flex items-center gap-2">
          <Code className="h-3 w-3 text-text-muted" />
          <span className="text-2xs text-text-muted font-mono">
            [{cell.execution_count ?? ' '}]
          </span>
        </div>

        {/* Code */}
        <div className="min-w-0 bg-surface">
          <pre className="overflow-x-auto whitespace-pre-wrap break-all p-3 text-sm font-mono">
            <code
              dangerouslySetInnerHTML={{
                __html: hljs.highlight(source, {
                  language: 'python',
                  ignoreIllegals: true,
                }).value,
              }}
            />
          </pre>
        </div>

        {/* Outputs */}
        {cell.outputs && cell.outputs.length > 0 && (
          <div className="min-w-0 space-y-2 border-t border-border bg-background-secondary p-3">
            {cell.outputs.map((output, i) => (
              <CellOutputComponent key={i} output={output} />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <pre className="text-sm text-text-muted font-mono p-4 bg-surface rounded">
      {source}
    </pre>
  )
}

export function JupyterPreview({ content, filename, onDownload }: JupyterPreviewProps) {
  const notebook = useMemo<NotebookJSON | null>(() => {
    try {
      return JSON.parse(content)
    } catch {
      return null
    }
  }, [content])

  if (!notebook) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-text-muted p-4">
        <p className="mb-4">Failed to parse notebook</p>
        <Button variant="secondary" size="sm" onClick={onDownload}>
          <Download className="h-4 w-4 mr-2" />
          Download File
        </Button>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-2 border-b border-border bg-surface flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-text-muted" />
          <span className="text-sm text-text-secondary font-mono">{filename}</span>
          <span className="text-2xs text-text-muted">
            ({notebook.cells.length} cells)
          </span>
        </div>
        <Button variant="secondary" size="sm" onClick={onDownload}>
          <Download className="h-4 w-4 mr-2" />
          Download
        </Button>
      </div>

      {/* Cells */}
      <ScrollArea className="flex-1">
        <div className="min-w-0 w-full space-y-4 p-4">
          {notebook.cells.map((cell, index) => (
            <NotebookCellComponent key={index} cell={cell} />
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

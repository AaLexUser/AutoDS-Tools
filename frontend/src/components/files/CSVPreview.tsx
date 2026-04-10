'use client'

import { useMemo } from 'react'
import Papa from 'papaparse'
import { Download, Table } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils/cn'

interface CSVPreviewProps {
  content: string
  filename: string
  onDownload: () => void
}

export function CSVPreview({ content, filename, onDownload }: CSVPreviewProps) {
  const parsed = useMemo(() => {
    return Papa.parse(content, {
      header: true,
      preview: 100,
      skipEmptyLines: true,
    })
  }, [content])

  const columns = parsed.meta.fields || []
  const rows = parsed.data as Record<string, unknown>[]

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-2 border-b border-border bg-surface flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Table className="h-4 w-4 text-text-muted" />
          <span className="text-sm font-mono text-text-secondary">{filename}</span>
          <span className="text-sm text-text-secondary">
            {rows.length} rows × {columns.length} columns
          </span>
          {parsed.data.length >= 100 && (
            <span className="text-2xs text-text-muted">(showing first 100)</span>
          )}
        </div>
        <Button variant="secondary" size="sm" onClick={onDownload}>
          <Download className="h-4 w-4 mr-2" />
          Download
        </Button>
      </div>

      {/* Table */}
      <ScrollArea className="flex-1">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="bg-surface-elevated">
                <th className="px-3 py-2 text-left text-2xs font-medium text-text-muted uppercase tracking-wider border-b border-border w-12">
                  #
                </th>
                {columns.map((col, i) => (
                  <th
                    key={i}
                    className="px-3 py-2 text-left text-2xs font-medium text-text-muted uppercase tracking-wider border-b border-border whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className={cn(
                    'hover:bg-surface-hover transition-colors',
                    rowIndex % 2 === 0 ? 'bg-transparent' : 'bg-surface/50'
                  )}
                >
                  <td className="px-3 py-2 text-text-muted font-mono text-xs border-b border-border-subtle">
                    {rowIndex + 1}
                  </td>
                  {columns.map((col, colIndex) => (
                    <td
                      key={colIndex}
                      className="px-3 py-2 text-text-primary border-b border-border-subtle max-w-[200px] truncate"
                      title={String(row[col] ?? '')}
                    >
                      {String(row[col] ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ScrollArea>
    </div>
  )
}

'use client'

import { useState } from 'react'
import { Download, Copy, Check } from 'lucide-react'
import hljs from 'highlight.js/lib/core'
import python from 'highlight.js/lib/languages/python'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'

hljs.registerLanguage('python', python)

interface PythonPreviewProps {
  content: string
  filename: string
  onDownload: () => void
}

export function PythonPreview({ content, filename, onDownload }: PythonPreviewProps) {
  const [copied, setCopied] = useState(false)

  const lines = content.split('\n')

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-2 border-b border-border bg-surface flex items-center justify-between">
        <span className="text-sm text-text-secondary font-mono">{filename}</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon-sm" onClick={handleCopy}>
            {copied ? (
              <Check className="h-4 w-4 text-status-success" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
          <Button variant="secondary" size="sm" onClick={onDownload}>
            <Download className="h-4 w-4 mr-2" />
            Download
          </Button>
        </div>
      </div>

      {/* Code */}
      <ScrollArea className="flex-1 bg-surface">
        <pre className="p-4 text-sm leading-relaxed">
          <code>
            <table className="border-collapse">
              <tbody>
                {lines.map((line, index) => (
                  <tr key={index} className="hover:bg-surface-hover">
                    <td className="pr-4 text-text-muted select-none text-right align-top font-mono text-xs w-12">
                      {index + 1}
                    </td>
                    <td>
                      <span
                        dangerouslySetInnerHTML={{
                          __html:
                            hljs.highlight(line || ' ', {
                              language: 'python',
                              ignoreIllegals: true,
                            }).value || ' ',
                        }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </code>
        </pre>
      </ScrollArea>
    </div>
  )
}

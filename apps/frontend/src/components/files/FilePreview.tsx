'use client'

import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { CSVPreview } from './CSVPreview'
import { PythonPreview } from './PythonPreview'
import { JupyterPreview } from './JupyterPreview'
import { useFileContent } from '@/hooks/useArtifacts'
import {
  isPythonFile,
  isCSVFile,
  isJupyterNotebook,
  isTextFile,
  isImageFile,
} from '@/hooks/useArtifacts'
import { apiClient } from '@/lib/api/client'
import { getApiBaseUrl } from '@/lib/api/base-url'

interface FilePreviewProps {
  sessionId: string
  filePath: string
}

export function FilePreview({ sessionId, filePath }: FilePreviewProps) {
  const { data: content, isLoading, error } = useFileContent(sessionId, filePath)
  const filename = filePath.split('/').pop() || ''

  const handleDownload = async () => {
    try {
      const response = await apiClient.getFile(sessionId, filePath)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download file:', err)
    }
  }

  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-text-muted p-4">
        <p className="mb-4">Failed to load file preview</p>
        <Button variant="secondary" size="sm" onClick={handleDownload}>
          <Download className="h-4 w-4 mr-2" />
          Download File
        </Button>
      </div>
    )
  }

  // Image preview
  if (isImageFile(filename)) {
    return (
      <div className="h-full flex flex-col">
        <div className="flex-1 flex items-center justify-center p-4 bg-surface">
          {/* Artifact previews can be arbitrary local files, so a plain img is the most reliable option here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${getApiBaseUrl()}/api/sessions/${sessionId}/file?file_path=${encodeURIComponent(filePath)}`}
            alt={filename}
            className="max-w-full max-h-full object-contain"
          />
        </div>
        <div className="p-3 border-t border-border flex justify-end">
          <Button variant="secondary" size="sm" onClick={handleDownload}>
            <Download className="h-4 w-4 mr-2" />
            Download
          </Button>
        </div>
      </div>
    )
  }

  // CSV preview
  if (isCSVFile(filename) && content) {
    return <CSVPreview content={content} filename={filename} onDownload={handleDownload} />
  }

  // Python file preview
  if (isPythonFile(filename) && content) {
    return <PythonPreview content={content} filename={filename} onDownload={handleDownload} />
  }

  // Jupyter notebook preview
  if (isJupyterNotebook(filename) && content) {
    return <JupyterPreview content={content} filename={filename} onDownload={handleDownload} />
  }

  // Text file preview
  if (isTextFile(filename) && content) {
    return (
      <div className="h-full flex flex-col">
        <ScrollArea className="flex-1">
          <pre className="p-4 text-sm font-mono text-text-primary whitespace-pre-wrap">
            {content}
          </pre>
        </ScrollArea>
        <div className="p-3 border-t border-border flex justify-end">
          <Button variant="secondary" size="sm" onClick={handleDownload}>
            <Download className="h-4 w-4 mr-2" />
            Download
          </Button>
        </div>
      </div>
    )
  }

  // Binary or unknown file type
  return (
    <div className="h-full flex flex-col items-center justify-center text-text-muted p-4">
      <p className="mb-4">Preview not available for this file type</p>
      <Button variant="secondary" size="sm" onClick={handleDownload}>
        <Download className="h-4 w-4 mr-2" />
        Download File
      </Button>
    </div>
  )
}

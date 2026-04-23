'use client'

import { Download, RefreshCw } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { FileTree } from './FileTree'
import { FilePreview } from './FilePreview'
import { useUIStore } from '@/stores/useUIStore'
import { useSessionStore } from '@/stores/useSessionStore'
import { useArtifacts } from '@/hooks/useArtifacts'
import { apiClient } from '@/lib/api/client'

export function FileExplorerDialog() {
  const { fileExplorerOpen, closeFileExplorer, filePreviewPath, setFilePreviewPath } = useUIStore()
  const { currentSessionId } = useSessionStore()
  // Only poll when dialog is open
  const { data: artifacts, isLoading, refetch } = useArtifacts(currentSessionId, fileExplorerOpen)

  const handleDownloadAll = () => {
    if (currentSessionId) {
      window.open(apiClient.getArchiveUrl(currentSessionId), '_blank')
    }
  }

  return (
    <Dialog open={fileExplorerOpen} onOpenChange={(open) => !open && closeFileExplorer()}>
      <DialogContent className="max-w-5xl h-[80vh] flex flex-col p-0">
        <DialogHeader className="border-b border-border px-6 py-4 pr-16">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-3">
              <span>File Explorer</span>
              {currentSessionId && (
                <span className="text-sm font-mono text-text-muted">
                  {currentSessionId.slice(0, 8)}
                </span>
              )}
            </DialogTitle>
            <div className="flex flex-shrink-0 items-center gap-2">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => refetch()}
                disabled={isLoading}
              >
                <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={handleDownloadAll}
                disabled={!artifacts}
              >
                <Download className="h-4 w-4 mr-2" />
                Download All
              </Button>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 flex min-h-0">
          {/* File Tree Panel */}
          <div className="w-72 border-r border-border flex flex-col">
            <div className="px-4 py-2 border-b border-border">
              <p className="text-xs text-text-muted uppercase tracking-wider">Files</p>
            </div>
            <ScrollArea className="flex-1">
              <div className="p-2">
                {isLoading ? (
                  <div className="space-y-2 p-2">
                    {[...Array(5)].map((_, i) => (
                      <div key={i} className="h-8 rounded bg-surface animate-pulse" />
                    ))}
                  </div>
                ) : artifacts ? (
                  <FileTree
                    node={artifacts}
                    selectedPath={filePreviewPath}
                    onSelect={setFilePreviewPath}
                  />
                ) : (
                  <p className="text-sm text-text-muted text-center py-8">
                    No files yet
                  </p>
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Preview Panel */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="px-4 py-2 border-b border-border">
              <p className="text-xs text-text-muted uppercase tracking-wider">
                {filePreviewPath ? filePreviewPath.split('/').pop() : 'Preview'}
              </p>
            </div>
            <div className="flex-1 overflow-hidden">
              {filePreviewPath ? (
                <FilePreview
                  sessionId={currentSessionId!}
                  filePath={filePreviewPath}
                />
              ) : (
                <div className="h-full flex items-center justify-center text-text-muted">
                  <p>Select a file to preview</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

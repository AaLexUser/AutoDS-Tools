'use client'

import { format } from 'date-fns'
import {
  FolderOpen,
  Database,
  Package,
  Download,
  Loader2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils/cn'
import { useSessionStore } from '@/stores/useSessionStore'
import { useUIStore } from '@/stores/useUIStore'
import { useSession } from '@/hooks/useSessions'
import { apiClient } from '@/lib/api/client'

export function Header() {
  const { currentSessionId, status, isStreaming } = useSessionStore()
  const {
    openFileExplorer,
    openDatasetManager,
    openLibraryInstaller,
  } = useUIStore()
  const { data: session } = useSession(currentSessionId)

  const handleDownloadArtifacts = () => {
    if (currentSessionId) {
      window.open(apiClient.getArchiveUrl(currentSessionId), '_blank')
    }
  }

  const statusColors = {
    idle: 'bg-text-muted',
    connecting: 'bg-status-warning animate-pulse',
    streaming: 'bg-status-success animate-pulse',
    cancelling: 'bg-status-warning animate-pulse',
    error: 'bg-status-error',
  }

  return (
    <header className="relative z-10 h-14 flex items-center justify-between px-4 border-b border-border bg-background-secondary/50 backdrop-blur-sm">
      {/* Left: Session Info */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className={cn('h-2 w-2 rounded-full', statusColors[status])} />
          {currentSessionId ? (
            <div>
              <p className="font-mono text-sm text-text-primary">
                {currentSessionId.slice(0, 8)}
              </p>
              {session && (
                <p className="text-2xs text-text-muted">
                  Created {format(new Date(session.created_at), 'MMM d, HH:mm')}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-text-muted">No session selected</p>
          )}
        </div>

        {isStreaming && (
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-accent/10 border border-accent/30">
            <Loader2 className="h-3 w-3 text-accent animate-spin" />
            <span className="text-2xs text-accent font-medium">Running</span>
          </div>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={openFileExplorer}
                disabled={!currentSessionId}
              >
                <FolderOpen className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>File Explorer</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={openDatasetManager}
              >
                <Database className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Datasets</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={openLibraryInstaller}
                disabled={!currentSessionId}
              >
                <Package className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Install Libraries</TooltipContent>
          </Tooltip>

          <Separator orientation="vertical" className="h-6 mx-1" />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={handleDownloadArtifacts}
                disabled={!currentSessionId}
              >
                <Download className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download All Files</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </header>
  )
}

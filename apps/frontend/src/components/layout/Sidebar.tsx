'use client'

import { useState } from 'react'
import { format } from 'date-fns'
import {
  Plus,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils/cn'
import { formatBytes } from '@/lib/utils/format'
import { useSessions, useCreateSession, useDeleteSession } from '@/hooks/useSessions'
import { useSessionStore } from '@/stores/useSessionStore'
import { useUIStore } from '@/stores/useUIStore'
import type { Session } from '@/lib/api/client'

function SessionItem({
  session,
  isActive,
  onClick,
  onDelete,
  isDeleting,
}: {
  session: Session
  isActive: boolean
  onClick: () => void
  onDelete: () => void
  isDeleting: boolean
}) {
  const { sidebarCollapsed } = useUIStore()

  const shortId = session.id.slice(0, 8)
  const createdDate = new Date(session.created_at)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (window.confirm(`Delete session ${shortId} and all its files?`)) {
      onDelete()
    }
  }

  if (sidebarCollapsed) {
    return (
      <TooltipProvider>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>
            <button
              onClick={onClick}
              className={cn(
                'w-full flex items-center justify-center p-2 rounded-lg transition-all',
                isActive
                  ? 'bg-accent/10 text-accent border border-accent/30'
                  : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
              )}
            >
              <MessageSquare className="h-4 w-4" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p className="font-mono text-xs">{shortId}</p>
            <p className="text-2xs text-text-secondary">
              {format(createdDate, 'MMM d, HH:mm')} · {formatBytes(session.folder_size)}
            </p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return (
    <div
      className={cn(
        'w-full flex items-center gap-1 rounded-lg transition-all group',
        isActive
          ? 'bg-accent/10 text-text-primary border border-accent/30 shadow-glow-sm'
          : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover border border-transparent'
      )}
    >
      <button
        type="button"
        onClick={onClick}
        className="flex flex-1 items-center gap-3 p-3 min-w-0 text-left"
      >
        <MessageSquare className={cn('h-4 w-4 flex-shrink-0', isActive && 'text-accent')} />
        <div className="flex-1 text-left min-w-0">
          <p className="font-mono text-sm truncate">{shortId}</p>
          <p className="text-2xs text-text-muted">
            {format(createdDate, 'MMM d, HH:mm')} · {formatBytes(session.folder_size)}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={handleDelete}
        disabled={isDeleting}
        className={cn(
          'mr-2 p-1.5 rounded opacity-0 group-hover:opacity-100 transition-opacity',
          'hover:bg-red-500/20 hover:text-red-400',
          'disabled:opacity-50 disabled:cursor-not-allowed'
        )}
        title="Delete session"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export function Sidebar() {
  const { data: sessions, isLoading } = useSessions()
  const createSession = useCreateSession()
  const deleteSession = useDeleteSession()
  const currentSessionId = useSessionStore((state) => state.currentSessionId)
  const setCurrentSession = useSessionStore((state) => state.setCurrentSession)
  const { sidebarCollapsed, setSidebarCollapsed } = useUIStore()
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null)

  const handleNewSession = async () => {
    try {
      const newSession = await createSession.mutateAsync()
      // Only set session - useAgentWebSocket handles clearing messages on session change
      setCurrentSession(newSession.id)
    } catch (error) {
      console.error('Failed to create session:', error)
    }
  }

  const handleSelectSession = (session: Session) => {
    if (session.id !== currentSessionId) {
      // Only set session - useAgentWebSocket handles clearing messages on session change
      setCurrentSession(session.id)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      setDeletingSessionId(sessionId)
      await deleteSession.mutateAsync(sessionId)
      // Clear current session only after successful delete
      if (sessionId === currentSessionId) {
        setCurrentSession(null)
      }
    } catch (error) {
      console.error('Failed to delete session:', error)
    } finally {
      setDeletingSessionId(null)
    }
  }

  return (
    <div
      className={cn(
        'flex flex-col h-full bg-background-secondary border-r border-border transition-all duration-300',
        sidebarCollapsed ? 'w-16' : 'w-72'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border">
        {!sidebarCollapsed && (
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center">
              <span className="text-background font-bold text-sm">A</span>
            </div>
            <div>
              <h1 className="font-semibold text-text-primary text-sm">AutoDS</h1>
              <p className="text-2xs text-text-muted">Agent Interface</p>
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="text-text-secondary hover:text-text-primary"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* New Session Button */}
      <div className="p-3">
        {sidebarCollapsed ? (
          <TooltipProvider>
            <Tooltip delayDuration={0}>
              <TooltipTrigger asChild>
                <Button
                  onClick={handleNewSession}
                  disabled={createSession.isPending}
                  size="icon"
                  className="w-full"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">New Session</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : (
          <Button
            onClick={handleNewSession}
            disabled={createSession.isPending}
            className="w-full gap-2"
          >
            <Plus className="h-4 w-4" />
            New Session
          </Button>
        )}
      </div>

      {/* Sessions List */}
      <ScrollArea className="flex-1 px-3">
        <div className="space-y-1 pb-4">
          {!sidebarCollapsed && (
            <p className="text-2xs text-text-muted uppercase tracking-wider px-3 py-2">
              Sessions
            </p>
          )}
          {isLoading ? (
            <div className="space-y-2 px-1">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="h-14 rounded-lg bg-surface animate-pulse"
                />
              ))}
            </div>
          ) : sessions && sessions.length > 0 ? (
            sessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === currentSessionId}
                onClick={() => handleSelectSession(session)}
                onDelete={() => handleDeleteSession(session.id)}
                isDeleting={deletingSessionId === session.id}
              />
            ))
          ) : (
            !sidebarCollapsed && (
              <p className="text-sm text-text-muted text-center py-8">
                No sessions yet
              </p>
            )
          )}
        </div>
      </ScrollArea>

      {/* Footer */}
      {!sidebarCollapsed && (
        <div className="p-4 border-t border-border">
          <p className="text-2xs text-text-muted text-center">
            AutoDS v0.1.0
          </p>
        </div>
      )}
    </div>
  )
}

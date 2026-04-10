'use client'

import { useEffect, useRef } from 'react'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { ChatContainer } from '@/components/chat/ChatContainer'
import { FileExplorerDialog } from '@/components/files/FileExplorerDialog'
import { DatasetManagerDialog } from '@/components/datasets/DatasetManagerDialog'
import { LibraryInstallerDialog } from '@/components/settings/LibraryInstallerDialog'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useSessions, useCreateSession } from '@/hooks/useSessions'
import { useSessionStore } from '@/stores/useSessionStore'

export default function Home() {
  const { data: sessions, isLoading: isLoadingSessions } = useSessions()
  const createSession = useCreateSession()
  const currentSessionId = useSessionStore((state) => state.currentSessionId)
  const setCurrentSession = useSessionStore((state) => state.setCurrentSession)
  const initializedRef = useRef(false)

  // Auto-create or select session on startup
  useEffect(() => {
    if (isLoadingSessions || initializedRef.current) return

    // If no current session, try to use most recent or create new
    if (!currentSessionId) {
      initializedRef.current = true
      if (sessions && sessions.length > 0) {
        // Select most recent session
        setCurrentSession(sessions[0].id)
      } else if (!createSession.isPending) {
        // Create new session - useAgentWebSocket handles clearing messages on session change
        createSession.mutateAsync().then((newSession) => {
          setCurrentSession(newSession.id)
        }).catch(console.error)
      }
    }
  }, [isLoadingSessions, sessions, currentSessionId, setCurrentSession, createSession])

  return (
    <TooltipProvider>
      <div className="flex h-screen w-full bg-background noise-overlay">
        {/* Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main className="flex-1 overflow-hidden">
            <ChatContainer />
          </main>
        </div>

        {/* Dialogs */}
        <FileExplorerDialog />
        <DatasetManagerDialog />
        <LibraryInstallerDialog />
      </div>
    </TooltipProvider>
  )
}

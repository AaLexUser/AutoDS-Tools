'use client'

import { useEffect, useRef } from 'react'
import Link from 'next/link'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { ChatContainer } from '@/components/chat/ChatContainer'
import { FileExplorerDialog } from '@/components/files/FileExplorerDialog'
import { DatasetManagerDialog } from '@/components/datasets/DatasetManagerDialog'
import { LibraryInstallerDialog } from '@/components/settings/LibraryInstallerDialog'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useAuthState } from '@/hooks/useAuth'
import { useSessions, useCreateSession } from '@/hooks/useSessions'
import { apiClient } from '@/lib/api/client'
import { useSessionStore } from '@/stores/useSessionStore'

export default function Home() {
  const { data: authState, isLoading: isLoadingAuth } = useAuthState()
  const authMode = authState?.mode ?? 'disabled'
  const isApproved = !isLoadingAuth && (
    authMode === 'disabled' || authState?.user?.status === 'approved'
  )
  const {
    data: sessions,
    isLoading: isLoadingSessions,
    isError: isSessionsError,
  } = useSessions(isApproved)
  const createSession = useCreateSession()
  const currentSessionId = useSessionStore((state) => state.currentSessionId)
  const setCurrentSession = useSessionStore((state) => state.setCurrentSession)
  const initializedRef = useRef(false)

  // Auto-create or select session on startup
  useEffect(() => {
    if (!isApproved || isLoadingAuth || isLoadingSessions || isSessionsError || initializedRef.current) return

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
  }, [isApproved, isLoadingAuth, isLoadingSessions, isSessionsError, sessions, currentSessionId, setCurrentSession, createSession])

  if (isLoadingAuth) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background">
        <p className="text-sm text-text-muted">Loading authentication...</p>
      </div>
    )
  }

  if (authMode === 'workos' && !authState?.authenticated) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background px-6">
        <div className="max-w-md space-y-4 rounded-xl border border-border bg-background-secondary p-8 text-center">
          <h1 className="text-xl font-semibold text-text-primary">Sign in required</h1>
          <p className="text-sm text-text-muted">
            Authenticate with WorkOS before you can access AutoDS.
          </p>
          <Button onClick={() => { window.location.href = apiClient.getLoginUrl() }}>
            Continue to Sign In
          </Button>
        </div>
      </div>
    )
  }

  if (authMode === 'workos' && authState?.user?.status === 'pending') {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background px-6">
        <div className="max-w-md space-y-4 rounded-xl border border-border bg-background-secondary p-8 text-center">
          <h1 className="text-xl font-semibold text-text-primary">Waiting for approval</h1>
          <p className="text-sm text-text-muted">
            Your account is authenticated but cannot use AutoDS until an administrator approves it.
          </p>
        </div>
      </div>
    )
  }

  if (authMode === 'workos' && authState?.user?.status === 'disabled') {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-background px-6">
        <div className="max-w-md space-y-4 rounded-xl border border-border bg-background-secondary p-8 text-center">
          <h1 className="text-xl font-semibold text-text-primary">Access disabled</h1>
          <p className="text-sm text-text-muted">
            Your account is disabled. Contact an administrator if this is unexpected.
          </p>
        </div>
      </div>
    )
  }

  return (
    <TooltipProvider>
      <div className="flex h-screen w-full bg-background noise-overlay">
        {/* Sidebar */}
        <Sidebar />

        {/* Main Content */}
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          {authMode === 'workos' && authState?.user?.is_admin && (
            <div className="border-b border-border bg-background-secondary/40 px-4 py-2 text-xs text-text-muted">
              <Link href="/admin/users" className="underline underline-offset-4">
                Admin: manage user approvals
              </Link>
            </div>
          )}
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

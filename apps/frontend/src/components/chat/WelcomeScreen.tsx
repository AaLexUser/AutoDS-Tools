'use client'

import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCreateSession } from '@/hooks/useSessions'
import { useSessionStore } from '@/stores/useSessionStore'

export function WelcomeScreen() {
  const createSession = useCreateSession()
  const setCurrentSession = useSessionStore(state => state.setCurrentSession)

  const handleCreateSession = async () => {
    try {
      const newSession = await createSession.mutateAsync()
      setCurrentSession(newSession.id)
    } catch (error) {
      console.error('Failed to create session:', error)
    }
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center p-8">
      <div className="space-y-6 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-accent/20 to-accent/5 border border-accent/20">
          <span className="text-2xl font-bold text-accent">A</span>
        </div>

        <div>
          <h1 className="text-2xl font-semibold text-text-primary">
            AutoDS Agent
          </h1>
          <p className="mt-2 text-text-secondary">
            Your autonomous data science assistant
          </p>
        </div>

        <Button
          size="xl"
          onClick={handleCreateSession}
          disabled={createSession.isPending}
        >
          <Plus className="mr-2 h-4 w-4" />
          New Session
        </Button>
      </div>
    </div>
  )
}

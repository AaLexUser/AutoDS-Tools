'use client'

import { Plus, Zap, Database, Code } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCreateSession } from '@/hooks/useSessions'
import { useSessionStore } from '@/stores/useSessionStore'

export function WelcomeScreen() {
  const createSession = useCreateSession()
  const setCurrentSession = useSessionStore((state) => state.setCurrentSession)

  const handleCreateSession = async () => {
    try {
      const newSession = await createSession.mutateAsync()
      // Only set session - useAgentWebSocket handles clearing messages on session change
      setCurrentSession(newSession.id)
    } catch (error) {
      console.error('Failed to create session:', error)
    }
  }

  const features = [
    {
      icon: Zap,
      title: 'Autonomous Execution',
      description: 'Runs complete data science workflows without manual intervention',
    },
    {
      icon: Database,
      title: 'Data Processing',
      description: 'Handles data exploration, cleaning, and feature engineering',
    },
    {
      icon: Code,
      title: 'Model Training',
      description: 'Builds, trains, and evaluates machine learning models',
    },
  ]

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        {/* Logo */}
        <div className="mb-8">
          <div className="h-20 w-20 mx-auto rounded-2xl bg-gradient-to-br from-accent to-accent-muted flex items-center justify-center shadow-glow">
            <span className="text-background font-bold text-3xl">A</span>
          </div>
        </div>

        {/* Title */}
        <h1 className="text-3xl font-bold text-text-primary mb-3">
          AutoDS Agent
        </h1>
        <p className="text-lg text-text-secondary mb-8">
          Your autonomous data science assistant powered by LLM
        </p>

        {/* CTA Button */}
        <Button
          size="xl"
          onClick={handleCreateSession}
          disabled={createSession.isPending}
          className="mb-12"
        >
          <Plus className="h-5 w-5 mr-2" />
          Start New Session
        </Button>

        {/* Features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="p-6 rounded-xl bg-surface border border-border-subtle hover:border-border transition-colors"
            >
              <div className="h-10 w-10 rounded-lg bg-accent/10 flex items-center justify-center mb-4 mx-auto">
                <feature.icon className="h-5 w-5 text-accent" />
              </div>
              <h3 className="font-medium text-text-primary mb-2">
                {feature.title}
              </h3>
              <p className="text-sm text-text-secondary">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

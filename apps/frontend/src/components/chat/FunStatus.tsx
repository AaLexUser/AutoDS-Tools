'use client'

import { useState, useEffect, useCallback } from 'react'
import { cn } from '@/lib/utils/cn'

const FUNNY_PHRASES = [
  'Simmering…',
  'Brewing insights…',
  'Stirring the data pot…',
  'Following the breadcrumbs…',
  'Untangling the spaghetti…',
  'Chasing wild hypotheses…',
  'Diving down rabbit holes…',
  'Polishing the crystal ball…',
  'Coaxing numbers to talk…',
  'Herding cats (and datasets)…',
  'Waking up the neurons…',
  'Consulting the data spirits…',
  'Connecting the dots…',
  'Chasing patterns in the chaos…',
  'Mining for golden nuggets…',
  'Pondering the meaning of variance…',
  'Weaving a narrative…',
  'Summoning statistical wisdom…',
  'Befriending the outliers…',
  'Teaching computers to think…',
  'Distilling pure knowledge…',
  'Hunting for correlations…',
  'Wrestling with the algorithm…',
  'Waiting for inspiration to strike…',
  'Baking fresh insights…',
  'Calibrating the intuition engine…',
  'Peering into the data abyss…',
  'Deciphering the secret codes…',
  'Orchestrating the bits…',
  'Making magic happen…',
]

interface FunStatusProps {
  className?: string
  size?: 'sm' | 'md'
  active?: boolean
}

// Animated pulsing dots indicator
function PulsingDots({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const dotSize = size === 'sm' ? 'w-1 h-1' : 'w-1.5 h-1.5'
  const gap = size === 'sm' ? 'gap-0.5' : 'gap-1'

  return (
    <div className={cn('flex items-center', gap)}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            dotSize,
            'rounded-full bg-accent',
            'animate-pulse',
          )}
          style={{
            animationDelay: `${i * 500}ms`,
            animationDuration: '10s',
          }}
        />
      ))}
    </div>
  )
}

// Get a random index different from the current one
function getRandomIndex(length: number, exclude?: number): number {
  let idx = Math.floor(Math.random() * length)
  while (exclude !== undefined && idx === exclude && length > 1) {
    idx = Math.floor(Math.random() * length)
  }
  return idx
}

export function FunStatus({ className, size = 'md', active = true }: FunStatusProps) {
  const [index, setIndex] = useState(() => getRandomIndex(FUNNY_PHRASES.length))

  // Pick a new random phrase when active
  const rotateMessage = useCallback(() => {
    if (!active) return
    setIndex(prev => getRandomIndex(FUNNY_PHRASES.length, prev))
  }, [active])

  useEffect(() => {
    if (!active) return
    const interval = setInterval(rotateMessage, 6000)
    return () => clearInterval(interval)
  }, [rotateMessage, active])

  // Don't render anything when not active
  if (!active) return null

  const current = FUNNY_PHRASES[index]

  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <PulsingDots size={size} />
      <span
        className={cn(
          'text-accent font-medium transition-all duration-500 ease-in-out',
          size === 'sm' ? 'text-xs' : 'text-sm'
        )}
      >
        {current}
      </span>
    </div>
  )
}

// Static messages for InputArea placeholder
export const FUN_PLACEHOLDERS = [
  'Simmering your request…',
  'Brewing fresh insights…',
  'Following the data trail…',
  'Untangling complexity…',
  'Polishing findings…',
  'Consulting the data spirits…',
  'Mining for golden nuggets…',
  'Herding datasets…',
]

export function getRandomPlaceholder(): string {
  return FUN_PLACEHOLDERS[Math.floor(Math.random() * FUN_PLACEHOLDERS.length)]
}

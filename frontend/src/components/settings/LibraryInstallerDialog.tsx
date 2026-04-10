'use client'

import { useState } from 'react'
import { Package, Plus, X, Loader2, AlertCircle, CheckCircle } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useUIStore } from '@/stores/useUIStore'
import { useSessionStore } from '@/stores/useSessionStore'
import { useInstallLibraries } from '@/hooks/useDatasets'

const SUGGESTED_LIBRARIES = [
  { name: 'pandas', description: 'Data manipulation and analysis' },
  { name: 'numpy', description: 'Numerical computing' },
  { name: 'scikit-learn', description: 'Machine learning' },
  { name: 'matplotlib', description: 'Data visualization' },
  { name: 'seaborn', description: 'Statistical visualization' },
  { name: 'xgboost', description: 'Gradient boosting' },
  { name: 'lightgbm', description: 'Light gradient boosting' },
  { name: 'torch', description: 'Deep learning (PyTorch)' },
  { name: 'lightautoml[all]', description: 'AutoML framework' },
  { name: 'replay-rec[spark]', description: 'Recommendation system library' },
  { name: 'tsururu', description: 'Time series forecasting' },
  { name: 'pytorch-lifestream', description: 'Sequence/event prediction' },
]

export function LibraryInstallerDialog() {
  const { libraryInstallerOpen, closeLibraryInstaller } = useUIStore()
  const { currentSessionId } = useSessionStore()
  const installLibraries = useInstallLibraries()

  const [libraries, setLibraries] = useState<string[]>([])
  const [inputValue, setInputValue] = useState('')
  const [status, setStatus] = useState<'idle' | 'installing' | 'success' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  const handleAddLibrary = (lib?: string) => {
    const libName = (lib || inputValue).trim().toLowerCase()
    if (libName && !libraries.includes(libName)) {
      setLibraries([...libraries, libName])
      setInputValue('')
    }
  }

  const handleRemoveLibrary = (lib: string) => {
    setLibraries(libraries.filter((l) => l !== lib))
  }

  const handleInstall = async () => {
    if (!currentSessionId || libraries.length === 0) return

    setStatus('installing')
    setError(null)

    try {
      await installLibraries.mutateAsync({
        sessionId: currentSessionId,
        libraries,
      })
      setStatus('success')
      setTimeout(() => {
        setLibraries([])
        setStatus('idle')
      }, 2000)
    } catch {
      setStatus('error')
      setError('Failed to install libraries. Please try again.')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddLibrary()
    }
  }

  return (
    <Dialog open={libraryInstallerOpen} onOpenChange={(open) => !open && closeLibraryInstaller()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Package className="h-5 w-5 text-accent" />
            Install Libraries
          </DialogTitle>
          <DialogDescription>
            Install Python libraries to the session&apos;s virtual environment before running the agent.
          </DialogDescription>
        </DialogHeader>

        {/* Input */}
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter library name (e.g., pandas)"
            className="flex-1"
          />
          <Button onClick={() => handleAddLibrary()} disabled={!inputValue.trim()}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        {/* Suggested Libraries */}
        <div>
          <p className="text-2xs text-text-muted uppercase tracking-wider mb-2">
            Suggested Libraries
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_LIBRARIES.filter((lib) => !libraries.includes(lib.name)).map((lib) => (
              <button
                key={lib.name}
                onClick={() => handleAddLibrary(lib.name)}
                className="px-2.5 py-1 rounded-full text-xs bg-surface border border-border hover:border-accent hover:text-accent transition-colors"
                title={lib.description}
              >
                {lib.name}
              </button>
            ))}
          </div>
        </div>

        {/* Selected Libraries */}
        {libraries.length > 0 && (
          <div>
            <p className="text-2xs text-text-muted uppercase tracking-wider mb-2">
              To Install ({libraries.length})
            </p>
            <ScrollArea className="max-h-32">
              <div className="flex flex-wrap gap-2">
                {libraries.map((lib) => (
                  <div
                    key={lib}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent/10 border border-accent/30 text-sm"
                  >
                    <span className="text-accent">{lib}</span>
                    <button
                      onClick={() => handleRemoveLibrary(lib)}
                      className="text-accent/60 hover:text-accent"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Status Messages */}
        {status === 'installing' && (
          <div className="flex items-center gap-2 text-sm text-accent bg-accent/10 rounded-lg px-3 py-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Installing libraries...</span>
          </div>
        )}

        {status === 'success' && (
          <div className="flex items-center gap-2 text-sm text-status-success bg-status-success/10 rounded-lg px-3 py-2">
            <CheckCircle className="h-4 w-4" />
            <span>Libraries installed successfully!</span>
          </div>
        )}

        {status === 'error' && error && (
          <div className="flex items-center gap-2 text-sm text-status-error bg-status-error/10 rounded-lg px-3 py-2">
            <AlertCircle className="h-4 w-4" />
            <span>{error}</span>
          </div>
        )}

        {/* Install Button */}
        <div className="flex justify-end gap-2 mt-2">
          <Button variant="secondary" onClick={closeLibraryInstaller}>
            Cancel
          </Button>
          <Button
            onClick={handleInstall}
            disabled={libraries.length === 0 || status === 'installing' || !currentSessionId}
          >
            {status === 'installing' ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Installing...
              </>
            ) : (
              <>
                <Package className="h-4 w-4 mr-2" />
                Install {libraries.length > 0 ? `(${libraries.length})` : ''}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

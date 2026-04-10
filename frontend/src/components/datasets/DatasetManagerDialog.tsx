'use client'

import { useState } from 'react'
import { Database, Plus, Trash2, Loader2, Link, RefreshCw, AlertCircle } from 'lucide-react'
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
import { cn } from '@/lib/utils/cn'
import { useUIStore } from '@/stores/useUIStore'
import { useDatasets, useAddDataset, useDeleteDataset } from '@/hooks/useDatasets'

export function DatasetManagerDialog() {
  const { datasetManagerOpen, closeDatasetManager } = useUIStore()
  // Only fetch datasets when dialog is open
  const { data: datasets, isLoading, refetch } = useDatasets(datasetManagerOpen)
  const addDataset = useAddDataset()
  const deleteDataset = useDeleteDataset()

  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleAddDataset = async () => {
    if (!url.trim()) return

    // Basic GitHub URL validation
    if (!url.includes('github.com')) {
      setError('Please enter a valid GitHub repository URL')
      return
    }

    setError(null)

    try {
      await addDataset.mutateAsync(url)
      setUrl('')
    } catch {
      setError('Failed to add repository. Please try again.')
    }
  }

  const handleDeleteDataset = async (name: string) => {
    try {
      await deleteDataset.mutateAsync(name)
    } catch (err) {
      console.error('Failed to delete dataset:', err)
    }
  }

  return (
    <Dialog open={datasetManagerOpen} onOpenChange={(open) => !open && closeDatasetManager()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Database className="h-5 w-5 text-accent" />
            Dataset Manager
          </DialogTitle>
          <DialogDescription>
            Add GitHub repositories to index their API documentation for the agent to reference.
          </DialogDescription>
        </DialogHeader>

        {/* Add Repository Form */}
        <div className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Link className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="pl-10"
                onKeyDown={(e) => e.key === 'Enter' && handleAddDataset()}
              />
            </div>
            <Button
              onClick={handleAddDataset}
              disabled={addDataset.isPending || !url.trim()}
            >
              {addDataset.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              <span className="ml-2">Add</span>
            </Button>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-status-error">
              <AlertCircle className="h-4 w-4" />
              {error}
            </div>
          )}

          {addDataset.isPending && (
            <div className="flex items-center gap-2 text-sm text-accent bg-accent/10 rounded-lg px-3 py-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Indexing repository... This may take a few minutes.</span>
            </div>
          )}
        </div>

        {/* Datasets List */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm text-text-muted">
              Indexed Repositories ({datasets?.length || 0})
            </p>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => refetch()}
              disabled={isLoading}
            >
              <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
            </Button>
          </div>

          <ScrollArea className="h-64 rounded-lg border border-border">
            {isLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="h-12 rounded-lg bg-surface animate-pulse" />
                ))}
              </div>
            ) : datasets && datasets.length > 0 ? (
              <div className="p-2 space-y-1">
                {datasets.map((dataset) => (
                  <div
                    key={dataset.id}
                    className="flex items-center justify-between p-3 rounded-lg hover:bg-surface-hover transition-colors group"
                  >
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded bg-accent/10 flex items-center justify-center">
                        <Link className="h-4 w-4 text-accent" />
                      </div>
                      <div>
                        <p className="font-medium text-text-primary">{dataset.name}</p>
                        <p className="text-2xs text-text-muted font-mono">{dataset.id}</p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleDeleteDataset(dataset.name)}
                      disabled={deleteDataset.isPending}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-status-error hover:text-status-error hover:bg-status-error/10"
                    >
                      {deleteDataset.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-text-muted p-8">
                <Database className="h-8 w-8 mb-3 opacity-50" />
                <p className="text-sm">No repositories indexed yet</p>
                <p className="text-2xs mt-1">Add a GitHub repository above to get started</p>
              </div>
            )}
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  )
}

'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Send, Loader2, Paperclip, Square, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils/cn'
import {
  useCurrentSessionId,
  useIsStreaming,
  useSessionStatus,
  useSessionStore,
  type Message,
} from '@/stores/useSessionStore'
import { useSendMessage } from '@/hooks/useSessions'
import { useUploadFiles } from '@/hooks/useArtifacts'
import { apiClient } from '@/lib/api/client'
import { getRandomPlaceholder } from './FunStatus'

export function InputArea() {
  const [input, setInput] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentSessionId = useCurrentSessionId()
  const isStreaming = useIsStreaming()
  const status = useSessionStatus()

  const addMessage = useSessionStore(state => state.addMessage)
  const setStreaming = useSessionStore(state => state.setStreaming)
  const setStatus = useSessionStore(state => state.setStatus)

  const sendMessage = useSendMessage()
  const uploadFiles = useUploadFiles()

  const isCancelling = status === 'cancelling'
  const isDisabled =
    !currentSessionId ||
    isStreaming ||
    status === 'connecting' ||
    isCancelling

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`
    }
  }, [])

  useEffect(() => {
    adjustHeight()
  }, [input, adjustHeight])

  const handleCancel = useCallback(async () => {
    if (!currentSessionId) return
    try {
      await apiClient.cancelSession(currentSessionId)
    } catch (error) {
      console.error('Failed to cancel session:', error)
    }
  }, [currentSessionId])

  const handleSubmit = useCallback(async () => {
    if (!input.trim() || !currentSessionId || isStreaming) return

    const content = input.trim()
    setInput('')

    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    }
    addMessage(userMessage)

    if (files.length > 0) {
      try {
        await uploadFiles.mutateAsync({ sessionId: currentSessionId, files })
        setFiles([])
      } catch (error) {
        console.error('Failed to upload files:', error)
      }
    }

    try {
      setStreaming(true)
      setStatus('streaming')
      await sendMessage.mutateAsync({
        sessionId: currentSessionId,
        message: content,
      })
    } catch (error) {
      console.error('Failed to send message:', error)
      setStatus('error', 'Failed to send message')
      setStreaming(false)
    }
  }, [
    input,
    currentSessionId,
    isStreaming,
    files,
    addMessage,
    setStreaming,
    setStatus,
    sendMessage,
    uploadFiles,
  ])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = Array.from(e.target.files || [])
      setFiles(prev => [...prev, ...selected])
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
    [],
  )

  const removeFile = useCallback((index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }, [])

  const placeholder = useMemo(() => {
    if (isCancelling) return 'Cancelling…'
    if (status === 'connecting') return 'Reconnecting…'
    if (isStreaming) return getRandomPlaceholder()
    return 'Describe your data science task…'
  }, [isCancelling, isStreaming, status])

  return (
    <div className="space-y-2">
      <div
        className={cn(
          'overflow-hidden rounded-2xl border bg-surface transition-colors',
          isDisabled
            ? 'border-border opacity-60'
            : 'border-border focus-within:border-accent/40',
        )}
      >
        {/* Attached files */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {files.map((file, index) => (
              <div
                key={index}
                className="flex items-center gap-1.5 rounded-md bg-surface-elevated px-2 py-1 text-xs"
              >
                <Paperclip className="h-3 w-3 text-text-muted" />
                <span className="max-w-[120px] truncate text-text-primary">
                  {file.name}
                </span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="ml-0.5 text-text-muted hover:text-text-primary"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          className="block w-full min-h-[44px] max-h-[200px] resize-none bg-transparent px-4 py-3 text-sm text-text-primary placeholder:text-text-muted outline-none disabled:cursor-not-allowed"
        />

        {/* Bottom toolbar */}
        <div className="flex items-center justify-between px-3 pb-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isDisabled}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary disabled:opacity-50"
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <div className="flex items-center gap-2">
            <span className="hidden text-[10px] text-text-muted sm:inline">
              ↵ send · ⇧↵ newline
            </span>
            {isStreaming ? (
              <Button
                onClick={handleCancel}
                disabled={isCancelling}
                variant="destructive"
                size="icon"
                className="h-8 w-8 rounded-lg"
              >
                {isCancelling ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="h-3.5 w-3.5" />
                )}
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={isDisabled || !input.trim()}
                size="icon"
                className="h-8 w-8 rounded-lg"
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={handleFileSelect}
        accept=".csv,.txt,.md,.py,.json,.yaml,.yml"
      />
    </div>
  )
}

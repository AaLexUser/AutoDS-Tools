'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { AlertCircle, Check, Loader2, Paperclip, RotateCw, Send, Square, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils/cn'
import {
  useCurrentSessionId,
  useIsStreaming,
  useSessionStatus,
  useSessionStore,
  type Message,
} from '@/stores/useSessionStore'
import { useSendMessage } from '@/hooks/useSessions'
import { formatFileSize } from '@/hooks/useArtifacts'
import { useFileAttachments } from '@/hooks/useFileAttachments'
import { apiClient } from '@/lib/api/client'
import {
  ALLOWED_UPLOAD_ACCEPT,
  buildMessageWithUploads,
  isAllowedUpload,
  LARGE_FILE_CONFIRM_BYTES,
} from '@/lib/uploads'
import { getRandomPlaceholder } from './FunStatus'

export function InputArea() {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentSessionId = useCurrentSessionId()
  const isStreaming = useIsStreaming()
  const status = useSessionStatus()

  const addMessage = useSessionStore(state => state.addMessage)
  const setStreaming = useSessionStore(state => state.setStreaming)
  const setStatus = useSessionStore(state => state.setStatus)

  const sendMessage = useSendMessage()
  const {
    attachments,
    pendingLargeFiles,
    enqueueAttachments,
    stageLargeFilesForConfirm,
    confirmLargeFiles,
    cancelLargeFiles,
    removeAttachment,
    retryAttachment,
    clearAttachments,
    anyUploading,
    anyUploadError,
    allUploaded,
    uploadedFilenames,
  } = useFileAttachments(currentSessionId)

  const isCancelling = status === 'cancelling'
  const isDisabled =
    !currentSessionId ||
    isStreaming ||
    status === 'connecting' ||
    isCancelling

  const canSend =
    !isDisabled &&
    !anyUploading &&
    !anyUploadError &&
    pendingLargeFiles.length === 0 &&
    (input.trim().length > 0 || allUploaded)

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
    if (!canSend || !currentSessionId || isStreaming) return

    const content = buildMessageWithUploads(input, uploadedFilenames)
    setInput('')
    clearAttachments()

    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    }
    addMessage(userMessage)

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
    canSend,
    currentSessionId,
    isStreaming,
    input,
    uploadedFilenames,
    addMessage,
    setStreaming,
    setStatus,
    sendMessage,
    clearAttachments,
  ])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        void handleSubmit()
      }
    },
    [handleSubmit],
  )

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const selected = Array.from(e.target.files || [])
      if (selected.length === 0) return

      const allowed = selected.filter(file => isAllowedUpload(file.name))
      const immediate = allowed.filter(file => file.size < LARGE_FILE_CONFIRM_BYTES)
      const needsConfirm = allowed.filter(file => file.size >= LARGE_FILE_CONFIRM_BYTES)

      if (immediate.length > 0) {
        enqueueAttachments(immediate)
      }
      if (needsConfirm.length > 0) {
        stageLargeFilesForConfirm(needsConfirm)
      }

      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    },
    [enqueueAttachments, stageLargeFilesForConfirm],
  )

  const placeholder = useMemo(() => {
    if (isCancelling) return 'Cancelling…'
    if (status === 'connecting') return 'Reconnecting…'
    if (isStreaming) return getRandomPlaceholder()
    if (anyUploading) return 'Uploading files…'
    return 'Describe your data science task…'
  }, [isCancelling, isStreaming, status, anyUploading])

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
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-4 pt-3">
            {attachments.map(attachment => {
              const isUploading =
                attachment.status === 'uploading' || attachment.status === 'pending'

              return (
                <div
                  key={attachment.id}
                  className={cn(
                    'flex max-w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs',
                    attachment.status === 'error'
                      ? 'bg-destructive/10 text-destructive'
                      : 'bg-surface-elevated text-text-primary',
                  )}
                >
                  {attachment.status === 'uploaded' ? (
                    <Check className="h-3 w-3 shrink-0 text-emerald-500" />
                  ) : attachment.status === 'error' ? (
                    <AlertCircle className="h-3 w-3 shrink-0" />
                  ) : (
                    <Loader2 className="h-3 w-3 shrink-0 animate-spin text-text-muted" />
                  )}

                  <div className="min-w-0">
                    <div className="max-w-[160px] truncate">{attachment.file.name}</div>
                    <div className="text-[10px] text-text-muted">
                      {formatFileSize(attachment.file.size)}
                      {isUploading && attachment.progress > 0
                        ? ` · ${attachment.progress}%`
                        : ''}
                      {attachment.status === 'error' && attachment.error
                        ? ` · ${attachment.error}`
                        : ''}
                    </div>
                  </div>

                  {attachment.status === 'error' && (
                    <button
                      type="button"
                      onClick={() => retryAttachment(attachment.id)}
                      className="ml-0.5 text-text-muted hover:text-text-primary"
                      aria-label={`Retry upload for ${attachment.file.name}`}
                    >
                      <RotateCw className="h-3 w-3" />
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => removeAttachment(attachment.id)}
                    className="ml-0.5 text-text-muted hover:text-text-primary"
                    aria-label={`Remove ${attachment.file.name}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              )
            })}
          </div>
        )}

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
              {anyUploading
                ? 'Waiting for uploads…'
                : pendingLargeFiles.length > 0
                  ? 'Confirm large uploads…'
                  : '↵ send · ⇧↵ newline'}
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
                onClick={() => void handleSubmit()}
                disabled={!canSend}
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
        accept={ALLOWED_UPLOAD_ACCEPT}
      />

      <Dialog
        open={pendingLargeFiles.length > 0}
        onOpenChange={open => {
          if (!open) cancelLargeFiles()
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Upload large file{pendingLargeFiles.length > 1 ? 's' : ''}?</DialogTitle>
            <DialogDescription>
              {pendingLargeFiles.length === 1
                ? 'This file is at least 1 GB. Upload may take a while.'
                : `These ${pendingLargeFiles.length} files are at least 1 GB each. Uploads may take a while.`}
            </DialogDescription>
          </DialogHeader>

          <ul className="max-h-48 space-y-2 overflow-y-auto text-sm">
            {pendingLargeFiles.map(file => (
              <li
                key={`${file.name}-${file.size}-${file.lastModified}`}
                className="flex items-center justify-between gap-3 rounded-md bg-surface-elevated px-3 py-2"
              >
                <span className="truncate">{file.name}</span>
                <span className="shrink-0 text-text-muted">{formatFileSize(file.size)}</span>
              </li>
            ))}
          </ul>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={cancelLargeFiles}>
              Cancel
            </Button>
            <Button type="button" onClick={confirmLargeFiles}>
              Upload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

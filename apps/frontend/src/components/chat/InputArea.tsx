'use client'

import { useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { Send, Upload, Loader2, Paperclip, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils/cn'
import {
  useCurrentSessionId,
  useIsStreaming,
  useSessionStatus,
  useSessionStore,
  type Message
} from '@/stores/useSessionStore'
import { useSendMessage } from '@/hooks/useSessions'
import { useUploadFiles } from '@/hooks/useArtifacts'
import { apiClient } from '@/lib/api/client'

export function InputArea() {
  const [input, setInput] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Use optimized selectors
  const currentSessionId = useCurrentSessionId()
  const isStreaming = useIsStreaming()
  const status = useSessionStatus()

  // Get actions directly from store (stable references)
  const addMessage = useSessionStore((state) => state.addMessage)
  const setStreaming = useSessionStore((state) => state.setStreaming)
  const setStatus = useSessionStore((state) => state.setStatus)

  const sendMessage = useSendMessage()
  const uploadFiles = useUploadFiles()

  const isCancelling = status === 'cancelling'
  const isDisabled = !currentSessionId || isStreaming

  // Auto-resize textarea based on content
  const adjustTextareaHeight = useCallback(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [])

  // Adjust height when input changes
  useEffect(() => {
    adjustTextareaHeight()
  }, [input, adjustTextareaHeight])

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

    const messageContent = input.trim()
    setInput('')

    // Add user message to store
    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: messageContent,
      timestamp: new Date(),
    }
    addMessage(userMessage)

    // Upload any attached files first
    if (files.length > 0) {
      try {
        await uploadFiles.mutateAsync({
          sessionId: currentSessionId,
          files,
        })
        setFiles([])
      } catch (error) {
        console.error('Failed to upload files:', error)
      }
    }

    // Send message to agent
    try {
      setStreaming(true)
      setStatus('streaming')
      await sendMessage.mutateAsync({
        sessionId: currentSessionId,
        message: messageContent,
      })
    } catch (error) {
      console.error('Failed to send message:', error)
      setStatus('error', 'Failed to send message')
      setStreaming(false)
    }
  }, [input, currentSessionId, isStreaming, files, addMessage, setStreaming, setStatus, sendMessage, uploadFiles])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }, [handleSubmit])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || [])
    setFiles((prev) => [...prev, ...selectedFiles])
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [])

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const openFileDialog = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
  }, [])

  // Memoize placeholder text
  const placeholder = useMemo(() => {
    if (isCancelling) return 'Cancelling...'
    if (isStreaming) return 'Agent is working...'
    return 'Describe your data science task...'
  }, [isCancelling, isStreaming])

  return (
    <div className="space-y-3">
      {/* File attachments */}
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {files.map((file, index) => (
            <div
              key={index}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border text-sm"
            >
              <Paperclip className="h-3 w-3 text-text-muted" />
              <span className="text-text-primary truncate max-w-[150px]">
                {file.name}
              </span>
              <button
                onClick={() => removeFile(index)}
                className="text-text-muted hover:text-text-primary"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="flex items-end gap-3">
        {/* File upload button */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="secondary"
                size="icon"
                disabled={isDisabled}
                onClick={openFileDialog}
              >
                <Upload className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Upload files</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileSelect}
          accept=".csv,.txt,.md,.py,.json,.yaml,.yml"
        />

        {/* Message input */}
        <div className="flex-1 relative">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isDisabled}
            className={cn(
              'min-h-[48px] max-h-[200px] pr-12 resize-none',
              'bg-surface border-border focus:border-accent',
              isDisabled && 'opacity-50 cursor-not-allowed'
            )}
            rows={1}
          />
        </div>

        {/* Send/Stop button */}
        {isStreaming ? (
          <Button
            onClick={handleCancel}
            disabled={isCancelling}
            variant="destructive"
            size="icon"
            className="h-12 w-12"
          >
            {isCancelling ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Square className="h-4 w-4" />
            )}
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={isDisabled || !input.trim()}
            size="icon"
            className="h-12 w-12"
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Helper text */}
      <p className="text-2xs text-text-muted text-center">
        {isStreaming
          ? 'Click stop to interrupt the agent'
          : 'Press Enter to send, Shift+Enter for new line'}
      </p>
    </div>
  )
}

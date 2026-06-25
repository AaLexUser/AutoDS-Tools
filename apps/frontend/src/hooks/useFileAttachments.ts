'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'
import { isAllowedUpload, MAX_CONCURRENT_UPLOADS } from '@/lib/uploads'

export type AttachmentStatus = 'pending' | 'uploading' | 'uploaded' | 'error'

export interface Attachment {
  id: string
  file: File
  status: AttachmentStatus
  progress: number
  error?: string
}

function createAttachment(file: File): Attachment {
  return {
    id: crypto.randomUUID(),
    file,
    status: 'pending',
    progress: 0,
  }
}

export function useFileAttachments(sessionId: string | null) {
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [pendingLargeFiles, setPendingLargeFiles] = useState<File[]>([])
  const abortControllersRef = useRef(new Map<string, AbortController>())
  const uploadQueueRef = useRef<Attachment[]>([])
  const activeUploadsRef = useRef(0)
  const queryClient = useQueryClient()

  const hasAttachments = attachments.length > 0
  const anyUploading = attachments.some(
    attachment => attachment.status === 'uploading' || attachment.status === 'pending',
  )
  const anyUploadError = attachments.some(attachment => attachment.status === 'error')
  const allUploaded =
    hasAttachments && attachments.every(attachment => attachment.status === 'uploaded')
  const uploadedFilenames = attachments
    .filter(attachment => attachment.status === 'uploaded')
    .map(attachment => attachment.file.name)

  useEffect(() => {
    return () => {
      for (const controller of abortControllersRef.current.values()) {
        controller.abort()
      }
      abortControllersRef.current.clear()
    }
  }, [])

  useEffect(() => {
    for (const controller of abortControllersRef.current.values()) {
      controller.abort()
    }
    abortControllersRef.current.clear()
    uploadQueueRef.current = []
    activeUploadsRef.current = 0
    setAttachments([])
    setPendingLargeFiles([])
  }, [sessionId])

  const uploadAttachment = useCallback(
    async (attachment: Attachment) => {
      if (!sessionId) return

      if (!isAllowedUpload(attachment.file.name)) {
        setAttachments(prev =>
          prev.map(item =>
            item.id === attachment.id
              ? {
                  ...item,
                  status: 'error',
                  error: 'File type is not supported',
                }
              : item,
          ),
        )
        return
      }

      const controller = new AbortController()
      abortControllersRef.current.set(attachment.id, controller)

      setAttachments(prev =>
        prev.map(item =>
          item.id === attachment.id
            ? { ...item, status: 'uploading', progress: 0, error: undefined }
            : item,
        ),
      )

      try {
        await apiClient.uploadFile(
          sessionId,
          attachment.file,
          progress => {
            setAttachments(prev =>
              prev.map(item =>
                item.id === attachment.id ? { ...item, progress } : item,
              ),
            )
          },
          controller.signal,
        )

        abortControllersRef.current.delete(attachment.id)
        setAttachments(prev =>
          prev.map(item =>
            item.id === attachment.id
              ? { ...item, status: 'uploaded', progress: 100 }
              : item,
          ),
        )
        queryClient.invalidateQueries({ queryKey: ['artifacts', sessionId] })
      } catch (error) {
        abortControllersRef.current.delete(attachment.id)

        if (error instanceof DOMException && error.name === 'AbortError') {
          setAttachments(prev => prev.filter(item => item.id !== attachment.id))
          return
        }

        const message =
          error instanceof Error ? error.message : 'Failed to upload file'

        setAttachments(prev =>
          prev.map(item =>
            item.id === attachment.id
              ? { ...item, status: 'error', error: message }
              : item,
          ),
        )
      }
    },
    [sessionId, queryClient],
  )

  const processUploadQueue = useCallback(() => {
    if (!sessionId) return

    while (
      activeUploadsRef.current < MAX_CONCURRENT_UPLOADS &&
      uploadQueueRef.current.length > 0
    ) {
      const next = uploadQueueRef.current.shift()
      if (!next) break

      activeUploadsRef.current += 1
      void uploadAttachment(next).finally(() => {
        activeUploadsRef.current -= 1
        processUploadQueue()
      })
    }
  }, [sessionId, uploadAttachment])

  const enqueueAttachments = useCallback(
    (files: File[]) => {
      if (files.length === 0) return

      const newAttachments = files.map(createAttachment)
      setAttachments(prev => [...prev, ...newAttachments])
      uploadQueueRef.current.push(...newAttachments)
      processUploadQueue()
    },
    [processUploadQueue],
  )

  const removeAttachment = useCallback((attachmentId: string) => {
    uploadQueueRef.current = uploadQueueRef.current.filter(item => item.id !== attachmentId)

    const controller = abortControllersRef.current.get(attachmentId)
    if (controller) {
      controller.abort()
      abortControllersRef.current.delete(attachmentId)
    }

    setAttachments(prev => prev.filter(item => item.id !== attachmentId))
  }, [])

  const retryAttachment = useCallback(
    (attachmentId: string) => {
      const attachment = attachments.find(item => item.id === attachmentId)
      if (!attachment) return

      setAttachments(prev =>
        prev.map(item =>
          item.id === attachmentId
            ? { ...item, status: 'pending', progress: 0, error: undefined }
            : item,
        ),
      )

      const retryAttachmentState = { ...attachment, status: 'pending' as const, progress: 0 }
      uploadQueueRef.current.push(retryAttachmentState)
      processUploadQueue()
    },
    [attachments, processUploadQueue],
  )

  const clearAttachments = useCallback(() => {
    uploadQueueRef.current = []
    setAttachments([])
  }, [])

  const stageLargeFilesForConfirm = useCallback((files: File[]) => {
    if (files.length === 0) return
    setPendingLargeFiles(prev => [...prev, ...files])
  }, [])

  const confirmLargeFiles = useCallback(() => {
    enqueueAttachments(pendingLargeFiles)
    setPendingLargeFiles([])
  }, [enqueueAttachments, pendingLargeFiles])

  const cancelLargeFiles = useCallback(() => {
    setPendingLargeFiles([])
  }, [])

  return {
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
    hasAttachments,
    uploadedFilenames,
  }
}

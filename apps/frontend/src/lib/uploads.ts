export const ALLOWED_UPLOAD_EXTENSIONS = [
  '.csv',
  '.tsv',
  '.parquet',
  '.json',
  '.jsonl',
  '.md',
  '.txt',
  '.rst',
  '.yaml',
  '.yml',
  '.toml',
  '.py',
  '.ipynb',
] as const

export const ALLOWED_UPLOAD_ACCEPT = ALLOWED_UPLOAD_EXTENSIONS.join(',')

/** Prompt before uploading files at or above this size (1 GB). */
export const LARGE_FILE_CONFIRM_BYTES = 1024 * 1024 * 1024

/** Use chunked uploads at or above this size to avoid reverse-proxy body limits. */
export const CHUNKED_UPLOAD_THRESHOLD_BYTES = 64 * 1024 * 1024

/** Chunk size for large uploads (32 MB). */
export const UPLOAD_CHUNK_BYTES = 32 * 1024 * 1024

/** Maximum number of simultaneous upload requests (must match server-side session serialization). */
export const MAX_CONCURRENT_UPLOADS = 1

export const FILES_ONLY_MESSAGE = 'Please analyze the uploaded files.'

export function getUploadExtension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  if (dot === -1) return ''
  return filename.slice(dot).toLowerCase()
}

export function isAllowedUpload(filename: string): boolean {
  const ext = getUploadExtension(filename)
  return (ALLOWED_UPLOAD_EXTENSIONS as readonly string[]).includes(ext)
}

export function buildMessageWithUploads(text: string, uploadedFilenames: string[]): string {
  const trimmed = text.trim()
  const body = trimmed || (uploadedFilenames.length > 0 ? FILES_ONLY_MESSAGE : '')

  if (uploadedFilenames.length === 0) {
    return body
  }

  const fileList = uploadedFilenames.map(name => `- ${name}`).join('\n')
  return `${body}\n\nUploaded files:\n${fileList}`
}

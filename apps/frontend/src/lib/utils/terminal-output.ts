const ansiPattern = /\x1b\[[0-9;]*[mK]/g

export function stripAnsiCodes(content: string): string {
  return content.replace(ansiPattern, '')
}

export function looksLikeErrorOutput(content: string): boolean {
  return /traceback \(most recent call last\)|\b(error|exception)\b/i.test(content)
}

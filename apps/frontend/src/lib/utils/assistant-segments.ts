export interface ParsedAssistantSegment {
  type: 'text' | 'tool'
  content: string
  tool?: string
  attributes?: Record<string, string>
  presentation?: 'tool' | 'assistant-code'
}

export interface ParsedAssistantContent {
  segments: ParsedAssistantSegment[]
  hasToolSegments: boolean
  lastToolSegmentIndex: number
}

interface ParsedMatch {
  index: number
  length: number
  segment: ParsedAssistantSegment
}

const INVALID_TOOLS = new Set(['thinking', 'reasoning'])
const pairedTagPattern = /<([A-Za-z_][A-Za-z0-9_-]*)\b([^>]*)>([\s\S]*?)<\/\1>/gi
const selfClosingTagPattern = /<([A-Za-z_][A-Za-z0-9_-]*)\b([^>]*?)\s*\/>/gi
const attributePattern = /(\w+)=["']([^"']*)["']/g

function parseAttributes(rawAttributes: string | undefined): Record<string, string> {
  if (!rawAttributes) {
    return {}
  }

  const attributes: Record<string, string> = {}
  for (const match of rawAttributes.matchAll(attributePattern)) {
    attributes[match[1]] = match[2]
  }
  return attributes
}

function normalizeBlockContent(content: string): string {
  const trimmed = content.replace(/^\s*\n/, '').replace(/\n\s*$/, '')
  if (!trimmed) {
    return ''
  }

  const lines = trimmed.split('\n')
  const indentation = lines
    .filter(line => line.trim())
    .map(line => line.match(/^\s*/)?.[0].length ?? 0)
  const commonIndent = indentation.length ? Math.min(...indentation) : 0

  if (commonIndent === 0) {
    return trimmed
  }

  return lines.map(line => line.slice(commonIndent)).join('\n')
}

function buildPairedMatches(content: string): ParsedMatch[] {
  const matches: ParsedMatch[] = []

  for (const match of content.matchAll(pairedTagPattern)) {
    const index = match.index ?? 0
    const tag = match[1]
    const rawAttributes = match[2]
    const body = match[3]
    const tagLower = tag.toLowerCase()

    if (INVALID_TOOLS.has(tagLower)) {
      continue
    }

    const attributes = parseAttributes(rawAttributes)
    const normalizedBody = normalizeBlockContent(body)

    if (tagLower === 'codeblock' && normalizedBody) {
      const language = (attributes.lang || attributes.language || 'text').toLowerCase()
      matches.push({
        index,
        length: match[0].length,
        segment: {
          type: 'tool',
          tool: language,
          content: normalizedBody,
          attributes: {
            ...attributes,
            arg: normalizedBody,
          },
          presentation: 'assistant-code',
        },
      })
      continue
    }

    matches.push({
      index,
      length: match[0].length,
      segment: {
        type: 'tool',
        tool: tag,
        content: normalizedBody || match[0],
        attributes,
        presentation: 'tool',
      },
    })
  }

  return matches
}

function buildSelfClosingMatches(content: string): ParsedMatch[] {
  const matches: ParsedMatch[] = []

  for (const match of content.matchAll(selfClosingTagPattern)) {
    const index = match.index ?? 0
    const tag = match[1]
    const rawAttributes = match[2]
    const tagLower = tag.toLowerCase()

    if (INVALID_TOOLS.has(tagLower)) {
      continue
    }

    const attributes = parseAttributes(rawAttributes)
    matches.push({
      index,
      length: match[0].length,
      segment: {
        type: 'tool',
        tool: tag,
        content: match[0],
        attributes,
        presentation: 'tool',
      },
    })
  }

  return matches
}

export function parseAssistantSegments(content: string): ParsedAssistantSegment[] {
  const matches = [...buildPairedMatches(content), ...buildSelfClosingMatches(content)].sort(
    (left, right) => left.index - right.index
  )
  const segments: ParsedAssistantSegment[] = []
  let cursor = 0

  for (const match of matches) {
    if (match.index < cursor) {
      continue
    }

    if (match.index > cursor) {
      segments.push({
        type: 'text',
        content: content.slice(cursor, match.index),
      })
    }

    segments.push(match.segment)
    cursor = match.index + match.length
  }

  if (cursor < content.length) {
    segments.push({
      type: 'text',
      content: content.slice(cursor),
    })
  }

  return segments
}

export function parseAssistantContent(content: string): ParsedAssistantContent {
  const segments = parseAssistantSegments(content)
  const lastToolSegmentIndex = segments.reduce(
    (lastIndex, segment, index) => (segment.type === 'tool' ? index : lastIndex),
    -1,
  )

  return {
    segments,
    hasToolSegments: lastToolSegmentIndex >= 0,
    lastToolSegmentIndex,
  }
}

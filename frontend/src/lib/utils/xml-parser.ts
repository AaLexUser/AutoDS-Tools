export interface ParsedToolSegment {
  type: 'text' | 'tool'
  content: string
  tool?: string
  attributes?: Record<string, string>
}

const blockPattern =
  /<(shell|jupyter|ipython|codeblocks|fileblocks|todo)(\s+[^>]*)?>([\s\S]*?)<\/\1>|<(submit)(\s+[^>]*)?\/>/gi

const attributePattern = /(\w+)="([^"]*)"/g

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

export function parseToolCalls(content: string): ParsedToolSegment[] {
  const segments: ParsedToolSegment[] = []
  let cursor = 0

  for (const match of content.matchAll(blockPattern)) {
    const index = match.index ?? 0
    if (index > cursor) {
      segments.push({
        type: 'text',
        content: content.slice(cursor, index),
      })
    }

    const tool = match[1] ?? match[4]
    const rawAttributes = match[2] ?? match[5]
    const toolContent = (match[3] ?? '').trim()
    const attributes = parseAttributes(rawAttributes)

    segments.push({
      type: 'tool',
      tool,
      content: toolContent || match[0],
      attributes,
    })

    cursor = index + match[0].length
  }

  if (cursor < content.length) {
    segments.push({
      type: 'text',
      content: content.slice(cursor),
    })
  }

  return segments
}

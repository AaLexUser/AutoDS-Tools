import type { Message } from '../../stores/useSessionStore'
import { parseAssistantContent, type ParsedAssistantContent } from './assistant-segments'

export interface ChatRenderItem {
  message: Message
  assistantContent?: ParsedAssistantContent
  attachedEnvironment?: Message
}

export function buildChatRenderItems(messages: Message[]): ChatRenderItem[] {
  const items: ChatRenderItem[] = []

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]
    const nextMessage = messages[index + 1]
    const assistantContent =
      message.role === 'assistant'
        ? parseAssistantContent(message.content)
        : undefined

    if (
      message.role === 'assistant' &&
      nextMessage?.role === 'environment' &&
      assistantContent?.hasToolSegments
    ) {
      items.push({
        message,
        assistantContent,
        attachedEnvironment: nextMessage,
      })
      index += 1
      continue
    }

    if (message.role === 'environment') {
      continue
    }

    items.push({ message, assistantContent })
  }

  return items
}

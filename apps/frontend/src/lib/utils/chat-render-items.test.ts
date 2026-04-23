import test from 'node:test'
import assert from 'node:assert/strict'
import { buildChatRenderItems } from './chat-render-items.ts'
import type { Message } from '../../stores/useSessionStore.ts'

function createMessage(overrides: Partial<Message> & Pick<Message, 'id' | 'role' | 'content'>): Message {
  return {
    id: overrides.id,
    role: overrides.role,
    content: overrides.content,
    timestamp: overrides.timestamp ?? new Date('2026-04-15T00:00:00Z'),
    isStreaming: overrides.isStreaming,
    isTruncated: overrides.isTruncated,
  }
}

test('attaches environment output to the previous assistant code message', () => {
  const messages: Message[] = [
    createMessage({
      id: 'a1',
      role: 'assistant',
      content: '<CodeBlock lang="python">print("hi")</CodeBlock>',
    }),
    createMessage({
      id: 'e1',
      role: 'environment',
      content: 'hi',
    }),
  ]

  const items = buildChatRenderItems(messages)

  assert.equal(items.length, 1)
  assert.equal(items[0].message.id, 'a1')
  assert.equal(items[0].assistantContent?.hasToolSegments, true)
  assert.equal(items[0].attachedEnvironment?.id, 'e1')
})

test('attaches environment output to the previous assistant self-closing tool message', () => {
  const messages: Message[] = [
    createMessage({
      id: 'a1',
      role: 'assistant',
      content:
        '<libq url="https://github.com/sb-ai-lab/LightAutoML" query="What is LightAutoML?" />',
    }),
    createMessage({
      id: 'e1',
      role: 'environment',
      content: 'LightAutoML is an AutoML framework.',
    }),
  ]

  const items = buildChatRenderItems(messages)

  assert.equal(items.length, 1)
  assert.equal(items[0].message.id, 'a1')
  assert.equal(items[0].assistantContent?.lastToolSegmentIndex, 0)
  assert.equal(items[0].attachedEnvironment?.id, 'e1')
})

test('drops standalone environment messages that do not belong to an execution block', () => {
  const messages: Message[] = [
    createMessage({
      id: 'a1',
      role: 'assistant',
      content: 'No code here.',
    }),
    createMessage({
      id: 'e1',
      role: 'environment',
      content: 'shell output',
    }),
  ]

  const items = buildChatRenderItems(messages)

  assert.equal(items.length, 1)
  assert.equal(items[0].message.id, 'a1')
  assert.equal(items[0].assistantContent?.hasToolSegments, false)
  assert.equal(items[0].attachedEnvironment, undefined)
})

test('drops orphan environment messages completely', () => {
  const messages: Message[] = [
    createMessage({
      id: 'e1',
      role: 'environment',
      content: 'shell output',
    }),
  ]

  const items = buildChatRenderItems(messages)

  assert.deepEqual(items, [])
})

import test from 'node:test'
import assert from 'node:assert/strict'
import { parseAssistantContent, parseAssistantSegments } from './assistant-segments'

test('parses CodeBlock tags into assistant-code tool segments', () => {
  const message = [
    'Plan first.',
    '<CodeBlock lang="python">',
    '  print("hello")',
    '  print("world")',
    '</CodeBlock>',
    'Done.',
  ].join('\n')

  const segments = parseAssistantSegments(message)

  assert.deepEqual(segments, [
    {
      type: 'text',
      content: 'Plan first.\n',
    },
    {
      type: 'tool',
      tool: 'python',
      content: 'print("hello")\nprint("world")',
      attributes: {
        arg: 'print("hello")\nprint("world")',
        lang: 'python',
      },
      presentation: 'assistant-code',
    },
    {
      type: 'text',
      content: '\nDone.',
    },
  ])
})

test('preserves tool tags and surrounding markdown order', () => {
  const message = [
    'Before',
    '<shell>echo hi</shell>',
    '<CodeBlock lang="bash">',
    '  ls -la',
    '</CodeBlock>',
    '<submit id="done" />',
  ].join('\n')

  const segments = parseAssistantSegments(message)

  assert.equal(segments.length, 6)
  assert.deepEqual(segments[0], {
    type: 'text',
    content: 'Before\n',
  })
  assert.deepEqual(segments[1], {
    type: 'tool',
    tool: 'shell',
    content: 'echo hi',
    attributes: {},
    presentation: 'tool',
  })
  assert.deepEqual(segments[2], {
    type: 'text',
    content: '\n',
  })
  assert.deepEqual(segments[3], {
    type: 'tool',
    tool: 'bash',
    content: 'ls -la',
    attributes: {
      arg: 'ls -la',
      lang: 'bash',
    },
    presentation: 'assistant-code',
  })
  assert.deepEqual(segments[4], {
    type: 'text',
    content: '\n',
  })
  assert.deepEqual(segments[5], {
    type: 'tool',
    tool: 'submit',
    content: '<submit id="done" />',
    attributes: {
      id: 'done',
    },
    presentation: 'tool',
  })
})

test('ignores invalid pseudo-tools', () => {
  const segments = parseAssistantSegments('<thinking>skip me</thinking>\nKeep this.')

  assert.deepEqual(segments, [
    {
      type: 'text',
      content: '<thinking>skip me</thinking>\nKeep this.',
    },
  ])
})

test('computes assistant render metadata in one pass', () => {
  const parsed = parseAssistantContent('Before\n<libq query="test" />\nAfter')

  assert.equal(parsed.hasToolSegments, true)
  assert.equal(parsed.lastToolSegmentIndex, 1)
  assert.equal(parsed.segments[1]?.type, 'tool')
})

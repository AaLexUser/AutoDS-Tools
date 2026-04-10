'use client'

import { memo, useMemo } from 'react'
import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ToolCallBlock } from './ToolCallBlock'
import { CodeBlock } from './CodeBlock'
import { parseToolCalls } from '@/lib/utils/xml-parser'

interface MarkdownRendererProps {
  content: string
}

// Remark plugins array - stable reference
const remarkPlugins = [remarkGfm]

const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const codeString = String(children)
    const isInline = !match && !codeString.replace(/\n$/, '').includes('\n')

    if (isInline) {
      return (
        <code className="bg-surface-elevated text-accent px-1.5 py-0.5 rounded font-mono text-sm" {...props}>
          {children}
        </code>
      )
    }

    return (
      <CodeBlock
        language={match ? match[1] : 'text'}
        code={codeString.replace(/\n$/, '')}
      />
    )
  },
  pre({ children }) {
    return <>{children}</>
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent hover:text-accent-muted underline underline-offset-2"
      >
        {children}
      </a>
    )
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-4">
        <table className="w-full border-collapse">{children}</table>
      </div>
    )
  },
  th({ children }) {
    return (
      <th className="border border-border px-3 py-2 text-left bg-surface-elevated font-medium">
        {children}
      </th>
    )
  },
  td({ children }) {
    return (
      <td className="border border-border px-3 py-2 text-left">
        {children}
      </td>
    )
  },
}

function MarkdownRendererComponent({ content }: MarkdownRendererProps) {
  // Memoize parsed segments to avoid re-parsing on every render
  const segments = useMemo(() => parseToolCalls(content), [content])

  return (
    <div className="space-y-4">
      {segments.map((segment, index) => {
        if (segment.type === 'text') {
          // Render markdown text
          return segment.content.trim() ? (
            <ReactMarkdown
              key={index}
              remarkPlugins={remarkPlugins}
              components={markdownComponents}
            >
              {segment.content}
            </ReactMarkdown>
          ) : null
        } else if (segment.tool) {
          // Render tool call
          return (
            <ToolCallBlock
              key={index}
              tool={segment.tool}
              content={segment.content}
              attributes={segment.attributes}
            />
          )
        }

        return null
      })}
    </div>
  )
}

export const MarkdownRenderer = memo(MarkdownRendererComponent)

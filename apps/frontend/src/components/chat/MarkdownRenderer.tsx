'use client'

import { memo } from 'react'
import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CodeBlock } from './CodeBlock'

interface MarkdownRendererProps {
  content: string
}

const remarkPlugins = [remarkGfm]

const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || '')
    const codeString = String(children)
    const isInline = !match && !codeString.replace(/\n$/, '').includes('\n')

    if (isInline) {
      return (
        <code
          className="rounded bg-surface-elevated px-1.5 py-0.5 font-mono text-[13px] text-accent"
          {...props}
        >
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
        className="text-accent underline underline-offset-2 hover:text-accent-muted"
      >
        {children}
      </a>
    )
  },
  table({ children }) {
    return (
      <div className="my-4 overflow-x-auto">
        <table className="w-full border-collapse">{children}</table>
      </div>
    )
  },
  th({ children }) {
    return (
      <th className="border border-border bg-surface-elevated px-3 py-2 text-left font-medium">
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

function MarkdownRendererComponent({
  content,
}: MarkdownRendererProps) {
  return (
    <div className="space-y-3">
      <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
        {content}
      </ReactMarkdown>
    </div>
  )
}

export const MarkdownRenderer = memo(MarkdownRendererComponent)

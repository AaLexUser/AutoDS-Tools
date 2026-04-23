'use client'

import { memo } from 'react'
import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Code, Terminal, FileCode, CheckSquare, Send } from 'lucide-react'
import { ExecutionCell } from './ExecutionCell'
import { CodeBlock } from './CodeBlock'
import { parseAssistantContent, type ParsedAssistantContent } from '@/lib/utils/assistant-segments'
import { type Message as SessionMessage } from '@/stores/useSessionStore'

interface MarkdownRendererProps {
  content: string
  assistantContent?: ParsedAssistantContent
  attachedEnvironment?: SessionMessage
  attachedEnvironmentExpanded?: boolean
  onToggleAttachedEnvironment?: (messageId: string) => void
}

const remarkPlugins = [remarkGfm]

const TOOL_ICONS: Record<string, React.ReactNode> = {
  python: <Code className="h-3.5 w-3.5" />,
  ipython: <Code className="h-3.5 w-3.5" />,
  jupyter: <Code className="h-3.5 w-3.5" />,
  shell: <Terminal className="h-3.5 w-3.5" />,
  bash: <Terminal className="h-3.5 w-3.5" />,
  sh: <Terminal className="h-3.5 w-3.5" />,
  codeblocks: <FileCode className="h-3.5 w-3.5" />,
  fileblocks: <FileCode className="h-3.5 w-3.5" />,
  todo: <CheckSquare className="h-3.5 w-3.5" />,
  submit: <Send className="h-3.5 w-3.5" />,
}

function toolIcon(tool: string): React.ReactNode {
  return TOOL_ICONS[tool.toLowerCase()] ?? <Code className="h-3.5 w-3.5" />
}

function toolTitle(tool: string): string {
  return tool
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

function toolLanguage(tool: string): string {
  const t = tool.toLowerCase()
  if (t === 'shell' || t === 'bash' || t === 'sh') return 'bash'
  if (t === 'python' || t === 'ipython' || t === 'jupyter') return 'python'
  return 'text'
}

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
  assistantContent,
  attachedEnvironment,
  attachedEnvironmentExpanded = false,
  onToggleAttachedEnvironment,
}: MarkdownRendererProps) {
  const parsedContent = assistantContent ?? parseAssistantContent(content)
  const { segments, lastToolSegmentIndex } = parsedContent

  return (
    <div className="space-y-3">
      {segments.map((segment, index) => {
        if (segment.type === 'text') {
          return segment.content.trim() ? (
            <ReactMarkdown
              key={index}
              remarkPlugins={remarkPlugins}
              components={markdownComponents}
            >
              {segment.content}
            </ReactMarkdown>
          ) : null
        }

        if (segment.presentation === 'assistant-code' && segment.tool) {
          const lang = segment.tool.toLowerCase()
          const shouldAttach =
            index === lastToolSegmentIndex &&
            attachedEnvironment &&
            onToggleAttachedEnvironment

          return (
            <ExecutionCell
              key={index}
              title={toolTitle(segment.tool)}
              language={lang}
              code={segment.content}
              icon={toolIcon(lang)}
              output={
                shouldAttach
                  ? {
                      id: attachedEnvironment.id,
                      content: attachedEnvironment.content,
                      isTruncated: attachedEnvironment.isTruncated,
                      expanded: attachedEnvironmentExpanded,
                      onToggleExpanded: onToggleAttachedEnvironment,
                    }
                  : undefined
              }
            />
          )
        }

        if (segment.tool) {
          const t = segment.tool.toLowerCase()
          const shouldAttach =
            index === lastToolSegmentIndex &&
            attachedEnvironment &&
            onToggleAttachedEnvironment
          return (
            <ExecutionCell
              key={index}
              title={toolTitle(segment.tool)}
              language={toolLanguage(t)}
              code={segment.content}
              icon={toolIcon(t)}
              output={
                shouldAttach
                  ? {
                      id: attachedEnvironment.id,
                      content: attachedEnvironment.content,
                      isTruncated: attachedEnvironment.isTruncated,
                      expanded: attachedEnvironmentExpanded,
                      onToggleExpanded: onToggleAttachedEnvironment,
                    }
                  : undefined
              }
            />
          )
        }

        return null
      })}
    </div>
  )
}

export const MarkdownRenderer = memo(MarkdownRendererComponent)

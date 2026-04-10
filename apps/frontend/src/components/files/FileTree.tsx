'use client'

import { useState, type ReactNode } from 'react'
import {
  Folder,
  FolderOpen,
  FileText,
  FileCode,
  FileSpreadsheet,
  FileJson,
  Image,
  ChevronRight,
  ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils/cn'
import { type ArtifactNode } from '@/lib/api/client'
import {
  formatFileSize,
  getFileExtension,
  isPythonFile,
  isCSVFile,
  isJupyterNotebook,
  isImageFile,
} from '@/hooks/useArtifacts'

interface FileTreeProps {
  node: ArtifactNode
  selectedPath: string | null
  onSelect: (path: string | null) => void
  depth?: number
}

function getFileIcon(filename: string | null | undefined) {
  if (!filename) return FileText
  const ext = getFileExtension(filename)

  if (isPythonFile(filename)) return FileCode
  if (isCSVFile(filename)) return FileSpreadsheet
  if (isJupyterNotebook(filename)) return FileJson
  if (isImageFile(filename)) return Image
  if (['json', 'yaml', 'yml', 'toml'].includes(ext)) return FileJson

  return FileText
}

function renderNodeIcon(isDirectory: boolean, expanded: boolean, filename: string | null | undefined): ReactNode {
  if (isDirectory) {
    return expanded ? <FolderOpen className="h-4 w-4 flex-shrink-0 text-accent" /> : <Folder className="h-4 w-4 flex-shrink-0 text-accent" />
  }

  const Icon = getFileIcon(filename)
  return <Icon className="h-4 w-4 flex-shrink-0 text-text-muted" />
}

export function FileTree({ node, selectedPath, onSelect, depth = 0 }: FileTreeProps) {
  const [expanded, setExpanded] = useState(depth < 2)

  const isDirectory = node.type === 'directory'
  const isSelected = node.path === selectedPath

  const handleClick = () => {
    if (isDirectory) {
      setExpanded(!expanded)
    } else {
      onSelect(node.path)
    }
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          'w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left transition-colors',
          'hover:bg-surface-hover',
          isSelected && 'bg-accent/10 text-accent border border-accent/30',
          !isSelected && 'text-text-primary'
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {isDirectory && (
          <span className="text-text-muted">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
        {renderNodeIcon(isDirectory, expanded, node.name)}
        <span className="truncate text-sm flex-1">{node.name}</span>
        {!isDirectory && node.size !== undefined && (
          <span className="text-2xs text-text-muted flex-shrink-0">
            {formatFileSize(node.size)}
          </span>
        )}
      </button>

      {isDirectory && expanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTree
              key={child.path}
              node={child}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

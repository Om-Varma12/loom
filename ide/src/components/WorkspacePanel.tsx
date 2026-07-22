import { useEffect, useState } from 'react'
import {
  getWorkspaceTree,
  getFileContent,
  saveFileContent,
  downloadWorkspaceZip,
  type FileTreeNode
} from '../lib/projects'
import FileExplorer from './FileExplorer'
import CodeEditor from './CodeEditor'

type WorkspacePanelProps = {
  projectId: string
  projectName?: string
  onClose?: () => void
  status?: string
}

export default function WorkspacePanel({ projectId, projectName = 'Project', onClose, status }: WorkspacePanelProps) {
  const [tree, setTree] = useState<FileTreeNode[]>([])
  const [activeFilePath, setActiveFilePath] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  
  const [isTreeLoading, setIsTreeLoading] = useState(false)
  const [isFileLoading, setIsFileLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDownloading, setIsDownloading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // Reset active file when project changes
  useEffect(() => {
    setActiveFilePath(null)
    setFileContent(null)
    setErrorMessage(null)
  }, [projectId])

  // Load/reload tree on mount, or when project changes, or when status changes
  useEffect(() => {
    loadTree()
  }, [projectId, status])

  const loadTree = async () => {
    setIsTreeLoading(true)
    setErrorMessage(null)
    try {
      const data = await getWorkspaceTree(projectId)
      setTree(data)
    } catch (err: any) {
      console.error(err)
      setErrorMessage('Failed to load workspace file tree.')
    } finally {
      setIsTreeLoading(false)
    }
  }

  const handleSelectFile = async (path: string) => {
    setIsFileLoading(true)
    setErrorMessage(null)
    setSaveSuccess(false)
    try {
      const data = await getFileContent(projectId, path)
      setFileContent(data.content)
      setActiveFilePath(path)
    } catch (err: any) {
      console.error(err)
      setErrorMessage(`Failed to load file contents for '${path}'`)
    } finally {
      setIsFileLoading(false)
    }
  }

  const handleSaveFile = async (path: string, content: string) => {
    setIsSaving(true)
    setErrorMessage(null)
    setSaveSuccess(false)
    try {
      await saveFileContent(projectId, path, content)
      setFileContent(content)
      setSaveSuccess(true)
      // Auto clear success message after 3 seconds
      setTimeout(() => setSaveSuccess(false), 3000)
    } catch (err: any) {
      console.error(err)
      setErrorMessage(`Failed to save file '${path}'`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleDownloadWorkspace = async () => {
    setIsDownloading(true)
    setErrorMessage(null)
    try {
      await downloadWorkspaceZip(projectId, projectName)
    } catch (err: any) {
      console.error(err)
      setErrorMessage('Failed to download workspace ZIP.')
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="w-full h-full flex flex-col bg-[#141414] border-l border-[#262626]">
      {/* Panel Top Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#171717] border-b border-[#262626] shrink-0">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[20px]">terminal</span>
          <span className="font-semibold text-white text-[14px] truncate max-w-[200px]" title={`${projectName} Workspace`}>
            {projectName} Workspace
          </span>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Refresh Button */}
          <button
            onClick={loadTree}
            className="p-1.5 text-on-surface-variant hover:text-white rounded hover:bg-[#262626] transition-colors"
            title="Refresh File Tree"
            type="button"
          >
            <span className={`material-symbols-outlined text-[18px] ${isTreeLoading ? 'animate-spin' : ''}`}>
              refresh
            </span>
          </button>

          {/* Download Zip button */}
          <button
            onClick={handleDownloadWorkspace}
            className="flex items-center gap-1 bg-tertiary-fixed-dim hover:bg-opacity-95 text-on-tertiary-fixed px-3 py-1.5 rounded text-[12px] font-medium transition-all shadow-md active:scale-95"
            disabled={isDownloading}
            title="Download full workspace as ZIP"
            type="button"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            <span>{isDownloading ? 'Downloading...' : 'Download ZIP'}</span>
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 text-on-surface-variant hover:text-white rounded hover:bg-[#262626] transition-colors ml-1 flex items-center justify-center"
              title="Close Workspace Explorer"
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace Layout (Explorer Sidebar + Code Editor Pane) */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        
        {/* Left Side: File Explorer list */}
        <div className="w-[220px] shrink-0 border-r border-[#262626] flex flex-col bg-[#171717] overflow-hidden">
          <div className="px-3 py-1.5 border-b border-[#262626]/40 flex items-center justify-between bg-[#141414]/50">
            <span className="text-[11px] font-label-caps text-on-surface-variant/80 tracking-wider">Files</span>
            {tree.length > 0 && (
              <span className="text-[10px] bg-[#262626] text-on-surface-variant px-1.5 py-0.5 rounded-full font-mono">
                {tree.length} modules
              </span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {isTreeLoading ? (
              <div className="p-4 flex flex-col items-center justify-center gap-2 text-on-surface-variant text-[12px]">
                <span className="material-symbols-outlined animate-spin">sync</span>
                <span>Reading tree...</span>
              </div>
            ) : (
              <FileExplorer
                tree={tree}
                activeFilePath={activeFilePath}
                onSelectFile={handleSelectFile}
              />
            )}
          </div>
        </div>

        {/* Right Side: Monaco Code Editor or Empty State */}
        <div className="flex-1 bg-[#1e1e1e] p-3 flex flex-col overflow-hidden relative">
          
          {/* Notification Overlay */}
          {errorMessage && (
            <div className="absolute top-4 left-4 right-4 z-20 glass-panel p-3 border-[#ef4444]/20 bg-[#ef4444]/10 rounded-lg flex items-center justify-between animate-step-fade-in shadow-xl">
              <div className="flex items-center gap-2 text-[#ef4444] text-[12px] font-medium">
                <span className="material-symbols-outlined text-[16px]">error</span>
                <span>{errorMessage}</span>
              </div>
              <button 
                onClick={() => setErrorMessage(null)}
                className="text-on-surface-variant hover:text-white"
                type="button"
              >
                <span className="material-symbols-outlined text-[14px]">close</span>
              </button>
            </div>
          )}

          {saveSuccess && (
            <div className="absolute top-4 right-4 z-20 bg-tertiary-fixed-dim text-on-tertiary-fixed px-3 py-1.5 rounded-lg text-[12px] font-medium flex items-center gap-1.5 shadow-lg animate-step-fade-in">
              <span className="material-symbols-outlined text-[16px]">check_circle</span>
              <span>File saved!</span>
            </div>
          )}

          {isFileLoading ? (
            /* Loading File Content State */
            <div className="flex-1 flex flex-col items-center justify-center gap-2 text-on-surface-variant">
              <span className="material-symbols-outlined animate-spin text-[24px]">sync</span>
              <span className="text-[13px] font-code-md">Reading file content...</span>
            </div>
          ) : activeFilePath && fileContent !== null ? (
            /* Active Code Editor */
            <CodeEditor
              filePath={activeFilePath}
              content={fileContent}
              onSave={handleSaveFile}
              isSaving={isSaving}
            />
          ) : (
            /* No file selected - Premium Empty State */
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-[#1e1e1e] border border-[#262626]/60 rounded-lg">
              <div className="w-16 h-16 rounded-full bg-[#171717] border border-[#262626] flex items-center justify-center mb-4 text-on-surface-variant/40">
                <span className="material-symbols-outlined text-[32px] animate-pulse">developer_mode</span>
              </div>
              <h3 className="font-semibold text-white text-[15px] mb-1">Editor Ready</h3>
              <p className="text-[12px] text-on-surface-variant max-w-xs mb-6 leading-relaxed">
                Select any generated file from the explorer on the left to read and edit its source code directly.
              </p>
              
              <div className="text-[11px] text-on-surface-variant/75 space-y-2 border-t border-[#262626]/60 pt-4 w-44 font-code-md">
                <div className="flex justify-between">
                  <span>Open file</span>
                  <span className="bg-[#262626] px-1 rounded text-[9px]">Click</span>
                </div>
                <div className="flex justify-between">
                  <span>Save file</span>
                  <span className="bg-[#262626] px-1 rounded text-[9px]">Ctrl + S</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

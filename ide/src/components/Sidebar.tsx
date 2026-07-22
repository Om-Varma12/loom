import { useEffect, useState, useRef } from 'react'
import {
  createProject,
  getProjects,
  getChats,
  type Project,
  type Chat,
} from '../lib/projects'

export type AppPage = 'chat' | 'marketplace'

type SidebarProps = {
  activePage: AppPage
  onNavigate: (page: AppPage, agentId?: string | null) => void
  activeChatId?: string | null
  onSelectChat?: (chatId: string) => void
  onSelectProject?: (projectId: string, projectName: string) => void
  onSelectAgents?: () => void
  isAgentsActive?: boolean
  onSelectProjectsList?: () => void
  isProjectsListActive?: boolean
}

function Sidebar({
  activePage,
  onNavigate,
  activeChatId,
  onSelectChat,
  onSelectProject,
  onSelectAgents,
  isAgentsActive = false,
  onSelectProjectsList,
  isProjectsListActive = false,
}: SidebarProps) {
  const [projects, setProjects] = useState<Project[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [isAddingProject, setIsAddingProject] = useState(false)
  const [newProjectPath, setNewProjectPath] = useState('')
  const [newProjectName, setNewProjectName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [isProjectsExpanded, setIsProjectsExpanded] = useState(() => {
    const persisted = localStorage.getItem('sidebar_projects_expanded')
    return persisted !== null ? persisted === 'true' : true
  })
  const [isChatsExpanded, setIsChatsExpanded] = useState(() => {
    const persisted = localStorage.getItem('sidebar_chats_expanded')
    return persisted !== null ? persisted === 'true' : true
  })

  const toggleProjects = () => {
    setIsProjectsExpanded((prev) => {
      const next = !prev
      localStorage.setItem('sidebar_projects_expanded', String(next))
      return next
    })
  }

  const toggleChats = () => {
    setIsChatsExpanded((prev) => {
      const next = !prev
      localStorage.setItem('sidebar_chats_expanded', String(next))
      return next
    })
  }

  useEffect(() => {
    let active = true

    async function loadData(force = false) {
      try {
        const [projectData, chatData] = await Promise.all([
          getProjects(force),
          getChats(force),
        ])
        if (active) {
          setProjects(projectData)
          setChats(chatData)
        }
      } catch (error) {
        console.error('Failed to fetch sidebar data', error)
      }
    }

    void loadData()

    const handleProjectCreated = () => void loadData(true)
    const handleChatCreated = () => void loadData(true)

    window.addEventListener('project-created', handleProjectCreated)
    window.addEventListener('chat-created', handleChatCreated)

    return () => {
      active = false
      window.removeEventListener('project-created', handleProjectCreated)
      window.removeEventListener('chat-created', handleChatCreated)
    }
  }, [])

  const handleAddProjectClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files
    if (files && files.length > 0) {
      const folder = files[0] as File & { path?: string }
      const folderName = folder.name || 'New Project'
      setNewProjectName(folderName)
      setNewProjectPath(folder.path || '')
      setIsAddingProject(true)
    }
  }

  const handleSaveProject = () => {
    if (newProjectName) {
      createProject({
        name: newProjectName,
        description: newProjectPath || null,
        agent_ids: [],
      })
        .then(() => {
          window.dispatchEvent(new CustomEvent('project-created'))
          setIsAddingProject(false)
          setNewProjectName('')
          setNewProjectPath('')
        })
        .catch((error) => {
          console.error('Failed to create project:', error)
          alert(`Failed to create project: ${error.message}`)
        })
    }
  }

  const handleCancelAddProject = () => {
    setIsAddingProject(false)
    setNewProjectName('')
    setNewProjectPath('')
  }

  return (
    <aside
      className="hidden md:flex flex-col h-full bg-[#161616] h-screen w-sidebar-width shrink-0"
      aria-label="Workspace navigation"
    >
      {/* Brand Header */}
      <div className="px-6 py-6 flex items-center justify-between">
        <div className="flex gap-3 items-center">
          <div className="flex flex-col">
            <span className="font-headline-lg text-headline-lg font-bold text-primary dark:text-primary text-[20px] leading-none tracking-tight">
              L00m AI
            </span>
            <span className="font-label-caps text-label-caps text-on-surface-variant opacity-60 text-[10px] mt-0.5">
              Developer Workspace
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2 flex flex-col gap-1 hide-scrollbar">
        {activePage === 'marketplace' ? (
          <button
            className="flex items-center gap-3 text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary px-4 py-2 transition-all font-body-sm text-body-sm hover:bg-surface-container-highest dark:hover:bg-surface-container-high w-full text-left"
            onClick={() => onNavigate('chat')}
            type="button"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            <span>Back to Dashboard</span>
          </button>
        ) : (
          <>
            {/* New Chat */}
            <button
              aria-current={(activePage === 'chat' && !activeChatId) ? 'page' : undefined}
              className={`flex items-center gap-3 px-4 py-2 font-body-sm text-body-sm transition-all text-left w-full ${
                (activePage === 'chat' && !activeChatId)
                  ? 'text-primary dark:text-primary border-l-2 border-primary bg-surface-container-high dark:bg-surface-container-highest'
                  : 'text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary hover:bg-surface-container-highest dark:hover:bg-surface-container-high'
              }`}
              onClick={() => onNavigate('chat')}
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">add_box</span>
              <span>New chat</span>
            </button>

            {/* Marketplace */}
            <button
              aria-current={(activePage as string) === 'marketplace' ? 'page' : undefined}
              className={`flex items-center gap-3 px-4 py-2 font-body-sm text-body-sm transition-all text-left w-full ${
                (activePage as string) === 'marketplace'
                  ? 'text-primary dark:text-primary border-l-2 border-primary bg-surface-container-high dark:bg-surface-container-highest'
                  : 'text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary hover:bg-surface-container-highest dark:hover:bg-surface-container-high'
              }`}
              onClick={() => onNavigate('marketplace')}
              type="button"
            >
              <span className="material-symbols-outlined text-[18px]">storefront</span>
              <span>Marketplace</span>
            </button>

            {/* Other links */}
            {/* <a
              className="flex items-center gap-3 text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary px-4 py-2 transition-colors font-body-sm text-body-sm hover:bg-surface-container-highest dark:hover:bg-surface-container-high"
              href="#"
            >
              <span className="material-symbols-outlined text-[18px]">extension</span>
              <span>Plugins</span>
            </a>
            <a
              className="flex items-center gap-3 text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary px-4 py-2 transition-colors font-body-sm text-body-sm hover:bg-surface-container-highest dark:hover:bg-surface-container-high"
              href="#"
            >
              <span className="material-symbols-outlined text-[18px]">smart_toy</span>
              <span>Automations</span>
            </a> */}

            {/* ── Projects ───────────────────────────────────────── */}
            <div className="mt-2 px-4 mb-1 flex items-center justify-between">
              <button
                type="button"
                onClick={toggleProjects}
                className="flex items-center gap-1 text-left font-label-caps text-label-caps text-on-surface-variant opacity-70 text-[11px] tracking-widest hover:opacity-100 transition-opacity cursor-pointer uppercase font-semibold select-none"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {isProjectsExpanded ? 'keyboard_arrow_down' : 'keyboard_arrow_right'}
                </span>
                <span>Projects</span>
              </button>
              <button
                onClick={handleAddProjectClick}
                type="button"
                className="material-symbols-outlined text-[16px] text-on-surface-variant opacity-70 hover:text-primary dark:hover:text-primary transition-colors cursor-pointer"
                title="Add existing project"
              >
                add
              </button>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>

            {isProjectsExpanded && (
              <div className="flex flex-col gap-0.5">
                {projects.length > 0 ? (
                  projects.slice(0, 7).map((project) => (
                    <a
                      className="flex items-center gap-3 text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary px-4 py-2 transition-all font-body-sm text-body-sm hover:bg-surface-container-highest dark:hover:bg-surface-container-high cursor-pointer"
                      href="#"
                      key={project.id}
                      onClick={(e) => {
                        e.preventDefault()
                        if (onSelectProject) {
                          onSelectProject(project.id, project.name)
                        }
                      }}
                    >
                      <span className="material-symbols-outlined text-[18px] opacity-70">folder</span>
                      <span className="truncate">{project.name}</span>
                    </a>
                  ))
                ) : null}

                {projects.length > 7 && (
                  <button
                    type="button"
                    onClick={onSelectProjectsList}
                    className={`flex items-center gap-3 px-4 py-2 font-body-sm text-body-sm transition-all text-left w-full rounded-lg ${
                      isProjectsListActive
                        ? 'text-primary dark:text-primary border-l-2 border-primary bg-surface-container-high dark:bg-surface-container-highest font-medium'
                        : 'text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary hover:bg-surface-container-highest dark:hover:bg-surface-container-high'
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px] opacity-70">more_horiz</span>
                    <span>View all {projects.length} projects</span>
                  </button>
                )}
              </div>
            )}

            {/* Add Project Modal/Dialog */}
            {isAddingProject && (
              <div className="px-4 py-3 bg-surface-container-high dark:bg-surface-container-high rounded-lg mb-2 animate-step-fade-in">
                <div className="flex items-center gap-3 mb-3">
                  <span className="material-symbols-outlined text-primary text-[20px]">folder_open</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-primary font-medium text-[13px] truncate">{newProjectName}</p>
                    <p className="text-on-surface-variant text-[11px] truncate">{newProjectPath}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCancelAddProject}
                    className="flex items-center gap-1.5 text-on-surface-variant hover:text-primary text-[11px] px-2 py-1 hover:bg-surface-container-high rounded transition-colors"
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[16px]">close</span>
                    Cancel
                  </button>
                  <div className="flex-1" />
                  <button
                    onClick={handleSaveProject}
                    className="flex items-center gap-1.5 text-on-primary bg-primary hover:bg-primary/90 text-[11px] px-3 py-1.5 rounded transition-colors"
                    type="button"
                  >
                    <span className="material-symbols-outlined text-[16px]">save</span>
                    Save
                  </button>
                </div>
              </div>
            )}

            {/* Agents Row Button */}
            <div className="mt-5 px-3 mb-2">
              <button
                type="button"
                onClick={onSelectAgents}
                className={`flex items-center gap-3 px-4 py-2 font-body-sm text-body-sm transition-all text-left w-full rounded-lg ${
                  isAgentsActive
                    ? 'text-primary dark:text-primary border-l-2 border-primary bg-surface-container-high dark:bg-surface-container-highest font-medium'
                    : 'text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary hover:bg-surface-container-highest dark:hover:bg-surface-container-high'
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">smart_toy</span>
                <span>Agents</span>
              </button>
            </div>


            {/* ── Chats ─────────────────────────────────────────── */}
            <div className="mt-5 px-4 mb-1 flex items-center justify-between">
              <button
                type="button"
                onClick={toggleChats}
                className="flex items-center gap-1 text-left font-label-caps text-label-caps text-on-surface-variant opacity-70 text-[11px] tracking-widest hover:opacity-100 transition-opacity cursor-pointer uppercase font-semibold select-none"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {isChatsExpanded ? 'keyboard_arrow_down' : 'keyboard_arrow_right'}
                </span>
                <span>Chats</span>
              </button>
            </div>

            {isChatsExpanded && (
              <div className="flex flex-col gap-0.5">
                {chats.length > 0 ? (
                  chats.map((chat) => {
                    const isActive = activeChatId === chat.id
                    return (
                      <button
                        className={`flex items-center gap-3 px-4 py-2 font-body-sm text-body-sm transition-all text-left w-full ${
                          isActive
                            ? 'text-primary dark:text-primary border-l-2 border-primary bg-surface-container-high dark:bg-surface-container-highest font-medium'
                            : 'text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary hover:bg-surface-container-highest dark:hover:bg-surface-container-high'
                        }`}
                        onClick={() => {
                          onNavigate('chat')
                          if (onSelectChat) {
                            onSelectChat(chat.id)
                          }
                        }}
                        type="button"
                        key={chat.id}
                        title={chat.title}
                      >
                        <span className="material-symbols-outlined text-[18px] opacity-70">chat</span>
                        <span className="truncate">{chat.title}</span>
                      </button>
                    )
                  })
                ) : (
                  <span className="px-4 py-1.5 text-[12px] text-on-surface-variant italic">
                    No chats yet
                  </span>
                )}
              </div>
            )}
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="marketplace-sidebar-footer mt-auto border-t border-outline-variant py-2">

        <a
          className="flex items-center gap-3 text-on-surface-variant dark:text-on-surface-variant hover:text-primary dark:hover:text-primary px-4 py-2 transition-all font-body-sm text-body-sm hover:bg-surface-container-highest dark:hover:bg-surface-container-high"
          href="#"
        >
          <span className="material-symbols-outlined text-[18px]">settings</span>
          <span>Settings</span>
        </a>
      </div>
    </aside>
  )
}

export default Sidebar

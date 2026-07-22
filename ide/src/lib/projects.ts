import {
  apiUrl,
  authFetch,
  registerAuthCacheResetter,
} from './authFetch'

export type Project = {
  id: string
  name: string
  description?: string | null
  agent_ids?: string[]
}

let cachedProjects: Project[] | null = null
let projectsFetchPromise: Promise<Project[]> | null = null

export function invalidateProjectsCache() {
  cachedProjects = null
  projectsFetchPromise = null
}

export async function createProject(input: {
  name: string
  description?: string | null
  agent_ids: string[]
}): Promise<{ project_id: string; name: string; description: string | null; status: string }> {
  const response = await authFetch(apiUrl('/projects'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(errorText || 'Failed to create project')
  }

  invalidateProjectsCache()
  return response.json()
}

export async function getProject(projectId: string): Promise<Project> {
  const response = await authFetch(apiUrl(`/projects/${projectId}`), {
    method: 'GET',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch project')
  }

  return response.json()
}

export async function getProjects(forceRefresh = false): Promise<Project[]> {
  if (forceRefresh) {
    invalidateProjectsCache()
  }

  if (cachedProjects) {
    return cachedProjects
  }

  if (projectsFetchPromise) {
    return projectsFetchPromise
  }

  projectsFetchPromise = (async () => {
    try {
      const response = await authFetch(apiUrl('/projects/get-projects'), {
        method: 'POST',
      })

      if (!response.ok) {
        throw new Error('Failed to fetch projects')
      }

      const data = await response.json()
      cachedProjects = data
      return data
    } finally {
      projectsFetchPromise = null
    }
  })()

  return projectsFetchPromise
}

// ── Chats ──────────────────────────────────────────────────────────────────

export type Chat = {
  id: string
  title: string
  project_id: string
  created_at: string
  updated_at: string
}

let cachedChats: Chat[] | null = null
let chatsFetchPromise: Promise<Chat[]> | null = null

export function invalidateChatsCache() {
  cachedChats = null
  chatsFetchPromise = null
}

registerAuthCacheResetter(() => {
  invalidateProjectsCache()
  invalidateChatsCache()
})

export async function getChats(forceRefresh = false): Promise<Chat[]> {
  if (forceRefresh) {
    invalidateChatsCache()
  }

  if (cachedChats) {
    return cachedChats
  }

  if (chatsFetchPromise) {
    return chatsFetchPromise
  }

  chatsFetchPromise = (async () => {
    try {
      const response = await authFetch(apiUrl('/chats/get-chats'), {
        method: 'POST',
      })

      if (!response.ok) {
        throw new Error('Failed to fetch chats')
      }

      const data: Chat[] = await response.json()
      cachedChats = data
      return data
    } finally {
      chatsFetchPromise = null
    }
  })()

  return chatsFetchPromise
}

export type ChatMessage = {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'agent' | 'system'
  message_type: 'text' | 'agent_execution' | 'task_plan' | 'system_event'
  content: any
  created_at: string
}

export type ChatDetail = {
  session: Chat
  messages: ChatMessage[]
}

export async function getChatDetail(sessionId: string): Promise<ChatDetail> {
  const response = await authFetch(apiUrl(`/chats/get-chat/${sessionId}`), {
    method: 'GET',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch chat details')
  }

  return response.json()
}


export async function developProject(
  projectId: string,
  prompt: string,
  selectedAgentIds: string[],
  chatSessionId?: string | null,
  themeId?: string | null,
): Promise<any> {
  const response = await authFetch(apiUrl('/projects/develop'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      project_id: projectId,
      prompt: prompt,
      selected_agent_ids: selectedAgentIds,
      chat_session_id: chatSessionId || null,
      theme_id: themeId || null,
    }),
  })

  if (!response.ok) {
    const errorText = await response.text()
    let errorMsg = 'Failed to develop project'
    try {
      const parsed = JSON.parse(errorText)
      errorMsg = parsed.detail || errorMsg
    } catch {
      errorMsg = errorText || errorMsg
    }
    throw new Error(errorMsg)
  }

  return response.json()
}

export async function developProjectStream(
  projectId: string,
  prompt: string,
  selectedAgentIds: string[],
  onChunk: (chunk: any) => void,
  chatSessionId?: string | null,
  themeId?: string | null,
): Promise<void> {
  const response = await authFetch(apiUrl('/projects/develop'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      project_id: projectId,
      prompt: prompt,
      selected_agent_ids: selectedAgentIds,
      chat_session_id: chatSessionId || null,
      theme_id: themeId || null,
    }),
  })

  if (!response.ok) {
    const errorText = await response.text()
    let errorMsg = 'Failed to develop project'
    try {
      const parsed = JSON.parse(errorText)
      errorMsg = parsed.detail || errorMsg
    } catch {
      errorMsg = errorText || errorMsg
    }
    throw new Error(errorMsg)
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  if (reader) {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.trim()) {
          try {
            const chunk = JSON.parse(line)
            onChunk(chunk)
          } catch (e) {
            console.error('Failed to parse chunk', e)
          }
        }
      }
    }
  }
}

// ── Workspace ──────────────────────────────────────────────────────────────

export type FileTreeNode = {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileTreeNode[]
}

export type FileContentResponse = {
  path: string
  content: string
}

export async function getWorkspaceTree(projectId: string): Promise<FileTreeNode[]> {
  const response = await authFetch(apiUrl(`/workspace/${projectId}/tree`), {
    method: 'GET',
  })
  if (!response.ok) {
    throw new Error('Failed to fetch workspace tree')
  }
  return response.json()
}

export async function getFileContent(projectId: string, path: string): Promise<FileContentResponse> {
  const encodedPath = encodeURIComponent(path)
  const response = await authFetch(apiUrl(`/workspace/${projectId}/file?path=${encodedPath}`), {
    method: 'GET',
  })
  if (!response.ok) {
    throw new Error('Failed to fetch file content')
  }
  return response.json()
}

export async function saveFileContent(projectId: string, path: string, content: string): Promise<any> {
  const response = await authFetch(apiUrl(`/workspace/${projectId}/file`), {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      path,
      content,
    }),
  })
  if (!response.ok) {
    throw new Error('Failed to save file content')
  }
  return response.json()
}

export async function downloadWorkspaceZip(projectId: string, projectName: string): Promise<void> {
  const response = await authFetch(apiUrl(`/workspace/${projectId}/download`), {
    method: 'GET',
  })

  if (!response.ok) {
    throw new Error('Failed to download workspace')
  }

  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `${projectName || 'workspace'}_workspace.zip`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

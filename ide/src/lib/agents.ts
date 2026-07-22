import {
  apiUrl,
  authFetch,
  registerAuthCacheResetter,
} from './authFetch'

export type AgentCategory =
  | 'API'
  | 'Data'
  | 'AI'
  | 'DevOps'
  | 'Security'
  | 'Testing'

export type AgentData = {
  id: string
  name: string
  version: string
  type: 'Core' | 'Community'
  rating: string
  icon: string
  tone: 'amber' | 'green' | 'blue' | 'violet' | 'sky' | 'rose'
  description: string
  sources: string[]
  synced: string
  installs: string
  category: AgentCategory
  createdAt: string | null
  syncedAt: string | null
  downloaded: boolean
}

let cachedAgents: AgentData[] | null = null
let agentsFetchPromise: Promise<AgentData[]> | null = null

export function invalidateAgentsCache() {
  cachedAgents = null
  agentsFetchPromise = null
}

registerAuthCacheResetter(invalidateAgentsCache)

export async function getAgents(forceRefresh = false): Promise<AgentData[]> {
  if (forceRefresh) {
    invalidateAgentsCache()
  }

  if (cachedAgents) {
    return cachedAgents
  }

  if (agentsFetchPromise) {
    return agentsFetchPromise
  }

  agentsFetchPromise = (async () => {
    try {
      const response = await authFetch(apiUrl('/agents'))
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(detail || `Failed to fetch agents (${response.status})`)
      }

      const data: AgentData[] = await response.json()
      cachedAgents = data
      return data
    } finally {
      agentsFetchPromise = null
    }
  })()

  return agentsFetchPromise
}

export async function getDownloadedAgents(forceRefresh = false): Promise<AgentData[]> {
  const agents = await getAgents(forceRefresh)
  return agents.filter((agent) => agent.downloaded)
}

function notifyAgentsChanged() {
  window.dispatchEvent(new CustomEvent('agents-changed'))
}

export async function downloadAgent(agentId: string): Promise<void> {
  const response = await authFetch(apiUrl(`/agents/${agentId}/download`), {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error('Failed to download agent')
  }

  invalidateAgentsCache()
  notifyAgentsChanged()
}

export async function uninstallAgent(agentId: string): Promise<void> {
  const response = await authFetch(apiUrl(`/agents/${agentId}/download`), {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error('Failed to uninstall agent')
  }

  invalidateAgentsCache()
  notifyAgentsChanged()
}

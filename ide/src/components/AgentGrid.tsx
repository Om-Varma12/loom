import { useEffect, useState } from 'react'

import AgentCard from './AgentCard'
import MaterialIcon from './MaterialIcon'
import BorderGlow from './BorderGlow'
import type { MarketplaceFilter, MarketplaceSort } from '../lib/marketplace'
import {
  downloadAgent,
  getAgents,
  uninstallAgent,
  type AgentData,
} from '../lib/agents'

const INITIAL_VISIBLE_AGENTS = 12

type AgentGridProps = {
  activeFilter: MarketplaceFilter
  sortOption: MarketplaceSort
  searchTerm: string
}

function AgentGrid({
  activeFilter,
  sortOption,
  searchTerm,
}: AgentGridProps) {
  const [showAllAgents, setShowAllAgents] = useState(false)
  const [agents, setAgents] = useState<AgentData[]>([])
  const [pendingAgentId, setPendingAgentId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function loadAgents(forceRefresh = false) {
      try {
        const data = await getAgents(forceRefresh)
        if (active) {
          setAgents(data)
          setLoadError(null)
        }
      } catch (error) {
        console.error('Failed to fetch agents', error)
        if (active) {
          setLoadError(error instanceof Error ? error.message : 'Failed to fetch agents')
        }
      }
    }

    void loadAgents()
    const handleAgentsChanged = () => void loadAgents(true)
    window.addEventListener('agents-changed', handleAgentsChanged)

    return () => {
      active = false
      window.removeEventListener('agents-changed', handleAgentsChanged)
    }
  }, [])

  const normalizedSearch = searchTerm.trim().toLowerCase()

  const filteredAgents = agents.filter((agent) => {
    const matchesFilter =
      activeFilter === 'All Agents' ? true : agent.category === activeFilter

    if (!matchesFilter) {
      return false
    }

    if (!normalizedSearch) {
      return true
    }

    const searchableText = [
      agent.name,
      agent.description,
      agent.category,
      agent.type,
      ...agent.sources,
    ]
      .join(' ')
      .toLowerCase()

    return searchableText.includes(normalizedSearch)
  })

  const parseInstalls = (value: string) => {
    const normalized = value.trim().toLowerCase()
    if (normalized.endsWith('k')) {
      return Number.parseFloat(normalized) * 1000
    }
    if (normalized.endsWith('m')) {
      return Number.parseFloat(normalized) * 1000000
    }
    return Number.parseFloat(normalized) || 0
  }

  const sortedAgents = [...filteredAgents].sort((left, right) => {
    if (sortOption === 'Highest Rated') {
      return Number.parseFloat(right.rating) - Number.parseFloat(left.rating)
    }

    if (sortOption === 'Recently Synced') {
      const leftTime = left.syncedAt ? new Date(left.syncedAt).getTime() : 0
      const rightTime = right.syncedAt ? new Date(right.syncedAt).getTime() : 0
      return rightTime - leftTime
    }

    if (sortOption === 'Newest') {
      const leftTime = left.createdAt ? new Date(left.createdAt).getTime() : 0
      const rightTime = right.createdAt ? new Date(right.createdAt).getTime() : 0
      return rightTime - leftTime
    }

    return parseInstalls(right.installs) - parseInstalls(left.installs)
  })

  const visibleAgents = showAllAgents
    ? sortedAgents
    : sortedAgents.slice(0, INITIAL_VISIBLE_AGENTS)
  const remainingAgents = sortedAgents.length - visibleAgents.length
  const sectionTitle =
    activeFilter === 'All Agents' ? 'Popular Agents' : `${activeFilter} Agents`

  const handleDownload = async (agentId: string) => {
    setPendingAgentId(agentId)
    try {
      await downloadAgent(agentId)
      const refreshedAgents = await getAgents(true)
      setAgents(refreshedAgents)
      } catch (error) {
        console.error('Failed to download agent', error)
        setLoadError(error instanceof Error ? error.message : 'Failed to download agent')
      } finally {
      setPendingAgentId(null)
    }
  }

  const handleUninstall = async (agentId: string) => {
    setPendingAgentId(agentId)
    try {
      await uninstallAgent(agentId)
      const refreshedAgents = await getAgents(true)
      setAgents(refreshedAgents)
      } catch (error) {
        console.error('Failed to uninstall agent', error)
        setLoadError(error instanceof Error ? error.message : 'Failed to uninstall agent')
      } finally {
      setPendingAgentId(null)
    }
  }

  return (
    <section className="agent-section">
      <div className="agent-section__header">
        <h2>{sectionTitle}</h2>
        <span className="agent-section__summary">
          {sortedAgents.length} result{sortedAgents.length === 1 ? '' : 's'}
        </span>
      </div>

      {visibleAgents.length > 0 ? (
        <div className="agent-grid">
          {visibleAgents.map((agent) => (
            <BorderGlow
              key={agent.name}
              edgeSensitivity={78}
              glowColor="40 80 80"
              backgroundColor="#120F17"
              borderRadius={28}
              glowRadius={40}
              glowIntensity={1}
              coneSpread={25}
              animated={false}
              colors={['#c084fc', '#f472b6', '#38bdf8']}
            >
              <AgentCard
                agent={agent}
                isPending={pendingAgentId === agent.id}
                onDownload={handleDownload}
                onUninstall={handleUninstall}
              />
            </BorderGlow>
          ))}
        </div>
      ) : (
        <div className="agent-empty-state">
          <MaterialIcon name="filter_alt_off" />
          <p>
            {loadError
              ? `Unable to load agents: ${loadError}`
              : normalizedSearch
              ? 'No agents match this search and filter.'
              : 'No agents match this filter yet.'}
          </p>
        </div>
      )}

      <div className="market-pagination">
        <span>
          Showing {visibleAgents.length} of {sortedAgents.length} agents
        </span>
        {remainingAgents > 0 ? (
          <button type="button" onClick={() => setShowAllAgents(true)}>
            Load more agents
          </button>
        ) : null}
      </div>
    </section>
  )
}

export default AgentGrid

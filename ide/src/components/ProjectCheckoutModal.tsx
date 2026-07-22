import { useState } from 'react'

import type { AgentCardData } from './AgentCard'
import MaterialIcon from './MaterialIcon'
import { createProject } from '../lib/projects'

type ProjectCheckoutModalProps = {
  agents: AgentCardData[]
  onClose: () => void
  onRemoveAgent: (agentName: string) => void
  onSuccess?: () => void
}

function ProjectCheckoutModal({
  agents,
  onClose,
  onRemoveAgent,
  onSuccess,
}: ProjectCheckoutModalProps) {
  const [projectPath, setProjectPath] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projectDescription, setProjectDescription] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const isCreateEnabled = projectName.trim().length > 0 && projectDescription.trim().length > 0

  const handleCreateProject = async () => {
    if (!isCreateEnabled || isSubmitting) {
      return
    }

    setIsSubmitting(true)
    setSubmitError('')

    try {
      await createProject({
        name: projectName.trim(),
        description: projectDescription.trim(),
        agent_ids: agents.map((agent) => agent.id),
      })

      if (onSuccess) {
        onSuccess()
      } else {
        onClose()
      }
      window.dispatchEvent(new CustomEvent('project-created'))
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to create project')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="checkout-modal" role="presentation">
      <div className="checkout-modal__panel" role="dialog" aria-modal="true" aria-labelledby="checkout-title">
        <div className="checkout-modal__header">
          <div>
            <p className="label-text">Project Checkout</p>
            <h2 id="checkout-title">Create a new project</h2>
          </div>
          <button type="button" aria-label="Close checkout" onClick={onClose}>
            <MaterialIcon name="close" />
          </button>
        </div>

        <div className="checkout-modal__team">
          {agents.map((agent) => (
            <button
              aria-label={`Remove ${agent.name}`}
              key={agent.name}
              onClick={() => onRemoveAgent(agent.name)}
              type="button"
            >
              <MaterialIcon name="close" />
              <span>{agent.name}</span>
            </button>
          ))}
        </div>

        <form
          className="checkout-form"
          onSubmit={(e) => {
            e.preventDefault()
            void handleCreateProject()
          }}
        >
          <label>
            <span>Project name<span className="required"> *</span></span>
            <input
              type="text"
              placeholder="Customer support automation"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              required
            />
          </label>

          <label>
            <span>Project description<span className="required"> *</span></span>
            <textarea
              rows={10}
              placeholder="Describe what this agent team should build, automate, or maintain."
              value={projectDescription}
              onChange={(e) => setProjectDescription(e.target.value)}
              required
            />
          </label>

          <label>
            <span>GitHub repository</span>
            <input
              type="text"
              value={projectPath}
              placeholder="Enter GitHub repo to continue"
              onChange={(event) => setProjectPath(event.target.value)}
            />
          </label>

          <div className="checkout-form__actions">
            <button type="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" disabled={!isCreateEnabled || isSubmitting} aria-disabled={!isCreateEnabled || isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Project'}
            </button>
          </div>

          {submitError ? <p className="checkout-form__error">{submitError}</p> : null}
        </form>
      </div>
    </div>
  )
}

export default ProjectCheckoutModal

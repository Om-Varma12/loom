import MaterialIcon from "./MaterialIcon";
import type { AgentData } from "../lib/agents";

export type AgentCardData = AgentData;

type AgentCardProps = {
  agent: AgentData;
  isPending?: boolean;
  onDownload: (agentId: string) => void;
  onUninstall: (agentId: string) => void;
};

function AgentCard({
  agent,
  isPending = false,
  onDownload,
  onUninstall,
}: AgentCardProps) {
  return (
    <article
      className={`agent-card${agent.type === "Community" ? " agent-card--community" : ""}`}
    >
      <div className="agent-card__header">
        <div className="agent-card__identity">
          <div className={`market-icon market-icon--${agent.tone}`}>
            <MaterialIcon name={agent.icon} />
          </div>
          <div>
            <div className="agent-card__title-row">
              <h3>{agent.name}</h3>
              <span>{agent.version}</span>
            </div>
            <strong>{agent.type}</strong>
          </div>
        </div>

        <div className="agent-card__rating">
          <MaterialIcon name="star" />
          <span>{agent.rating}</span>
        </div>
      </div>

      <p className="agent-card__description">{agent.description}</p>

      <div className="agent-card__sources">
        {agent.sources.map((source) => (
          <button type="button" key={source}>
            {source}
          </button>
        ))}
      </div>

      <div className="agent-card__meta">
        <span>
          <MaterialIcon name="sync" /> {agent.synced}
        </span>
        <span>
          <MaterialIcon name="download" /> {agent.installs} installs
        </span>
      </div>

      <div className="agent-card__actions">
        <button
          className={
            agent.downloaded ? "agent-card__team-button--selected" : undefined
          }
          type="button"
          onClick={() => {
            if (!agent.downloaded) {
              onDownload(agent.id);
            }
          }}
          disabled={isPending}
        >
          <span className="agent-card__team-label">
            {isPending
              ? "Working..."
              : agent.downloaded
                ? "Downloaded"
                : "Download"}
          </span>
          {agent.downloaded ? (
            <span className="agent-card__team-remove-label">
              Installed in your workspace
            </span>
          ) : null}
        </button>
        {agent.downloaded ? (
          <button
            type="button"
            className="agent-card__secondary-action"
            onClick={() => onUninstall(agent.id)}
            disabled={isPending}
          >
            Uninstall
          </button>
        ) : (
          <a href="#">Details</a>
        )}
      </div>
    </article>
  );
}

export default AgentCard;

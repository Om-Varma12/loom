import { useState } from "react";
import type { AppPage } from "../components/Sidebar";
import MarketplacePage from "./MarketplacePage";
import WorkspacePage from "./WorkspacePage";
import "../App.css";

function Home() {
  const [page, setPage] = useState<AppPage>("chat");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const handleNavigate = (newPage: AppPage, agentId?: string | null) => {
    setPage(newPage);
    setSelectedAgentId(agentId || null);
  };

  if (page === "marketplace") {
    return (
      <MarketplacePage
        onNavigate={handleNavigate}
        initialSelectedAgentId={selectedAgentId}
      />
    );
  }

  return <WorkspacePage activePage={page} onNavigate={handleNavigate} />;
}

export default Home;

import { useEffect, useState, useRef } from "react";
import PromptComposer from "../components/PromptComposer";
import Sidebar, { type AppPage } from "../components/Sidebar";
import SuggestionGrid from "../components/SuggestionGrid";
import TopAppBar from "../components/TopAppBar";
import WorkspacePanel from "../components/WorkspacePanel";
import AgentTreePanel, { type TaskNode } from "../components/AgentTreePanel";
import SemanticChangeSummary, {
  type AgentChange,
} from "../components/SemanticChangeSummary";
import {
  developProjectStream,
  getChatDetail,
  getProject,
  getProjects,
  type ChatMessage,
  type Project,
} from "../lib/projects";
import {
  getDownloadedAgents,
  uninstallAgent,
  type AgentData,
} from "../lib/agents";
import AgentsPanel from "../components/AgentsPanel";
import ProjectsPanel from "../components/ProjectsPanel";

type WorkspacePageProps = {
  activePage: AppPage;
  onNavigate: (page: AppPage, agentId?: string | null) => void;
};

type ExecutionStep = {
  step: number;
  agent: string;
  task: string;
  status: "pending" | "running" | "completed" | "failed";
  files: string[];
};

type ChatSession = {
  projectId?: string;
  prompt: string;
  projectName: string;
  status: "idle" | "planning" | "running" | "completed" | "failed";
  steps: ExecutionStep[];
  elapsedTime: number;
  workspacePath: string;
  errors: string[];
  selectedAgentIds: string[];
  contextFiles: string[];
  qaResponse?: string;
  // Task graph for AgentTreePanel
  taskGraphNodes: TaskNode[];
  taskGraphLogs: string[];
  // Per-agent semantic changes for SemanticChangeSummary
  agentChanges: AgentChange[];
};

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

function getFileIcon(filename: string): string {
  if (filename.endsWith(".py")) return "code";
  if (filename.endsWith(".sql")) return "database";
  if (filename.endsWith(".yml") || filename.endsWith(".yaml"))
    return "settings";
  if (filename.endsWith(".md")) return "description";
  if (filename.endsWith(".txt")) return "description";
  if (
    filename.endsWith(".js") ||
    filename.endsWith(".ts") ||
    filename.endsWith(".tsx") ||
    filename.endsWith(".jsx")
  )
    return "code";
  return "description";
}

function getFileColorClass(filename: string): string {
  if (filename.endsWith(".py")) return "text-primary";
  if (filename.endsWith(".sql")) return "text-secondary";
  if (filename.endsWith(".yml") || filename.endsWith(".yaml"))
    return "text-on-surface-variant";
  if (filename.endsWith(".md")) return "text-secondary";
  if (
    filename.endsWith(".js") ||
    filename.endsWith(".ts") ||
    filename.endsWith(".tsx") ||
    filename.endsWith(".jsx")
  )
    return "text-[#61DAFB]";
  return "text-on-surface-variant";
}

function reconstructSessionFromMessages(
  sessionData: any,
  messages: ChatMessage[],
): ChatSession {
  const latestUserIndex = findLastIndex(
    messages,
    (m) => m.role === "user" && m.message_type === "text",
  );
  const latestPlanIndex = findLastIndex(
    messages,
    (m) => m.message_type === "task_plan",
  );

  // 1. Get the latest user prompt from messages
  const userMsg = latestUserIndex >= 0 ? messages[latestUserIndex] : undefined;
  const prompt = userMsg?.content?.text || sessionData.title || "";

  // 2. Get project name from messages or fallback
  const startMsg = messages.find(
    (m) =>
      m.role === "system" &&
      m.message_type === "system_event" &&
      m.content?.project_name,
  );
  const projectName = startMsg?.content?.project_name || "";

  // 3. Process steps
  let steps: ExecutionStep[] = [];

  // Find task plan if it exists
  const planMsg = latestPlanIndex >= 0 ? messages[latestPlanIndex] : undefined;
  if (planMsg && planMsg.content?.plan) {
    steps = planMsg.content.plan.map((step: any, idx: number) => ({
      step: step.step || idx + 1,
      agent: step.agent || "Unknown",
      task: step.task || "",
      status: "pending",
      files: [],
    }));
  }

  // Apply agent execution updates
  const executionMsgs = messages.filter(
    (m, index) =>
      m.message_type === "agent_execution" && index > latestPlanIndex,
  );
  executionMsgs.forEach((m) => {
    const completedIdx = m.content?.completed_step_idx;
    if (completedIdx !== undefined && steps[completedIdx]) {
      const stepErrors = m.content?.errors || [];
      steps[completedIdx].status =
        stepErrors.length > 0 ? "failed" : "completed";
      steps[completedIdx].files = m.content?.files || [];
    }
  });

  // 4. Get workspace path
  const fileWriterMsg = messages.find(
    (m) => m.message_type === "system_event" && m.content?.workspace_path,
  );
  const workspacePath = fileWriterMsg?.content?.workspace_path || "";

  // 5. Gather all errors
  const errors: string[] = [];
  messages.forEach((m) => {
    if (m.content?.errors) {
      errors.push(...m.content.errors);
    }
  });

  // 6. Status of the session
  let status: ChatSession["status"] = "completed";
  // If there's an error message or the execution failed, mark failed
  const errorMsg = messages.find(
    (m) =>
      m.message_type === "system_event" && m.content?.text?.includes("failed"),
  );
  if (errorMsg || errors.length > 0) {
    status = "failed";
  }

  // 6.5. Get QA response from messages if it exists
  const qaMsg = messages.find(
    (m) => m.role === "assistant" && m.message_type === "text",
  );
  const qaResponse = qaMsg?.content?.text || "";

  // 7. Calculate elapsed time if possible
  let elapsedTime = 0;
  if (messages.length > 1) {
    const firstTime = new Date(messages[0].created_at).getTime();
    const lastTime = new Date(
      messages[messages.length - 1].created_at,
    ).getTime();
    elapsedTime = Math.max(0, Math.floor((lastTime - firstTime) / 1000));
  }

  return {
    projectId: sessionData.project_id,
    prompt,
    projectName,
    status,
    steps,
    elapsedTime,
    workspacePath,
    errors,
    selectedAgentIds: [],
    contextFiles: [],
    qaResponse,
    taskGraphNodes: [],
    taskGraphLogs: [],
    agentChanges: [],
  };
}

function findLastIndex<T>(
  items: T[],
  predicate: (item: T, index: number) => boolean,
): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (predicate(items[index], index)) {
      return index;
    }
  }
  return -1;
}

function WorkspacePage({ activePage, onNavigate }: WorkspacePageProps) {
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const [downloadedAgents, setDownloadedAgents] = useState<AgentData[]>([]);

  const [confirmDeleteAgent, setConfirmDeleteAgent] =
    useState<AgentData | null>(null);

  const [selectedProjectId, setSelectedProjectId] =
    useState<string>("new-project");
  const [activeOverlayPanel, setActiveOverlayPanel] = useState<
    "explorer" | "agents" | "projects" | null
  >(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Sync selected project with active session when running
  useEffect(() => {
    if (activeSession?.projectId) {
      setSelectedProjectId(activeSession.projectId);
    }
  }, [activeSession?.projectId]);

  // Close overlay on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target as Node)
      ) {
        const target = event.target as HTMLElement;
        if (target.closest(".top-bar-toggle-btn")) {
          return; // Let toggle buttons handle themselves
        }
        setActiveOverlayPanel(null);
      }
    }
    if (activeOverlayPanel) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [activeOverlayPanel]);

  const [projects, setProjects] = useState<Project[]>([]);

  // Load projects on mount and listen to project-created
  useEffect(() => {
    async function loadProjects(force = false) {
      try {
        const data = await getProjects(force);
        setProjects(data);
      } catch (err) {
        console.error("Failed to load projects in WorkspacePage", err);
      }
    }
    void loadProjects();

    const handleProjectCreated = () => void loadProjects(true);
    window.addEventListener("project-created", handleProjectCreated);
    return () => {
      window.removeEventListener("project-created", handleProjectCreated);
    };
  }, []);

  // Load downloaded agents on mount and listen to agents-changed
  useEffect(() => {
    async function loadAgents() {
      try {
        const data = await getDownloadedAgents();
        setDownloadedAgents(data);
      } catch (err) {
        console.error("Failed to load agents in WorkspacePage", err);
      }
    }
    void loadAgents();

    const handleAgentsChanged = () => void loadAgents();
    window.addEventListener("agents-changed", handleAgentsChanged);
    return () => {
      window.removeEventListener("agents-changed", handleAgentsChanged);
    };
  }, []);

  const handleSelectChat = async (chatId: string) => {
    setActiveChatId(chatId);
    // Create a temporary loading state
    setActiveSession({
      prompt: "Loading chat session...",
      projectName: "",
      status: "planning",
      steps: [],
      elapsedTime: 0,
      workspacePath: "",
      errors: [],
      selectedAgentIds: [],
      contextFiles: [],
      taskGraphNodes: [],
      taskGraphLogs: [],
      agentChanges: [],
    });
    try {
      const chatDetail = await getChatDetail(chatId);
      const reconstructed = reconstructSessionFromMessages(
        chatDetail.session,
        chatDetail.messages,
      );
      if (reconstructed.projectId) {
        try {
          const projectData = await getProject(reconstructed.projectId);
          reconstructed.selectedAgentIds = projectData.agent_ids || [];
        } catch (err) {
          console.error("Failed to load project agents for chat detail", err);
        }
      }
      setActiveSession(reconstructed);
    } catch (err: any) {
      console.error("Failed to load chat details", err);
      setActiveSession({
        prompt: "Error loading chat",
        projectName: "",
        status: "failed",
        steps: [],
        elapsedTime: 0,
        workspacePath: "",
        errors: [
          `Failed to retrieve chat history: ${err.message || "Unknown error"}`,
        ],
        selectedAgentIds: [],
        contextFiles: [],
        taskGraphNodes: [],
        taskGraphLogs: [],
        agentChanges: [],
      });
    }
  };

  const handleSelectProject = (projectId: string, projectName: string) => {
    setActiveChatId(null);
    setSelectedProjectId(projectId);
    setActiveOverlayPanel("explorer");
    setActiveSession({
      projectId: projectId,
      prompt: "",
      projectName: projectName,
      status: "idle",
      steps: [],
      elapsedTime: 0,
      workspacePath: "",
      errors: [],
      selectedAgentIds: [],
      contextFiles: [],
      taskGraphNodes: [],
      taskGraphLogs: [],
      agentChanges: [],
    });
  };

  // Start incrementing timer when session is running
  useEffect(() => {
    if (
      activeSession &&
      (activeSession.status === "planning" ||
        activeSession.status === "running")
    ) {
      if (!timerRef.current) {
        timerRef.current = window.setInterval(() => {
          setActiveSession((curr) => {
            if (!curr) return null;
            return {
              ...curr,
              elapsedTime: curr.elapsedTime + 1,
            };
          });
        }, 1000);
      }
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [activeSession?.status]);

  const runPrompt = async (
    projectId: string,
    promptText: string,
    selectedAgentIds: string[],
    chatSessionId?: string | null,
    themeId?: string | null,
  ) => {
    if (!chatSessionId) {
      setActiveChatId(null);
    }
    const newSession: ChatSession = {
      projectId: projectId,
      prompt: promptText,
      projectName:
        activeSession?.projectId === projectId ? activeSession.projectName : "",
      status: "planning",
      steps: [],
      elapsedTime: 0,
      workspacePath:
        activeSession?.projectId === projectId
          ? activeSession.workspacePath
          : "",
      errors: [],
      selectedAgentIds,
      contextFiles: [],
      taskGraphNodes: [],
      taskGraphLogs: [],
      agentChanges: [],
    };
    setActiveSession(newSession);

    try {
      await developProjectStream(
        projectId,
        promptText,
        selectedAgentIds,
        (chunk) => {
          if (chunk.type === "start") {
            if (chunk.chat_id) {
              setActiveChatId(chunk.chat_id);
            }
            window.dispatchEvent(new CustomEvent("chat-created"));
          } else if (chunk.type === "complete" || chunk.type === "error") {
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent("chat-created"));
            }, 200);
          }

          setActiveSession((curr) => {
            if (!curr) return null;

            const updated = { ...curr };

            if (chunk.type === "start") {
              updated.projectName = chunk.project_name || "";
              updated.status = "planning";
            } else if (chunk.type === "context") {
              if (chunk.errors && chunk.errors.length > 0) {
                updated.errors = [...updated.errors, ...chunk.errors];
              }
            } else if (chunk.type === "folder_structure") {
              // Store planned dirs so the file explorer can show the skeleton
              // before any agent writes actual files.
              if (chunk.dirs && Array.isArray(chunk.dirs)) {
                updated.contextFiles = chunk.dirs;
              }
              if (chunk.errors && chunk.errors.length > 0) {
                updated.errors = [...updated.errors, ...chunk.errors];
              }
            } else if (chunk.type === "planner") {
              const planSteps = chunk.plan || [];
              updated.steps = planSteps.map((step: any, idx: number) => ({
                step: step.step || idx + 1,
                agent: step.agent || "Unknown",
                task: step.task || "",
                status: idx === 0 ? "running" : "pending",
                files: [],
              }));
              updated.status = "running";
              // Parse TaskGraph nodes if provided by the planner SSE event
              if (chunk.task_graph && Array.isArray(chunk.task_graph.nodes)) {
                updated.taskGraphNodes = chunk.task_graph.nodes.map(
                  (n: any) => ({
                    id: n.id,
                    parentId: n.parent_id ?? null,
                    agentId: n.agent_id,
                    task: n.task,
                    dependsOn: n.depends_on ?? [],
                    capabilityScore: n.capability_score,
                    selectionReasoning: n.selection_reasoning,
                  }),
                );
              }
              if (
                chunk.task_graph_logs &&
                Array.isArray(chunk.task_graph_logs)
              ) {
                updated.taskGraphLogs = chunk.task_graph_logs;
              }
            } else if (chunk.type === "executor") {
              const completedIdx = chunk.completed_step_idx;

              // Mark completed step
              if (updated.steps[completedIdx]) {
                updated.steps[completedIdx].status =
                  chunk.errors && chunk.errors.length > 0
                    ? "failed"
                    : "completed";
                updated.steps[completedIdx].files = chunk.files || [];
              }

              // Mark next step as running
              if (updated.steps[completedIdx + 1]) {
                updated.steps[completedIdx + 1].status = "running";
              }

              if (chunk.errors && chunk.errors.length > 0) {
                updated.errors = [...updated.errors, ...chunk.errors];
              }

              // Build AgentChange entry from patch metadata in executor chunk
              if (chunk.agent_id && chunk.patch) {
                const existingIdx = updated.agentChanges.findIndex(
                  (c: { agentId: string }) => c.agentId === chunk.agent_id,
                );
                const change = {
                  agentId: chunk.agent_id,
                  semanticSummary: chunk.patch.semantic_summary ?? [],
                  riskLevel: (chunk.patch.risk_level ?? "low") as
                    | "low"
                    | "medium"
                    | "high",
                  filesChanged: chunk.patch.total_files ?? 0,
                  linesChanged: chunk.patch.total_lines ?? 0,
                  withinBudget: chunk.patch.within_budget ?? true,
                  requiresApproval: chunk.patch.requires_approval ?? false,
                  buildStatus:
                    chunk.errors && chunk.errors.length > 0
                      ? "failed"
                      : "passed",
                  confidenceScore: chunk.confidence_score,
                };
                if (existingIdx >= 0) {
                  const newChanges = [...updated.agentChanges];
                  newChanges[existingIdx] = change;
                  updated.agentChanges = newChanges;
                } else {
                  updated.agentChanges = [...updated.agentChanges, change];
                }
              }

              // Update task graph logs if provided
              if (chunk.task_graph_log) {
                updated.taskGraphLogs = [
                  ...updated.taskGraphLogs,
                  chunk.task_graph_log,
                ];
              }
            } else if (chunk.type === "file_writer") {
              updated.workspacePath = chunk.workspace_path || "";
              if (chunk.errors && chunk.errors.length > 0) {
                updated.errors = [...updated.errors, ...chunk.errors];
              }
            } else if (chunk.type === "qa") {
              updated.qaResponse = chunk.message || "";
            } else if (chunk.type === "complete") {
              updated.steps = updated.steps.map((s) =>
                s.status === "running" || s.status === "pending"
                  ? { ...s, status: "completed" }
                  : s,
              );
              updated.status = "completed";
            } else if (chunk.type === "error") {
              updated.errors = [...updated.errors, chunk.message];
              updated.status = "failed";
            }

            return updated;
          });
        },
        chatSessionId,
        themeId,
      );
    } catch (err: any) {
      setActiveSession((curr) => {
        if (!curr) return null;
        return {
          ...curr,
          status: "failed",
          errors: [...curr.errors, err.message || "Stream connection error"],
        };
      });
    }
  };

  const handleSendPrompt = async (
    projectId: string,
    promptText: string,
    selectedAgentIds: string[],
    themeId?: string | null,
  ) => {
    await runPrompt(projectId, promptText, selectedAgentIds, null, themeId);
  };

  const handleSendActivePrompt = async (
    projectId: string,
    promptText: string,
    selectedAgentIds: string[],
    themeId?: string | null,
  ) => {
    if (!promptText.trim() || isDeveloping || !activeSession?.projectId) {
      return;
    }
    const agentIds =
      selectedAgentIds.length > 0
        ? selectedAgentIds
        : activeSession.selectedAgentIds || [];
    await runPrompt(projectId, promptText.trim(), agentIds, activeChatId, themeId);
  };

  const isDeveloping = activeSession
    ? activeSession.status === "planning" || activeSession.status === "running"
    : false;

  return (
    <div className="h-screen w-full flex overflow-hidden ">
      {/* Sidebar Component */}
      <Sidebar
        activePage={activePage}
        onNavigate={(page, agentId) => {
          if (page === "chat") {
            setActiveSession(null);
            setActiveChatId(null);
          }
          onNavigate(page, agentId);
        }}
        activeChatId={activeChatId}
        onSelectChat={handleSelectChat}
        onSelectProject={handleSelectProject}
        onSelectAgents={() => {
          if (activeOverlayPanel === "agents") {
            setActiveOverlayPanel(null);
          } else {
            setActiveOverlayPanel("agents");
          }
        }}
        isAgentsActive={activeOverlayPanel === "agents"}
        onSelectProjectsList={() => {
          if (activeOverlayPanel === "projects") {
            setActiveOverlayPanel(null);
          } else {
            setActiveOverlayPanel("projects");
          }
        }}
        isProjectsListActive={activeOverlayPanel === "projects"}
      />

      {/* Main Content Pane */}
      <main className="flex-1 flex flex-col h-full bg-[#101010] relative overflow-hidden">
        {/* Dynamic Top Header */}
        <TopAppBar
          projectName={activeSession?.projectName}
          prompt={activeSession?.prompt}
          isSessionActive={!!activeSession}
          activeOverlayPanel={activeOverlayPanel}
          setActiveOverlayPanel={setActiveOverlayPanel}
          isProjectSelected={
            selectedProjectId !== "" && selectedProjectId !== "new-project"
          }
        />

        {activeSession ? (
          /* Active session layout matching reference-chat-middle.html */
          <div className="flex-1 flex overflow-hidden pt-14">
            {/* Left Canvas (Chat & Logs + Input Box) */}
            <div className="flex-1 flex flex-col relative h-full min-w-0">
              {/* Scrollable Chat Feed */}
              <div className="flex-1 flex flex-col overflow-y-auto scroll-smooth pb-44 hide-scrollbar">
                <div className="max-w-3xl mx-auto w-full px-6 py-8 flex flex-col gap-8">
                  {/* User Prompt Card */}
                  {/* <div className="glass-panel p-6 rounded-xl flex gap-4 border border-[#262626] animate-step-fade-in">
                    <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center shrink-0">
                      <span className="material-symbols-outlined text-[18px] text-on-surface-variant">person</span>
                    </div>
                    <div className="font-body-sm text-body-sm text-on-surface leading-relaxed whitespace-pre-wrap flex-1">
                      {activeSession.prompt}
                    </div>
                  </div> */}

                  {/* AI Agent Activity Feed */}
                  <div className="flex flex-col gap-6 ml-2">
                    {/* Status Header */}
                    <div
                      className="flex items-center gap-3 text-on-surface-variant font-code-md text-[12px] animate-step-fade-in"
                      style={{ animationDelay: "0.1s" }}
                    >
                      <span
                        className={`material-symbols-outlined text-[16px] ${isDeveloping ? "animate-spin" : ""}`}
                      >
                        {isDeveloping ? "progress_activity" : "schedule"}
                      </span>
                      <span>
                        {activeSession.status === "completed"
                          ? `Worked for ${formatTime(activeSession.elapsedTime)}`
                          : activeSession.status === "failed"
                            ? `Stopped after ${formatTime(activeSession.elapsedTime)}`
                            : `Working... (${formatTime(activeSession.elapsedTime)})`}
                      </span>
                      <span className="material-symbols-outlined text-[16px]">
                        chevron_right
                      </span>
                    </div>

                    {/* Activity Log */}
                    <div className="flex flex-col gap-4 font-body-sm text-body-sm">
                      <p
                        className="text-primary font-medium animate-step-fade-in"
                        style={{ animationDelay: "0.15s" }}
                      >
                        {activeSession.status === "planning" &&
                          "Formulating multi-agent build plan..."}
                        {activeSession.status === "running" &&
                          "Executing step-by-step developer graph..."}
                        {activeSession.status === "completed" &&
                          `Successfully completed project ${activeSession.projectName}!`}
                        {activeSession.status === "failed" &&
                          "Development execution halted due to errors."}
                      </p>

                      {activeSession.qaResponse && (
                        <div className="glass-panel p-6 rounded-xl border border-outline-variant/30 bg-[#161616]/50 animate-step-fade-in text-[14px] leading-relaxed text-on-surface whitespace-pre-wrap">
                          {activeSession.qaResponse}
                        </div>
                      )}

                      {/* Folder Structure Card — shown as soon as folder_structure SSE event arrives */}
                      {activeSession.contextFiles &&
                        activeSession.contextFiles.length > 0 && (
                          <div
                            className="flex flex-col gap-2 animate-step-fade-in"
                            style={{ animationDelay: "0.18s" }}
                          >
                            <div className="flex items-center gap-2 text-on-surface-variant text-[12px] font-medium uppercase tracking-widest">
                              <span className="material-symbols-outlined text-[15px] text-secondary">
                                folder
                              </span>
                              Project Structure Planned
                            </div>
                            <div className="glass-panel rounded-xl border border-outline-variant/20 bg-[#0e0e0e]/60 overflow-hidden">
                              <div className="px-4 py-3 border-b border-outline-variant/10 flex items-center gap-2">
                                <span className="material-symbols-outlined text-[14px] text-secondary">
                                  account_tree
                                </span>
                                <span className="font-code-md text-[11px] text-on-surface-variant">
                                  {activeSession.contextFiles.length}{" "}
                                  directories pre-created in sandbox
                                </span>
                              </div>
                              <div className="px-4 py-3 font-mono text-[12px] text-secondary leading-[1.9] max-h-48 overflow-y-auto">
                                {activeSession.contextFiles
                                  .slice()
                                  .sort()
                                  .map((dir, i) => {
                                    const depth =
                                      (dir.match(/\//g) || []).length;
                                    return (
                                      <div
                                        key={i}
                                        className="flex items-center gap-1.5 text-on-surface-variant/80"
                                        style={{
                                          paddingLeft: `${depth * 14}px`,
                                        }}
                                      >
                                        <span className="material-symbols-outlined text-[12px] text-secondary/60">
                                          folder_open
                                        </span>
                                        <span>{dir.split("/").pop()}/</span>
                                      </div>
                                    );
                                  })}
                              </div>
                            </div>
                          </div>
                        )}

                      {/* Agent Execution Tree — shown when task graph is available */}
                      {activeSession.taskGraphNodes.length > 0 && (
                        <AgentTreePanel
                          nodes={activeSession.taskGraphNodes}
                          logs={activeSession.taskGraphLogs}
                          isRunning={isDeveloping}
                        />
                      )}

                      {activeSession.steps.length > 0 ? (
                        <ul className="flex flex-col gap-4 pl-1">
                          {activeSession.steps.map((step, idx) => {
                            let bulletColor = "bg-[#404040]";
                            if (step.status === "completed")
                              bulletColor = "bg-tertiary-fixed-dim";
                            else if (step.status === "failed")
                              bulletColor = "bg-[#ef4444]";
                            else if (step.status === "running")
                              bulletColor =
                                "bg-secondary-container pulse-glow ring-2 ring-secondary-container/20";

                            return (
                              <li
                                key={idx}
                                className="flex gap-3 animate-step-fade-in"
                                style={{
                                  animationDelay: `${0.2 + idx * 0.08}s`,
                                }}
                              >
                                <div
                                  className={`mt-2 w-1.5 h-1.5 rounded-full shrink-0 ${bulletColor}`}
                                />
                                <div className="flex flex-col gap-1.5 flex-1">
                                  <div className="flex items-center gap-2">
                                    <span className="text-primary font-medium">
                                      {step.agent
                                        .replace("_", " ")
                                        .replace(/\b\w/g, (c) =>
                                          c.toUpperCase(),
                                        )}{" "}
                                      Agent
                                    </span>
                                    {step.status === "running" && (
                                      <span className="text-[11px] font-label-caps bg-secondary-container/20 text-secondary px-2 py-0.5 rounded-full animate-pulse">
                                        active
                                      </span>
                                    )}
                                    {step.status === "completed" && (
                                      <span className="material-symbols-outlined text-[16px] text-tertiary-fixed-dim">
                                        check_circle
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-on-surface-variant text-[13px] leading-relaxed">
                                    {step.task}
                                  </div>

                                  {/* Generated File list under the completed step */}
                                  {step.files && step.files.length > 0 && (
                                    <div className="flex flex-col gap-1.5 pl-4 border-l border-[#262626] mt-2">
                                      {step.files.map((file, fileIdx) => (
                                        <div
                                          key={fileIdx}
                                          className="flex items-center gap-2 animate-file-slide-in"
                                          style={{
                                            animationDelay: `${0.15 + fileIdx * 0.05}s`,
                                          }}
                                        >
                                          <span
                                            className={`material-symbols-outlined text-[14px] ${getFileColorClass(file)}`}
                                          >
                                            {getFileIcon(file)}
                                          </span>
                                          <span className="font-code-md text-[13px] text-secondary">
                                            {file}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        activeSession.status === "planning" && (
                          <div className="flex items-center gap-2 text-on-surface-variant font-code-md text-[13px] animate-pulse">
                            <span className="material-symbols-outlined animate-spin text-[16px]">
                              sync
                            </span>
                            <span>Consulting planner agent...</span>
                          </div>
                        )
                      )}

                      {/* Workspace Path Success Panel */}
                      {activeSession.workspacePath && (
                        <div
                          className="mt-4 glass-panel p-4 rounded-xl flex items-center justify-between border-[#262626] animate-step-fade-in"
                          style={{ animationDelay: "0.4s" }}
                        >
                          <div className="flex items-center gap-3 font-code-md text-[13px]">
                            <span className="material-symbols-outlined text-tertiary-fixed-dim text-[18px]">
                              folder_open
                            </span>
                            <span className="text-on-surface-variant">
                              Workspace folder generated:{" "}
                              <strong className="text-primary font-medium">
                                {activeSession.workspacePath}
                              </strong>
                            </span>
                          </div>
                        </div>
                      )}

                      {/* Errors Panel */}
                      {activeSession.errors &&
                        activeSession.errors.length > 0 && (
                          <div
                            className="mt-4 glass-panel p-4 rounded-xl border-[#ef4444]/20 bg-[#ef4444]/5 animate-step-fade-in"
                            style={{ animationDelay: "0.4s" }}
                          >
                            <div className="flex items-center gap-2 text-[#ef4444] font-semibold text-[14px] mb-2">
                              <span className="material-symbols-outlined">
                                error
                              </span>
                              <span>Errors encountered during execution:</span>
                            </div>
                            <ul className="list-disc pl-5 text-[13px] text-[#ef4444]/80 flex flex-col gap-1">
                              {activeSession.errors.map((err, errIdx) => (
                                <li key={errIdx}>{err}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                      {/* Semantic Change Summary — shown after run completes */}
                      <SemanticChangeSummary
                        changes={activeSession.agentChanges}
                        isVisible={
                          activeSession.status === "completed" ||
                          activeSession.status === "failed"
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Sticky Prompt Composer at the Bottom of Left Pane */}
              <div className="absolute bottom-6 left-0 right-0 z-10 flex justify-center px-5 pointer-events-none">
                <div className="w-full max-w-205 pointer-events-auto">
                  <PromptComposer
                    selectedProjectId={activeSession.projectId || selectedProjectId}
                    setSelectedProjectId={setSelectedProjectId}
                    onSendPrompt={handleSendActivePrompt}
                    isDevelopingProps={isDeveloping}
                    defaultSelectedAgentIds={activeSession.selectedAgentIds}
                    lockProjectSelection
                    placeholder="Ask for follow-up changes"
                  />
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Idle landing view matching reference.html */
          <div className="flex-1 flex overflow-hidden pt-14 relative w-full h-full">
            <div className="flex-1 flex flex-col items-center justify-center px-6 relative z-10 w-full max-w-5xl mx-auto min-w-0 h-full overflow-y-auto">
              {/* Main Title */}
              <h1
                className="font-headline-lg text-headline-lg text-white mb-12 text-center max-w-2xl text-[32px] font-bold tracking-tight animate-step-fade-in"
                style={{ animationDelay: "0.1s" }}
              >
                What should we build in L00m?
              </h1>

              {/* Central Controls Container */}
              <div
                className="w-full max-w-5xl space-y-4 animate-step-fade-in"
                style={{ animationDelay: "0.2s" }}
              >
                {/* Prompt Composer */}
                <PromptComposer
                  selectedProjectId={selectedProjectId}
                  setSelectedProjectId={setSelectedProjectId}
                  onSendPrompt={handleSendPrompt}
                  isDevelopingProps={isDeveloping}
                />
              </div>

              {/* Suggestion Grid */}
              <div
                className="animate-step-fade-in w-full flex justify-center mt-4"
                style={{ animationDelay: "0.3s" }}
              >
                <SuggestionGrid />
              </div>

              {/* Atmospheric background glows */}
              <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-20 z-0 select-none">
                <div className="absolute -top-1/4 -right-1/4 w-200 h-200 bg-secondary-container blur-[160px] rounded-full opacity-10" />
                <div className="absolute -bottom-1/4 -left-1/4 w-150 h-150 bg-primary-container blur-[160px] rounded-full opacity-5" />
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Floating Overlay Panels */}
      {activeOverlayPanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Optional backdrop */}
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setActiveOverlayPanel(null)}
          />

          <div
            ref={panelRef}
            className={`relative animate-step-fade-in ${
              activeOverlayPanel === "explorer"
                ? "w-full max-w-6xl h-[80vh]"
                : "w-full max-w-5xl h-175 px-6"
            }`}
          >
            {activeOverlayPanel === "agents" ? (
              <AgentsPanel
                downloadedAgents={downloadedAgents}
                onUninstallClick={(agent) => setConfirmDeleteAgent(agent)}
                onClose={() => setActiveOverlayPanel(null)}
                onNavigateToMarketplace={(agentId) =>
                  onNavigate("marketplace", agentId)
                }
              />
            ) : activeOverlayPanel === "projects" ? (
              <ProjectsPanel
                projects={projects}
                onSelectProject={(projectId, projectName) => {
                  handleSelectProject(projectId, projectName);
                  setActiveOverlayPanel("explorer");
                }}
                onClose={() => setActiveOverlayPanel(null)}
              />
            ) : (
              <WorkspacePanel
                projectId={selectedProjectId}
                projectName={
                  projects.find((p) => p.id === selectedProjectId)?.name ||
                  "Project"
                }
                onClose={() => setActiveOverlayPanel(null)}
                status={activeSession?.status || "idle"}
              />
            )}
          </div>
        </div>
      )}
      {/* Delete Agent Confirmation Modal */}
      {confirmDeleteAgent && (
        <div className="checkout-modal z-100" role="presentation">
          <div
            className="checkout-modal__panel max-w-110"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-confirm-title"
          >
            <div className="checkout-modal__header">
              <div>
                <p className="label-text text-red-500">Uninstall Agent</p>
                <h2 id="delete-confirm-title">Confirm Removal</h2>
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setConfirmDeleteAgent(null)}
                className="text-on-surface-variant hover:text-white"
              >
                <span className="material-symbols-outlined text-[20px]">
                  close
                </span>
              </button>
            </div>
            <div className="p-6">
              <p className="text-[13px] text-on-surface-variant leading-relaxed">
                Are you sure you want to remove{" "}
                <strong>{confirmDeleteAgent.name}</strong> from your account?
                This will uninstall the agent from your workspace.
              </p>
              <div className="flex justify-end gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => setConfirmDeleteAgent(null)}
                  className="px-4 py-2 border border-outline-variant hover:bg-[#262626] rounded-lg text-[12px] font-medium text-on-surface transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const agentId = confirmDeleteAgent.id;
                    setConfirmDeleteAgent(null);
                    try {
                      await uninstallAgent(agentId);
                    } catch (err) {
                      console.error("Failed to uninstall agent", err);
                    }
                  }}
                  className="px-4 py-2 bg-error hover:bg-error/90 text-on-error rounded-lg text-[12px] font-medium transition-colors cursor-pointer"
                >
                  Uninstall
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default WorkspacePage;

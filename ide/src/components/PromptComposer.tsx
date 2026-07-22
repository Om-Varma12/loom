import {
  type ChangeEvent,
  type Dispatch,
  type KeyboardEvent,
  type SetStateAction,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  createProject,
  getProjects,
  developProject,
  type Project,
} from "../lib/projects";
import { getDownloadedAgents, type AgentData } from "../lib/agents";
import { getThemes, type ThemeMetadata } from "../lib/themes";

type PromptComposerProps = {
  selectedProjectId: string;
  setSelectedProjectId: Dispatch<SetStateAction<string>>;
  onSendPrompt?: (
    projectId: string,
    prompt: string,
    selectedAgentIds: string[],
    themeId?: string | null,
  ) => Promise<void> | void;
  isDevelopingProps?: boolean;
  defaultSelectedAgentIds?: string[];
  lockProjectSelection?: boolean;
  placeholder?: string;
};

function PromptComposer({
  selectedProjectId,
  setSelectedProjectId,
  onSendPrompt,
  isDevelopingProps,
  defaultSelectedAgentIds,
  lockProjectSelection = false,
  placeholder = "How can i help you today?",
}: PromptComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [prompt, setPrompt] = useState("");
  const [newProjectName, setNewProjectName] = useState("");
  const [isDevelopingState, setIsDevelopingState] = useState(false);
  const isDeveloping =
    isDevelopingProps !== undefined ? isDevelopingProps : isDevelopingState;
  const [developError, setDevelopError] = useState("");
  const [developSuccess, setDevelopSuccess] = useState("");

  // Composer states for permission, model, agents, and ripple effect
  const [permission, setPermission] = useState("default");
  const [selectedModel, setSelectedModel] = useState("gemini-1.5-pro");
  const [projects, setProjects] = useState<Project[]>([]);
  const [downloadedAgents, setDownloadedAgents] = useState<AgentData[]>([]);
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isAgentModalOpen, setIsAgentModalOpen] = useState(false);
  const [localSelectedProjectId, setLocalSelectedProjectId] = useState("");
  const [localSelectedAgents, setLocalSelectedAgents] = useState<string[]>([]);
  const [isRippling, setIsRippling] = useState(false);

  // ── Theme Selector state ──────────────────────────────────────────────────
  const [themes, setThemes] = useState<ThemeMetadata[]>([]);
  const [selectedThemeId, setSelectedThemeId] = useState<string | null>(null);
  const [isThemeModalOpen, setIsThemeModalOpen] = useState(false);
  const [localSelectedThemeId, setLocalSelectedThemeId] = useState<
    string | null
  >(null);
  const [isLoadingThemes, setIsLoadingThemes] = useState(false);

  // Detect whether the Streamlit agent is among the selected agents.
  // We match by name (case-insensitive) to avoid hardcoding an agent ID.
  const isStreamlitSelected = downloadedAgents.some(
    (a) =>
      selectedAgents.includes(a.id) &&
      a.name.toLowerCase().includes("streamlit"),
  );

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setPrompt(event.target.value);

    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  };

  const handleSend = async () => {
    if (
      !prompt.trim() ||
      !selectedProjectId ||
      selectedAgents.length === 0 ||
      isDeveloping
    ) {
      return;
    }

    if (selectedProjectId === "new-project" && !newProjectName.trim()) {
      setDevelopError("Please enter a project name for the new project.");
      return;
    }

    // Trigger Siri-like ripple effect for 2.5 seconds
    setIsRippling(true);
    setTimeout(() => {
      setIsRippling(false);
    }, 2500);

    let projectIdToDevelop = selectedProjectId;

    if (selectedProjectId === "new-project") {
      setIsDevelopingState(true);
      setDevelopError("");
      setDevelopSuccess("");
      try {
        const newProj = await createProject({
          name: newProjectName.trim(),
          description: `Created for: ${prompt.trim().substring(0, 100)}`,
          agent_ids: selectedAgents,
        });
        projectIdToDevelop = newProj.project_id;
        // Dispatch event to notify Sidebar and other components
        window.dispatchEvent(new CustomEvent("project-created"));
        setNewProjectName("");
      } catch (err: any) {
        setDevelopError(err.message || "Failed to create new project");
        setIsDevelopingState(false);
        return;
      }
    }

    // Only pass themeId when the Streamlit agent is selected
    const themeIdToSend = isStreamlitSelected ? selectedThemeId : null;

    if (onSendPrompt) {
      void onSendPrompt(
        projectIdToDevelop,
        prompt.trim(),
        selectedAgents,
        themeIdToSend,
      );
      setPrompt("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
      return;
    }

    setIsDevelopingState(true);
    setDevelopError("");
    setDevelopSuccess("");

    try {
      const result = await developProject(
        projectIdToDevelop,
        prompt.trim(),
        selectedAgents,
        null,
        themeIdToSend,
      );
      let successMsg = `Successfully developed project! Files written to: ${result.workspace_path}`;
      if (result.errors && result.errors.length > 0) {
        successMsg += ` (with errors: ${result.errors.join(", ")})`;
      }
      setDevelopSuccess(successMsg);
      setPrompt("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    } catch (error) {
      setDevelopError(
        error instanceof Error ? error.message : "Failed to develop project",
      );
    } finally {
      setIsDevelopingState(false);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  useEffect(() => {
    let active = true;

    async function loadComposerData(force = false) {
      try {
        const [projectData, downloadedAgentData] = await Promise.all([
          getProjects(force),
          getDownloadedAgents(force),
        ]);
        if (!active) {
          return;
        }

        setProjects(projectData);
        setDownloadedAgents(downloadedAgentData);
        setSelectedProjectId((currentProjectId) => {
          if (currentProjectId === "new-project") {
            return "new-project";
          }
          if (projectData.some((project) => project.id === currentProjectId)) {
            return currentProjectId;
          }

          return "new-project";
        });
        setSelectedAgents((currentSelectedAgents) => {
          const availableAgentIds = new Set(
            downloadedAgentData.map((agent) => agent.id),
          );
          const preferredAgentIds =
            defaultSelectedAgentIds && defaultSelectedAgentIds.length > 0
              ? defaultSelectedAgentIds
              : currentSelectedAgents;
          const filteredAgentIds = preferredAgentIds.filter((agentId) =>
            availableAgentIds.has(agentId),
          );

          if (filteredAgentIds.length > 0) {
            return filteredAgentIds;
          }

          return downloadedAgentData.slice(0, 2).map((agent) => agent.id);
        });
      } catch (error) {
        console.error("Failed to load composer data", error);
      }
    }

    void loadComposerData();

    const handleProjectCreated = () => {
      void loadComposerData(true);
    };
    const handleAgentsChanged = () => {
      void loadComposerData(true);
    };

    window.addEventListener("project-created", handleProjectCreated);
    window.addEventListener("agents-changed", handleAgentsChanged);

    return () => {
      active = false;
      window.removeEventListener("project-created", handleProjectCreated);
      window.removeEventListener("agents-changed", handleAgentsChanged);
    };
  }, [defaultSelectedAgentIds]);

  useEffect(() => {
    if (!defaultSelectedAgentIds || defaultSelectedAgentIds.length === 0) {
      return;
    }
    const availableAgentIds = new Set(downloadedAgents.map((agent) => agent.id));
    const nextSelectedAgents = defaultSelectedAgentIds.filter((agentId) =>
      availableAgentIds.has(agentId),
    );
    if (nextSelectedAgents.length > 0) {
      setSelectedAgents(nextSelectedAgents);
    }
  }, [defaultSelectedAgentIds, downloadedAgents]);

  // ── Fetch themes when Streamlit agent becomes selected ────────────────────
  useEffect(() => {
    if (!isStreamlitSelected) {
      // Clear theme selection when Streamlit is deselected
      setSelectedThemeId(null);
      setThemes([]);
      return;
    }

    let active = true;
    setIsLoadingThemes(true);

    getThemes().then((data) => {
      if (active) {
        setThemes(data);
        setIsLoadingThemes(false);
      }
    });

    return () => {
      active = false;
    };
  }, [isStreamlitSelected]);

  // ── Derived values ────────────────────────────────────────────────────────
  const selectedTheme = themes.find((t) => t.id === selectedThemeId) ?? null;

  return (
    <section className="w-full relative" aria-label="Project prompt composer">
      {/* Siri style tag for keyframe animations */}
      <style>{`
        @keyframes siri-ripple {
          0% {
            box-shadow: 0 0 0 0 rgba(147, 51, 234, 0.6), 0 0 0 0 rgba(59, 130, 246, 0.4);
          }
          50% {
            box-shadow: 0 0 0 10px rgba(147, 51, 234, 0.3), 0 0 0 20px rgba(59, 130, 246, 0.1);
          }
          100% {
            box-shadow: 0 0 0 20px rgba(147, 51, 234, 0), 0 0 0 30px rgba(59, 130, 246, 0);
          }
        }
        @keyframes border-glow {
          0%, 100% {
            border-color: rgba(147, 51, 234, 0.8);
          }
          50% {
            border-color: rgba(59, 130, 246, 0.8);
          }
        }
        .siri-active {
          animation: border-glow 1.2s infinite ease-in-out !important;
        }
        .siri-ripple-container {
          position: absolute;
          inset: -2px;
          border-radius: 26px;
          pointer-events: none;
          z-index: 0;
          animation: siri-ripple 1.2s infinite cubic-bezier(0.1, 0.8, 0.3, 1);
        }
        /* Hide native arrow and style select elements completely */
        select {
          -webkit-appearance: none !important;
          -moz-appearance: none !important;
          appearance: none !important;
          background-color: transparent !important;
          color: inherit !important;
          border: none !important;
        }
        select::-ms-expand {
          display: none !important;
        }
        /* Style select options for dark theme */
        select option {
          background-color: #171717 !important;
          color: #e5e2e1 !important;
        }
        /* Theme button entrance animation */
        @keyframes theme-btn-in {
          from { opacity: 0; transform: scale(0.85) translateX(-6px); }
          to   { opacity: 1; transform: scale(1)    translateX(0); }
        }
        .theme-btn-enter {
          animation: theme-btn-in 0.22s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }
      `}</style>

      <div className="relative group">
        {isRippling && <div className="siri-ripple-container" />}

        <div
          className={`bg-surface-container-low border border-outline-variant rounded-3xl flex flex-col shadow-2xl relative z-10 transition-colors duration-300 ${isRippling ? "siri-active" : ""}`}
        >
          {/* Project Name Input */}
          {selectedProjectId === "new-project" && !lockProjectSelection && (
            <div className="px-6 pt-5 pb-2 border-b border-outline-variant/30 flex items-center gap-2">
              <span className="material-symbols-outlined text-[18px] text-on-surface-variant">
                create_new_folder
              </span>
              <input
                type="text"
                className="w-full bg-transparent border-none outline-none focus:ring-0 text-primary placeholder:text-outline/40 text-[14px] font-medium p-0"
                placeholder="Enter new project name (e.g., Task Manager)"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                disabled={isDeveloping}
              />
            </div>
          )}
          {/* Text Area */}
          <div className="p-6">
            <textarea
              aria-label="Prompt"
              className="w-full bg-transparent border-none outline-none focus:ring-0 focus:border-transparent focus:outline-none font-body-lg text-body-lg text-on-surface resize-none placeholder:text-outline/60 p-0 m-0 max-h-[220px] overflow-y-auto"
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              ref={textareaRef}
              rows={2}
              value={prompt}
              disabled={isDeveloping}
            />
          </div>

          {/* Action Bar */}
          <div className="flex flex-wrap items-center justify-between px-4 py-3 border-t border-outline-variant/50 bg-surface-container-lowest/50 gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {/* Project Selector */}
              <button
                type="button"
                onClick={() => {
                  if (lockProjectSelection) {
                    return;
                  }
                  setLocalSelectedProjectId(selectedProjectId);
                  setIsProjectModalOpen(true);
                }}
                disabled={isDeveloping || lockProjectSelection}
                className={`flex items-center gap-1.5 px-3 py-1 text-on-surface-variant rounded-full border border-outline-variant/30 transition-colors max-w-55 text-left select-none ${
                  isDeveloping || lockProjectSelection
                    ? "opacity-80 cursor-default"
                    : "hover:text-white hover:bg-surface-variant/30 cursor-pointer"
                }`}
              >
                <span className="material-symbols-outlined text-[16px] pointer-events-none">
                  folder
                </span>
                <span className="font-label-caps text-[11px] truncate pointer-events-none">
                  {selectedProjectId === "new-project"
                    ? "Create New Project"
                    : projects.find((p) => p.id === selectedProjectId)?.name ||
                      "Select Project"}
                </span>
                <span className="material-symbols-outlined text-[16px] pointer-events-none">
                  keyboard_arrow_down
                </span>
              </button>

              {/* Permission Selector */}
              <div className="flex items-center gap-1.5 px-4 py-1 text-on-surface-variant hover:text-white rounded-full border border-outline-variant/30 hover:bg-surface-variant/30 transition-colors relative cursor-pointer">
                <span className="material-symbols-outlined text-[16px] pointer-events-none">
                  back_hand
                </span>
                <select
                  aria-label="Permission level"
                  className="bg-transparent border-none outline-none focus:ring-0 focus:border-transparent focus:outline-none text-inherit font-inherit font-label-caps text-[11px] py-0 pl-0 pr-4 cursor-pointer select-none appearance-none"
                  value={permission}
                  onChange={(e) => setPermission(e.target.value)}
                  disabled={isDeveloping}
                  style={{ paddingRight: "12px" }}
                >
                  <option
                    value="default"
                    className="bg-surface text-on-surface"
                  >
                    Default permissions
                  </option>
                  <option
                    value="auto-review"
                    className="bg-surface text-on-surface"
                  >
                    Auto-review
                  </option>
                  <option
                    value="full-access"
                    className="bg-surface text-on-surface"
                  >
                    Full Access
                  </option>
                </select>
                <span className="material-symbols-outlined text-[16px] absolute right-2 pointer-events-none">
                  keyboard_arrow_down
                </span>
              </div>

              {/* Model Selector */}
              <div className="flex items-center gap-1.5 px-3 py-1 text-on-surface-variant hover:text-white rounded-full border border-outline-variant/30 hover:bg-surface-variant/30 transition-colors relative cursor-pointer">
                <select
                  aria-label="Select model"
                  className="bg-transparent border-none outline-none focus:ring-0 focus:border-transparent focus:outline-none text-inherit font-inherit font-label-caps text-[11px] py-0 pl-0 pr-4 cursor-pointer select-none appearance-none"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  disabled={isDeveloping}
                  style={{ paddingRight: "12px" }}
                >
                  <option
                    value="LooM-1.0 (low)"
                    className="bg-surface text-on-surface"
                  >
                    LooM 1.0 (Low)
                  </option>
                  <option
                    value="LooM-1.0 (medium)"
                    className="bg-surface text-on-surface"
                  >
                    LooM 2.0 (Medium)
                  </option>
                  <option
                    value="LooM-1.0 (high)"
                    className="bg-surface text-on-surface"
                  >
                    LooM 1.0 (High)
                  </option>
                </select>
              </div>

              {/* ── Theme Selector — only visible when Streamlit agent is selected ── */}
              {isStreamlitSelected && (
                <button
                  id="theme-selector-btn"
                  type="button"
                  className={`theme-btn-enter flex items-center gap-1.5 px-3 py-1 rounded-full border transition-all duration-200 text-left select-none cursor-pointer ${
                    selectedThemeId
                      ? "border-primary/60 bg-primary/10 text-primary hover:bg-primary/15"
                      : "text-on-surface-variant border-outline-variant/30 hover:text-white hover:bg-surface-variant/30"
                  } ${isDeveloping ? "opacity-50 cursor-not-allowed pointer-events-none" : ""}`}
                  onClick={() => {
                    setLocalSelectedThemeId(selectedThemeId);
                    setIsThemeModalOpen(true);
                  }}
                  disabled={isDeveloping}
                  aria-label="Select UI theme"
                >
                  <span className="material-symbols-outlined text-[16px] pointer-events-none">
                    palette
                  </span>
                  <span className="font-label-caps text-[11px] truncate pointer-events-none max-w-28">
                    {isLoadingThemes
                      ? "Loading…"
                      : selectedTheme
                        ? selectedTheme.name
                        : "Select Theme"}
                  </span>
                  {selectedThemeId ? (
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label="Clear theme"
                      className="material-symbols-outlined text-[14px] pointer-events-auto opacity-70 hover:opacity-100 transition-opacity"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedThemeId(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.stopPropagation();
                          setSelectedThemeId(null);
                        }
                      }}
                    >
                      close
                    </span>
                  ) : (
                    <span className="material-symbols-outlined text-[16px] pointer-events-none">
                      keyboard_arrow_down
                    </span>
                  )}
                </button>
              )}

              {/* Agent Selector (Multi-select Modal Trigger) */}
              <button
                className="flex items-center gap-2 px-3 py-1 text-on-surface-variant hover:text-white rounded-full border border-outline-variant/30 hover:bg-surface-variant/30 transition-colors cursor-pointer text-left select-none"
                type="button"
                onClick={() => {
                  setLocalSelectedAgents(selectedAgents);
                  setIsAgentModalOpen(true);
                }}
                disabled={isDeveloping}
              >
                <div
                  className="flex -space-x-1.5 pointer-events-none"
                  aria-hidden="true"
                >
                  {selectedAgents.map((agentId) => {
                    const agent = downloadedAgents.find(
                      (a) => a.id === agentId,
                    );
                    if (!agent) return null;
                    return (
                      <div
                        key={agent.id}
                        className="w-5 h-5 rounded-md bg-surface-container-highest flex items-center justify-center border border-background"
                      >
                        <span className="material-symbols-outlined text-[12px]">
                          {agent.icon}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <span className="font-label-caps text-[11px] pointer-events-none">
                  {selectedAgents.length === 0
                    ? "No Agents"
                    : selectedAgents.length === 1
                      ? downloadedAgents.find((a) => a.id === selectedAgents[0])
                          ?.name
                      : "Agents"}
                </span>
                {selectedAgents.length > 2 && (
                  <span className="font-label-caps text-[10px] bg-secondary-container/20 text-secondary px-1.5 rounded-full pointer-events-none">
                    +{selectedAgents.length - 2}
                  </span>
                )}
                <span className="material-symbols-outlined text-[16px] pointer-events-none">
                  keyboard_arrow_down
                </span>
              </button>
            </div>

            <div className="flex items-center gap-2 ml-auto">
              <button
                className="p-2 text-on-surface-variant hover:text-white rounded-full hover:bg-surface-variant/30 transition-colors"
                type="button"
                aria-label="Use microphone"
                disabled={isDeveloping}
              >
                <span className="material-symbols-outlined text-[20px]">
                  mic
                </span>
              </button>
              <button
                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                  !prompt.trim() ||
                  !selectedProjectId ||
                  selectedAgents.length === 0 ||
                  isDeveloping
                    ? "bg-on-surface-variant/20 text-on-surface-variant/40 cursor-not-allowed"
                    : "bg-primary text-on-primary hover:bg-opacity-90 active:scale-95"
                }`}
                disabled={
                  !prompt.trim() ||
                  !selectedProjectId ||
                  selectedAgents.length === 0 ||
                  isDeveloping
                }
                type="button"
                aria-label="Send prompt"
                onClick={handleSend}
              >
                <span className="material-symbols-outlined text-[20px]">
                  {isDeveloping ? "progress_activity" : "arrow_upward"}
                </span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {developError ? (
        <div className="text-error font-body-sm text-[13px] mt-3 px-2 flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">error</span>
          <span>{developError}</span>
        </div>
      ) : null}
      {developSuccess ? (
        <div className="text-tertiary-fixed-dim font-body-sm text-[13px] mt-3 px-2 flex items-center gap-2">
          <span className="material-symbols-outlined text-[16px]">
            check_circle
          </span>
          <span>{developSuccess}</span>
        </div>
      ) : null}

      {/* Project Selection Modal */}
      {isProjectModalOpen &&
        createPortal(
          <div className="fixed inset-0 z-1000 flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setIsProjectModalOpen(false)}
            />
            <div className="relative w-full max-w-2xl bg-[#171717] border border-[#262626] rounded-2xl shadow-2xl flex flex-col max-h-[80vh] animate-step-fade-in z-10 overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#262626] bg-[#141414]">
                <h3 className="text-base font-semibold text-white flex items-center gap-2 select-none">
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    folder
                  </span>
                  Select Project
                </h3>
                <button
                  type="button"
                  onClick={() => setIsProjectModalOpen(false)}
                  className="text-on-surface-variant hover:text-white p-1 hover:bg-[#262626] rounded transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    close
                  </span>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 grid grid-cols-2 gap-4 scrollbar-thin">
                {/* Create New Project Card */}
                <button
                  type="button"
                  onClick={() => setLocalSelectedProjectId("new-project")}
                  className={`flex flex-col items-center justify-center p-5 rounded-xl border text-center gap-3 transition-all cursor-pointer select-none ${
                    localSelectedProjectId === "new-project"
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-[#262626] bg-[#1a1a1a]/50 hover:bg-[#202022] hover:border-[#333333] text-on-surface-variant hover:text-white"
                  }`}
                >
                  <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[24px]">
                      add_circle
                    </span>
                  </div>
                  <div>
                    <h4 className="text-[13px] font-semibold text-white">
                      Create New Project
                    </h4>
                    <p className="text-[11px] text-on-surface-variant mt-1">
                      Start a fresh project environment
                    </p>
                  </div>
                </button>

                {/* Projects cards */}
                {projects.map((project) => {
                  const isSelected = localSelectedProjectId === project.id;
                  return (
                    <button
                      key={project.id}
                      type="button"
                      onClick={() => setLocalSelectedProjectId(project.id)}
                      className={`flex items-start p-5 rounded-xl border text-left gap-4 transition-all cursor-pointer select-none ${
                        isSelected
                          ? "border-primary bg-primary/5 text-white"
                          : "border-[#262626] bg-[#1a1a1a]/50 hover:bg-[#202022] hover:border-[#333333] text-on-surface-variant hover:text-white"
                      }`}
                    >
                      <div
                        className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${isSelected ? "bg-primary/20 text-primary" : "bg-[#262626] text-on-surface-variant"}`}
                      >
                        <span className="material-symbols-outlined text-[20px]">
                          folder
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="text-[13px] font-semibold truncate text-white">
                          {project.name}
                        </h4>
                        <p className="text-[10px] text-on-surface-variant mt-1">
                          ID: {project.id.slice(0, 8)}...
                        </p>
                      </div>
                      {isSelected && (
                        <span className="material-symbols-outlined text-primary text-[18px] shrink-0">
                          check_circle
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#262626] bg-[#141414] shrink-0">
                <button
                  type="button"
                  onClick={() => setIsProjectModalOpen(false)}
                  className="px-4 py-2 text-[12px] text-on-surface-variant hover:text-white bg-transparent border border-outline-variant hover:bg-[#262626] rounded-lg transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedProjectId(localSelectedProjectId);
                    setIsProjectModalOpen(false);
                  }}
                  className="px-5 py-2 text-[12px] font-semibold text-on-primary bg-primary hover:bg-primary/90 rounded-lg transition-colors cursor-pointer"
                >
                  Confirm
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* Agent Selection Modal */}
      {isAgentModalOpen &&
        createPortal(
          <div className="fixed inset-0 z-1000 flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setIsAgentModalOpen(false)}
            />
            <div className="relative w-full max-w-2xl bg-[#171717] border border-[#262626] rounded-2xl shadow-2xl flex flex-col max-h-[80vh] animate-step-fade-in z-10 overflow-hidden">
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#262626] bg-[#141414]">
                <h3 className="text-base font-semibold text-white flex items-center gap-2 select-none">
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    smart_toy
                  </span>
                  Select Agents
                </h3>
                <button
                  type="button"
                  onClick={() => setIsAgentModalOpen(false)}
                  className="text-on-surface-variant hover:text-white p-1 hover:bg-[#262626] rounded transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    close
                  </span>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 grid grid-cols-2 gap-4 scrollbar-thin">
                {downloadedAgents.length === 0 ? (
                  <div className="col-span-2 text-center py-8 text-on-surface-variant text-[12px] italic select-none">
                    No agents downloaded. Visit the Marketplace to download
                    agents.
                  </div>
                ) : (
                  downloadedAgents.map((agent) => {
                    const isSelected = localSelectedAgents.includes(agent.id);
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => {
                          if (isSelected) {
                            setLocalSelectedAgents(
                              localSelectedAgents.filter(
                                (id) => id !== agent.id,
                              ),
                            );
                          } else {
                            setLocalSelectedAgents([
                              ...localSelectedAgents,
                              agent.id,
                            ]);
                          }
                        }}
                        className={`flex items-center p-4 rounded-xl border text-left gap-4 transition-all cursor-pointer select-none ${
                          isSelected
                            ? "border-primary bg-primary/5 text-white"
                            : "border-[#262626] bg-[#1a1a1a]/50 hover:bg-[#202022] hover:border-[#333333] text-on-surface-variant hover:text-white"
                        }`}
                      >
                        <span className="material-symbols-outlined text-[20px] text-primary shrink-0">
                          {isSelected ? "check_box" : "check_box_outline_blank"}
                        </span>
                        <div
                          className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${isSelected ? "bg-primary/20 text-primary" : "bg-[#262626] text-on-surface-variant"}`}
                        >
                          <span className="material-symbols-outlined text-[20px]">
                            {agent.icon}
                          </span>
                        </div>
                        <div className="min-w-0 flex-1">
                          <h4 className="text-[13px] font-semibold truncate text-white">
                            {agent.name}
                          </h4>
                          <p className="text-[10px] text-on-surface-variant mt-0.5 truncate">
                            {agent.description || "Assistant Agent"}
                          </p>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#262626] bg-[#141414] shrink-0">
                <button
                  type="button"
                  onClick={() => setIsAgentModalOpen(false)}
                  className="px-4 py-2 text-[12px] text-on-surface-variant hover:text-white bg-transparent border border-outline-variant hover:bg-[#262626] rounded-lg transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedAgents(localSelectedAgents);
                    setIsAgentModalOpen(false);
                  }}
                  className="px-5 py-2 text-[12px] font-semibold text-on-primary bg-primary hover:bg-primary/90 rounded-lg transition-colors cursor-pointer"
                >
                  Apply
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* ── Theme Selection Modal ─────────────────────────────────────────── */}
      {isThemeModalOpen &&
        createPortal(
          <div className="fixed inset-0 z-1000 flex items-center justify-center p-4">
            <div
              className="absolute inset-0 bg-black/60 backdrop-blur-sm"
              onClick={() => setIsThemeModalOpen(false)}
            />
            <div className="relative w-full max-w-2xl bg-[#171717] border border-[#262626] rounded-2xl shadow-2xl flex flex-col max-h-[80vh] animate-step-fade-in z-10 overflow-hidden">
              {/* Modal Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-[#262626] bg-[#141414]">
                <h3 className="text-base font-semibold text-white flex items-center gap-2 select-none">
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    palette
                  </span>
                  Select UI Theme
                </h3>
                <button
                  type="button"
                  onClick={() => setIsThemeModalOpen(false)}
                  className="text-on-surface-variant hover:text-white p-1 hover:bg-[#262626] rounded transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-[18px]">
                    close
                  </span>
                </button>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
                {/* No-theme card */}
                <div className="grid grid-cols-2 gap-4">
                  <button
                    type="button"
                    onClick={() => setLocalSelectedThemeId(null)}
                    className={`flex flex-col items-center justify-center p-5 rounded-xl border text-center gap-3 transition-all cursor-pointer select-none ${
                      localSelectedThemeId === null
                        ? "border-primary bg-primary/5 text-primary"
                        : "border-[#262626] bg-[#1a1a1a]/50 hover:bg-[#202022] hover:border-[#333333] text-on-surface-variant hover:text-white"
                    }`}
                  >
                    <div className="w-12 h-12 rounded-full bg-surface-container-highest flex items-center justify-center text-on-surface-variant">
                      <span className="material-symbols-outlined text-[24px]">
                        format_paint
                      </span>
                    </div>
                    <div>
                      <h4 className="text-[13px] font-semibold text-white">
                        Default (No Theme)
                      </h4>
                      <p className="text-[11px] text-on-surface-variant mt-1">
                        Use the agent's default UI style
                      </p>
                    </div>
                    {localSelectedThemeId === null && (
                      <span className="material-symbols-outlined text-primary text-[18px]">
                        check_circle
                      </span>
                    )}
                  </button>

                  {/* Theme cards — dynamically loaded from backend */}
                  {isLoadingThemes ? (
                    <div className="col-span-1 flex items-center justify-center py-8 text-on-surface-variant text-[12px] italic select-none">
                      <span className="material-symbols-outlined text-[18px] mr-2 animate-spin">
                        progress_activity
                      </span>
                      Loading themes…
                    </div>
                  ) : themes.length === 0 ? (
                    <div className="col-span-1 flex items-center justify-center py-8 text-on-surface-variant text-[12px] italic select-none">
                      No themes found. Add .md files to the server/themes/
                      directory.
                    </div>
                  ) : (
                    themes.map((theme) => {
                      const isSelected = localSelectedThemeId === theme.id;
                      return (
                        <button
                          key={theme.id}
                          type="button"
                          onClick={() => setLocalSelectedThemeId(theme.id)}
                          className={`flex items-start p-5 rounded-xl border text-left gap-4 transition-all cursor-pointer select-none ${
                            isSelected
                              ? "border-primary bg-primary/5 text-white"
                              : "border-[#262626] bg-[#1a1a1a]/50 hover:bg-[#202022] hover:border-[#333333] text-on-surface-variant hover:text-white"
                          }`}
                        >
                          <div
                            className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${
                              isSelected
                                ? "bg-primary/20 text-primary"
                                : "bg-[#262626] text-on-surface-variant"
                            }`}
                          >
                            <span className="material-symbols-outlined text-[20px]">
                              style
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <h4 className="text-[13px] font-semibold truncate text-white">
                              {theme.name}
                            </h4>
                            {theme.description && (
                              <p className="text-[10px] text-on-surface-variant mt-0.5 line-clamp-2">
                                {theme.description}
                              </p>
                            )}
                            <p className="text-[9px] text-on-surface-variant/50 mt-1 font-mono">
                              {theme.filename}
                            </p>
                          </div>
                          {isSelected && (
                            <span className="material-symbols-outlined text-primary text-[18px] shrink-0">
                              check_circle
                            </span>
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Modal Footer */}
              <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-[#262626] bg-[#141414] shrink-0">
                <p className="text-[11px] text-on-surface-variant select-none">
                  {localSelectedThemeId
                    ? `Selected: ${themes.find((t) => t.id === localSelectedThemeId)?.name ?? localSelectedThemeId}`
                    : "No theme selected — default UI style will be used"}
                </p>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setIsThemeModalOpen(false)}
                    className="px-4 py-2 text-[12px] text-on-surface-variant hover:text-white bg-transparent border border-outline-variant hover:bg-[#262626] rounded-lg transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedThemeId(localSelectedThemeId);
                      setIsThemeModalOpen(false);
                    }}
                    className="px-5 py-2 text-[12px] font-semibold text-on-primary bg-primary hover:bg-primary/90 rounded-lg transition-colors cursor-pointer"
                  >
                    Apply
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </section>
  );
}

export default PromptComposer;

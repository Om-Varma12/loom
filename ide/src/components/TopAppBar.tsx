import { useClerk, useUser } from "@clerk/react";
import { resetAuthCaches } from "../lib/authFetch";

type TopAppBarProps = {
  projectName?: string;
  prompt?: string;
  isSessionActive?: boolean;
  activeOverlayPanel: "explorer" | "agents" | "projects" | null;
  setActiveOverlayPanel: (
    panel: "explorer" | "agents" | "projects" | null,
  ) => void;
  isProjectSelected: boolean;
};

function TopAppBar({
  projectName,
  prompt,
  isSessionActive,
  activeOverlayPanel,
  setActiveOverlayPanel,
  isProjectSelected,
}: TopAppBarProps) {
  const { signOut } = useClerk();
  const { user } = useUser();
  const userLabel =
    user?.firstName ||
    user?.primaryEmailAddress?.emailAddress ||
    "Account";

  const handleSignOut = () => {
    resetAuthCaches();
    void signOut({ redirectUrl: "/sign-in" });
  };

  const accountButton = (
    <button
      aria-label="Sign out"
      className="p-2 text-on-surface-variant hover:bg-surface-variant/20 rounded-xl transition-all active:scale-95 flex items-center justify-center"
      onClick={handleSignOut}
      title={`Sign out ${userLabel}`}
      type="button"
    >
      <span className="material-symbols-outlined text-[18px]">logout</span>
    </button>
  );

  if (isSessionActive) {
    return (
      <header className="h-14 flex items-center justify-between px-6 border-b border-[#262626] bg-[#0A0A0A] shrink-0 w-full z-10">
        <div className="flex items-center gap-2 font-code-md text-code-md text-on-surface-variant text-[14px]">
          <span className="material-symbols-outlined text-[18px]">folder</span>
          <span className="font-semibold text-primary">
            {projectName || "project"}
          </span>
          <span className="material-symbols-outlined text-[16px] mx-1 opacity-50">
            chevron_right
          </span>
          <span className="truncate max-w-70 md:max-w-112.5 opacity-75">
            {prompt || "Agent execution"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Commit indicator */}
          <div className="flex items-center gap-2 px-3 py-1 bg-[#171717] border border-[#262626] rounded-full font-code-md text-[12px] text-on-surface-variant mr-2">
            <span className="material-symbols-outlined text-[14px]">
              commit
            </span>
            <span>main</span>
          </div>

          <button
            className="p-1.5 text-on-surface-variant hover:text-white rounded hover:bg-[#262626] transition-colors"
            type="button"
            aria-label="Information"
          >
            <span className="material-symbols-outlined text-[18px]">info</span>
          </button>

          {/* grid_view button */}
          <button
            className="p-2 text-on-surface-variant hover:bg-surface-variant/20 rounded-xl transition-all active:scale-95 top-bar-toggle-btn cursor-pointer flex items-center justify-center"
            type="button"
            onClick={() => {
              if (activeOverlayPanel === "agents") {
                setActiveOverlayPanel(null);
              } else {
                setActiveOverlayPanel("agents");
              }
            }}
            aria-label="Grid View"
            title="Grid View"
          >
            <span
              className={`material-symbols-outlined text-[18px] ${activeOverlayPanel === "agents" ? "text-primary font-semibold" : ""}`}
            >
              grid_view
            </span>
          </button>

          {/* view_sidebar button */}
          <button
            className={`p-2 rounded-xl transition-all active:scale-95 top-bar-toggle-btn flex items-center justify-center ${
              isProjectSelected
                ? "text-on-surface-variant hover:bg-surface-variant/20 cursor-pointer"
                : "text-on-surface-variant/30 cursor-not-allowed opacity-40"
            }`}
            type="button"
            onClick={() => {
              if (!isProjectSelected) return;
              if (activeOverlayPanel === "explorer") {
                setActiveOverlayPanel(null);
              } else {
                setActiveOverlayPanel("explorer");
              }
            }}
            disabled={!isProjectSelected}
            aria-label="Sidebar Right"
            title="Workspace Explorer"
          >
            <span
              className={`material-symbols-outlined text-[18px] ${activeOverlayPanel === "explorer" ? "text-primary font-semibold" : ""}`}
            >
              view_sidebar
            </span>
          </button>

          {accountButton}
        </div>
      </header>
    );
  }

  return (
    <header className="flex justify-end items-center px-6 py-4 w-full bg-transparent absolute top-0 left-0 z-10">
      <div className="flex items-center gap-4">
        {/* grid_view button */}
        <button
          className="p-2 text-on-surface-variant hover:bg-surface-variant/20 rounded-xl transition-all active:scale-95 top-bar-toggle-btn cursor-pointer flex items-center justify-center"
          type="button"
          onClick={() => {
            if (activeOverlayPanel === "agents") {
              setActiveOverlayPanel(null);
            } else {
              setActiveOverlayPanel("agents");
            }
          }}
          aria-label="Grid View"
          title="Grid View"
        >
          <span
            className={`material-symbols-outlined text-[20px] ${activeOverlayPanel === "agents" ? "text-primary font-semibold" : ""}`}
          >
            grid_view
          </span>
        </button>

        {/* view_sidebar button */}
        <button
          className={`p-2 rounded-xl transition-all active:scale-95 top-bar-toggle-btn flex items-center justify-center ${
            isProjectSelected
              ? "text-on-surface-variant hover:bg-surface-variant/20 cursor-pointer"
              : "text-on-surface-variant/30 cursor-not-allowed opacity-40"
          }`}
          type="button"
          onClick={() => {
            if (!isProjectSelected) return;
            if (activeOverlayPanel === "explorer") {
              setActiveOverlayPanel(null);
            } else {
              setActiveOverlayPanel("explorer");
            }
          }}
          disabled={!isProjectSelected}
          aria-label="Sidebar Right"
          title="Workspace Explorer"
        >
          <span
            className={`material-symbols-outlined text-[20px] ${activeOverlayPanel === "explorer" ? "text-primary font-semibold" : ""}`}
          >
            view_sidebar
          </span>
        </button>

        {accountButton}
      </div>
    </header>
  );
}

export default TopAppBar;

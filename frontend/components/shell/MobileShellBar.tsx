"use client";

import { Search } from "lucide-react";
import type { ShellTab } from "@/hooks/useShellNavigation";

type Props = {
  clientName?: string;
  activeTab: ShellTab;
  onOpenCommand: () => void;
};

export default function MobileShellBar({ clientName, activeTab, onOpenCommand }: Props) {
  const title =
    clientName && activeTab !== "portfolio" && activeTab !== "settings"
      ? clientName
      : activeTab === "settings"
        ? "Settings"
        : "Mission Control";

  const stage =
    activeTab !== "portfolio" && activeTab !== "settings" && activeTab !== "charts"
      ? activeTab.charAt(0).toUpperCase() + activeTab.slice(1)
      : null;

  return (
    <div className="bg-[color:var(--surface-light)]/92 sticky top-0 z-30 flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5 backdrop-blur-md sm:hidden">
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-sm font-semibold text-ink">{title}</span>
        {stage && <span className="text-muted truncate text-[11px] font-medium">{stage}</span>}
      </div>
      <button
        type="button"
        onClick={onOpenCommand}
        className="icon-btn"
        aria-label="Open command palette"
      >
        <Search size={16} strokeWidth={1.75} />
      </button>
    </div>
  );
}

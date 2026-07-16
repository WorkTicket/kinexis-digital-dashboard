"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LayoutGrid,
  Cog,
  Search,
  ListChecks,
  Target,
  ClipboardCheck,
  FileText,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Zap,
  Wrench,
  Link2,
} from "lucide-react";
import { Client } from "@/lib/api";

export type CommandAction = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  icon?: React.ReactNode;
  run: () => void;
};

type Props = {
  open: boolean;
  onClose: () => void;
  clients: Client[];
  onSelectClient: (id: number) => void;
  onNavigate: (tab: string) => void;
  hasClient: boolean;
  clientName?: string;
  onSync?: () => void;
  onGeneratePlan?: () => void;
  onExportReport?: () => void;
  onAssignTopFix?: () => void;
  onStartFix?: () => void;
  onOpenTopLever?: () => void;
  onGenerateReport?: () => void;
  onCopyDeepLink?: () => void;
};

const CLIENT_TABS = [
  { id: "detect", label: "Detect · Situation", icon: <Search size={14} /> },
  { id: "levers", label: "Detect · Problems", icon: <Zap size={14} /> },
  { id: "prescribe", label: "Prescribe · Fix queue", icon: <ListChecks size={14} /> },
  { id: "execute", label: "Execute", icon: <ClipboardCheck size={14} /> },
  { id: "prove", label: "Prove", icon: <Target size={14} /> },
  { id: "report", label: "Report", icon: <FileText size={14} /> },
];

export default function CommandPalette({
  open,
  onClose,
  clients,
  onSelectClient,
  onNavigate,
  hasClient,
  clientName,
  onSync,
  onGeneratePlan,
  onExportReport,
  onAssignTopFix,
  onStartFix,
  onOpenTopLever,
  onGenerateReport,
  onCopyDeepLink,
}: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const actions = useMemo<CommandAction[]>(() => {
    const q = query.trim().toLowerCase();
    const items: CommandAction[] = [
      {
        id: "nav-portfolio",
        label: "Portfolio",
        hint: "All clients",
        group: "Navigate",
        icon: <LayoutGrid size={14} />,
        run: () => onNavigate("portfolio"),
      },
      {
        id: "nav-settings",
        label: "Settings",
        hint: "AI & API keys",
        group: "Navigate",
        icon: <Cog size={14} />,
        run: () => onNavigate("settings"),
      },
    ];

    if (hasClient) {
      for (const tab of CLIENT_TABS) {
        items.push({
          id: `tab-${tab.id}`,
          label: tab.label,
          hint: "Current client",
          group: "Pages",
          icon: tab.icon,
          run: () => onNavigate(tab.id),
        });
      }
      items.push({
        id: "nav-rankings",
        label: "Google rankings",
        hint: "Detect · keyword positions",
        group: "Pages",
        icon: <TrendingUp size={14} />,
        run: () => onNavigate("rankings"),
      });
      if (onOpenTopLever) {
        items.push({
          id: "action-top-lever",
          label: clientName ? `Open top lever for ${clientName}` : "Open top lever",
          hint: "Detect · Problems",
          group: "Actions",
          icon: <Zap size={14} />,
          run: () => onOpenTopLever(),
        });
      }
      if (onStartFix) {
        items.push({
          id: "action-start-fix",
          label: clientName ? `Open Fix queue for ${clientName}` : "Open Fix queue",
          hint: "Prescribe · Assign here",
          group: "Actions",
          icon: <Wrench size={14} />,
          run: () => onStartFix(),
        });
      }
      if (onSync) {
        items.push({
          id: "action-sync",
          label: "Sync data",
          hint: "Refresh connectors",
          group: "Actions",
          icon: <RefreshCw size={14} />,
          run: () => onSync(),
        });
      }
      if (onGeneratePlan) {
        items.push({
          id: "action-plan",
          label: "Generate AI plan",
          hint: "Prescribe",
          group: "Actions",
          icon: <Sparkles size={14} />,
          run: () => onGeneratePlan(),
        });
      }
      if (onGenerateReport || onExportReport) {
        items.push({
          id: "action-report-generate",
          label: clientName ? `Generate month report for ${clientName}` : "Generate month report",
          hint: "Report library · builds & saves",
          group: "Actions",
          icon: <FileText size={14} />,
          run: () => (onGenerateReport || onExportReport)?.(),
        });
      }
      if (onExportReport) {
        items.push({
          id: "action-report",
          label: "Open report library",
          hint: "Saved months · PDF export",
          group: "Actions",
          icon: <FileText size={14} />,
          run: () => onExportReport(),
        });
      }
      if (onAssignTopFix) {
        items.push({
          id: "action-assign-fix",
          label: "Assign top fix to Cursor",
          hint: "Create task from highest-ranked insight",
          group: "Actions",
          icon: <ClipboardCheck size={14} />,
          run: () => onAssignTopFix(),
        });
      }
      if (onCopyDeepLink) {
        items.push({
          id: "action-copy-link",
          label: "Copy deep link",
          hint: "Client + tab URL",
          group: "Actions",
          icon: <Link2 size={14} />,
          run: () => onCopyDeepLink(),
        });
      }
    }

    for (const c of clients) {
      items.push({
        id: `client-${c.id}`,
        label: c.name,
        hint: c.industry || "Client",
        group: "Clients",
        run: () => onSelectClient(c.id),
      });
      // Only surface per-client Fix queue when searching — avoids N noise actions.
      if (q && c.name.toLowerCase().includes(q)) {
        items.push({
          id: `client-fix-${c.id}`,
          label: `Open Fix queue for ${c.name}`,
          hint: "Jump + Prescribe · Assign here",
          group: "Actions",
          icon: <Wrench size={14} />,
          run: () => {
            onSelectClient(c.id);
            onNavigate("prescribe");
          },
        });
      }
    }

    if (!q) return items;
    return items.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        (a.hint || "").toLowerCase().includes(q) ||
        a.group.toLowerCase().includes(q)
    );
  }, [
    query,
    clients,
    hasClient,
    clientName,
    onNavigate,
    onSelectClient,
    onSync,
    onGeneratePlan,
    onExportReport,
    onAssignTopFix,
    onStartFix,
    onOpenTopLever,
    onGenerateReport,
    onCopyDeepLink,
  ]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, Math.max(0, actions.length - 1)));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const item = actions[active];
        if (item) {
          try {
            item.run();
          } catch (err) {
            console.error("Command palette action failed:", err);
          }
          onClose();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, actions, active, onClose]);

  if (!open) return null;

  const groups = Array.from(new Set(actions.map((a) => a.group)));

  return (
    <div
      className="modal-backdrop animate-fade-in z-[80]"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="panel-elevated animate-scale-in w-full max-w-xl overflow-hidden shadow-dropdown"
      >
        <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] bg-surface-lighter/40 px-4 py-3.5">
          <Search size={16} className="text-muted shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages, actions, or clients…"
            className="placeholder:text-muted flex-1 bg-transparent text-[15px] font-medium text-ink outline-none placeholder:font-normal focus-visible:ring-0"
          />
          <kbd className="kbd">esc</kbd>
        </div>
        <div className="max-h-[360px] overflow-y-auto py-2">
          {actions.length === 0 && (
            <p className="text-muted px-4 py-6 text-center text-sm">No matches</p>
          )}
          {groups.map((group) => {
            const groupItems = actions.filter((a) => a.group === group);
            return (
              <div key={group} className="mb-2">
                <p className="text-label px-4 py-1">{group}</p>
                <ul>
                  {groupItems.map((item) => {
                    const flatIndex = actions.indexOf(item);
                    const isActive = flatIndex === active;
                    return (
                      <li key={item.id}>
                        <button
                          type="button"
                          className={`motion-micro flex w-full items-center gap-3 px-4 py-2 text-left text-sm ${
                            isActive
                              ? "bg-[color:var(--active-fill)] text-ink"
                              : "text-ink-secondary hover:bg-[var(--hover-fill)]"
                          }`}
                          onMouseEnter={() => setActive(flatIndex)}
                          onClick={() => {
                            item.run();
                            onClose();
                          }}
                        >
                          <span className="text-muted flex w-4 shrink-0 justify-center">
                            {item.icon}
                          </span>
                          <span className="flex-1 truncate font-medium">{item.label}</span>
                          {item.hint && (
                            <span className="text-muted max-w-[40%] truncate text-[11px]">
                              {item.hint}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
        <div className="text-muted flex flex-wrap gap-x-3 gap-y-1 border-t border-[color:var(--border-subtle)] px-4 py-2 text-xs">
          <span>
            <kbd className="font-mono-data">⌘/Ctrl K</kbd> palette
          </span>
          <span>
            <kbd className="font-mono-data">1–5</kbd> Detect→Report
          </span>
          <span>
            <kbd className="font-mono-data">⌘/Ctrl ,</kbd> Settings
          </span>
          <span>
            <kbd className="font-mono-data">Esc</kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}

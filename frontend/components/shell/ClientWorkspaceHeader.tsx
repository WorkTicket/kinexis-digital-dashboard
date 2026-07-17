"use client";

import { Settings2 } from "lucide-react";
import SyncStatusStrip from "@/components/SyncStatusStrip";
import ClientProfileEditor from "@/components/ClientProfileEditor";
import DatasourcesPanel from "@/components/DatasourcesPanel";
import StageModeRail from "@/components/shell/StageModeRail";
import { SelectDropdown } from "@/components/Dropdown";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import type { Client, DataSource } from "@/lib/api";
import type { ShellTab } from "@/hooks/useShellNavigation";

const INDUSTRY_OPTIONS = [
  { value: "", label: "Select industry…" },
  { value: "Technology", label: "Technology" },
  { value: "E-commerce & Retail", label: "E-commerce & Retail" },
  { value: "Healthcare", label: "Healthcare" },
  { value: "Finance & Insurance", label: "Finance & Insurance" },
  { value: "Real Estate", label: "Real Estate" },
  { value: "Education", label: "Education" },
  { value: "Hospitality & Travel", label: "Hospitality & Travel" },
  { value: "Legal", label: "Legal" },
  { value: "Manufacturing", label: "Manufacturing" },
  { value: "Media & Entertainment", label: "Media & Entertainment" },
  { value: "Professional Services", label: "Professional Services" },
  { value: "Other", label: "Other" },
];

type ProfileSection = "profile" | "datasources";

type Props = {
  client: Client | null;
  selectedClientId: number;
  loading: boolean;
  hasLoadedOnce: boolean;
  openIssues: number;
  datasources: DataSource[];
  syncing: boolean;
  lastSyncResults: Record<string, string> | null;
  showIndustry: boolean;
  profilePanelSection: ProfileSection;
  activeTab: ShellTab;
  openTasks: number;
  doneTasks: number;
  unprovenTasks: number;
  reportStatus: string;
  onSync: () => void;
  onToggleIndustry: () => void;
  onProfileSectionChange: (section: ProfileSection) => void;
  onIndustryChange: (industry: string) => void;
  onProfileSave: (data: {
    profile: Record<string, unknown>;
    owner: string;
    priority: number;
  }) => void;
  onDatasourcesChanged: (sources: DataSource[]) => void;
  onTabChange: (tab: ShellTab) => void;
};

export default function ClientWorkspaceHeader({
  client,
  selectedClientId,
  loading,
  hasLoadedOnce,
  openIssues,
  datasources,
  syncing,
  lastSyncResults,
  showIndustry,
  profilePanelSection,
  activeTab,
  openTasks,
  doneTasks,
  unprovenTasks,
  reportStatus,
  onSync,
  onToggleIndustry,
  onProfileSectionChange,
  onIndustryChange,
  onProfileSave,
  onDatasourcesChanged,
  onTabChange,
}: Props) {
  const riskTone = openIssues >= 5 ? "danger" : openIssues > 0 ? "warning" : ("success" as const);

  return (
    <header className="war-room-context animate-fade-up mb-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <h1 className="text-title truncate text-[22px] sm:text-[26px]">
              {client?.name || "…"}
            </h1>
            {loading && hasLoadedOnce && (
              <span className="text-muted inline-flex items-center gap-2 text-[11px] font-medium">
                <span
                  className="h-3 w-3 animate-spin rounded-full border-2 border-[color:var(--border-default)] border-t-kinexis-focus"
                  aria-hidden
                />
                Syncing
              </span>
            )}
            {openIssues > 0 ? (
              <Badge tone={riskTone}>{openIssues} open fixes</Badge>
            ) : (
              <Badge tone="success">Clear</Badge>
            )}
          </div>
          <SyncStatusStrip
            datasources={datasources}
            syncing={syncing}
            lastSyncResults={lastSyncResults}
            onSync={onSync}
            compact
            showSources
          />
        </div>
        <Button variant="ghost" size="sm" onClick={onToggleIndustry}>
          <Settings2 size={14} />
          {showIndustry ? "Hide" : "Profile & data"}
        </Button>
      </div>

      {showIndustry && (
        <div
          className="animate-fade-up mt-4 max-w-2xl space-y-4 border border-[color:var(--border-subtle)] bg-[color:var(--surface)] p-4 sm:p-4"
          style={{ borderRadius: "var(--radius-lg)" }}
        >
          <div className="flex flex-wrap gap-1">
            {(
              [
                ["profile", "Business context"],
                ["datasources", "Data sources"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => onProfileSectionChange(id)}
                className={`motion-micro px-3 py-2 text-[12px] font-medium ${
                  profilePanelSection === id
                    ? "bg-kinexis-focus/10 text-kinexis-focus"
                    : "text-muted hover:text-ink-secondary"
                }`}
                style={{ borderRadius: "var(--radius-md)" }}
              >
                {label}
              </button>
            ))}
          </div>
          {profilePanelSection === "profile" && (
            <>
              <div>
                <p className="text-label mb-2">Industry</p>
                <SelectDropdown
                  value={client?.industry || ""}
                  options={INDUSTRY_OPTIONS}
                  onChange={(v) => {
                    void onIndustryChange(v);
                  }}
                  placeholder="Industry…"
                />
              </div>
              <ClientProfileEditor
                profileJson={client?.profile_json}
                owner={client?.owner}
                priority={client?.priority}
                onSave={(p) => void onProfileSave(p)}
              />
            </>
          )}
          {profilePanelSection === "datasources" && (
            <DatasourcesPanel
              clientId={selectedClientId}
              datasources={datasources}
              onChanged={onDatasourcesChanged}
            />
          )}
        </div>
      )}

      <div className="mt-4">
        <StageModeRail
          activeTab={activeTab}
          onNavigate={(tab) => onTabChange(tab)}
          counts={{
            openIssues,
            openTasks,
            doneTasks,
            unprovenTasks,
            reportStatus,
          }}
        />
      </div>
    </header>
  );
}

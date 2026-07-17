"use client";

import { useState } from "react";
import { Archive, ArchiveRestore, Download, GitCompare, LayoutGrid, RefreshCw } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Button } from "@/components/ui/Button";
import { Stat } from "@/components/ui/Stat";
import { Panel } from "@/components/ui/Panel";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { usePortfolioData } from "@/hooks/usePortfolioData";
import { BookCapacity } from "@/components/portfolio/BookCapacity";
import { TodayQueue } from "@/components/portfolio/TodayQueue";
import { PortfolioClientTable } from "@/components/portfolio/PortfolioClientTable";
import { PortfolioWinsPanel } from "@/components/portfolio/PortfolioWinsPanel";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";

type OpenHint = {
  open_insights?: number;
  open_tasks?: number;
  risk?: string;
  tab?: string;
  insight_id?: number;
  task_id?: number;
};

type Props = {
  onSelectClient: (id: number) => void;
  onOpenClient?: (clientId: number, hint?: OpenHint) => void;
  onOpenClientTab?: (clientId: number, tab: string) => void;
  onCompare?: () => void;
};

export default function PortfolioView({
  onSelectClient,
  onOpenClient,
  onOpenClientTab,
  onCompare,
}: Props) {
  const data = usePortfolioData();
  const { success: toastSuccess, error: toastError } = useToast();
  const [startingId, setStartingId] = useState<number | null>(null);
  const {
    rows,
    wins,
    todayItems,
    aiValue,
    loading,
    loadError,
    sortKey,
    setSortKey,
    ownerFilter,
    setOwnerFilter,
    priorityOnly,
    setPriorityOnly,
    reportReadyOnly,
    setReportReadyOnly,
    myBookName,
    setMyBook,
    assigneePresets,
    syncingAll,
    syncNote,
    tableSearch,
    setTableSearch,
    bulkMode,
    bulkSelected,
    bulkBusy,
    loadPortfolio,
    handleSyncAll,
    portfolioStats,
    capacity,
    ownerOptions,
    sorted,
    clearFilters,
    toggleBulkSelect,
    toggleAllVisible,
    bulkSync,
    bulkArchive,
    bulkUnarchive,
    hasActiveFilters,
    exportCSV,
    toggleBulkMode,
  } = data;

  const { critical, watch, healthy, noData, overdue, atRisk, revenue30, leads30 } = portfolioStats;

  const openClient = (clientId: number, hint?: OpenHint) => {
    if (onOpenClient) onOpenClient(clientId, hint);
    else if (hint?.tab && onOpenClientTab) onOpenClientTab(clientId, hint.tab);
    else onSelectClient(clientId);
  };

  const startTopAction = async (clientId: number) => {
    setStartingId(clientId);
    try {
      const res = await api.actions.startTopAction(clientId);
      toastSuccess(`Started: ${res.title} — baseline captured`);
      // Desktop-only handoff — never toast IDE chrome at web users
      if (res.open_cursor && window.kinexis?.openCursorForTask) {
        try {
          await window.kinexis.openCursorForTask(res.task_id, {
            title: res.title,
            message: res.detail || undefined,
            notes: res.result_notes || undefined,
            targetQuery: res.target_query || undefined,
            targetUrl: res.target_url || undefined,
            playbookPattern: res.playbook_pattern || undefined,
          });
        } catch {
          /* silent — web and failed handoffs stay in-app */
        }
      }
      openClient(clientId, {
        tab: "execute",
        task_id: res.task_id,
        insight_id: res.insight_id ?? undefined,
      });
      void loadPortfolio();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to start top action");
    } finally {
      setStartingId(null);
    }
  };

  const missingCore = rows.filter((r) => {
    // Soft mandate signal from portfolio row if present; else skip
    const sc = r.success_contract;
    return !sc?.configured;
  }).length;

  if (loading) {
    return (
      <div className="workspace-content">
        <LoadingState variant="table" rows={8} />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="animate-fade-up mx-auto max-w-lg p-6 sm:p-6">
        <ErrorState
          title="Portfolio unavailable"
          description={loadError}
          onRetry={() => void loadPortfolio()}
        />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="animate-fade-up flex h-full min-h-[60vh] items-center justify-center px-6">
        <EmptyState
          className="w-full max-w-md !border-0 !bg-transparent"
          icon={<LayoutGrid size={20} strokeWidth={1.5} />}
          title="No clients yet"
          description="Open the client switcher in the command bar to add your first account."
          action={
            <ol className="w-full max-w-sm space-y-2.5 text-left text-[13px] text-ink-secondary">
              {[
                "Add a client from the switcher (or sync Cloudflare zones)",
                "Sync data sources for that client",
                "Open Detect and review the next move",
                "Assign and complete a fix (Prescribe → Execute)",
                "Generate the first monthly success report",
              ].map((step, i) => (
                <li key={step} className="flex items-start gap-3">
                  <span
                    className="font-mono-data text-muted mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center border border-[color:var(--border-default)] text-[11px] font-medium"
                    style={{ borderRadius: "var(--radius-sm)" }}
                  >
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{step}</span>
                </li>
              ))}
            </ol>
          }
        />
      </div>
    );
  }

  return (
    <div className="workspace-content animate-fade-up">
      <Panel padding="sm" className="mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Stat
            label="Critical"
            value={critical}
            tone={critical > 0 ? "danger" : "default"}
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[1.15rem]"
          />
          <Stat
            label="At risk"
            value={atRisk}
            tone={atRisk > 0 ? "warning" : "default"}
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[1.15rem]"
          />
          {overdue > 0 && (
            <Stat
              label="Overdue"
              value={overdue}
              tone="danger"
              className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[1.15rem]"
            />
          )}
          {(revenue30 > 0 || leads30 > 0) && (
            <Stat
              label={revenue30 > 0 ? "Revenue 30d" : "Leads 30d"}
              value={revenue30 > 0 ? `$${Math.round(revenue30 / 1000)}k` : leads30}
              tone="success"
              className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[1.15rem]"
            />
          )}
          {syncNote && <span className="text-muted text-[12px]">{syncNote}</span>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={exportCSV} title="Export CSV">
            <Download size={13} strokeWidth={1.75} />
            Export
          </Button>
          {onCompare && (
            <Button variant="ghost" size="sm" onClick={onCompare} title="Compare clients">
              <GitCompare size={13} strokeWidth={1.75} />
              Compare
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={toggleBulkMode}>
            {bulkMode ? "Cancel" : "Bulk"}
          </Button>
          {bulkMode && bulkSelected.size > 0 && (
            <>
              <Button variant="soft" size="sm" onClick={bulkSync} disabled={bulkBusy}>
                <RefreshCw
                  size={13}
                  strokeWidth={1.75}
                  className={bulkBusy ? "animate-spin" : ""}
                />
                Sync {bulkSelected.size}
              </Button>
              <Button variant="ghost" size="sm" onClick={bulkArchive} disabled={bulkBusy}>
                <Archive size={13} />
                Archive
              </Button>
              <Button variant="ghost" size="sm" onClick={bulkUnarchive} disabled={bulkBusy}>
                <ArchiveRestore size={13} />
                Restore
              </Button>
            </>
          )}
          <Button variant="soft" size="sm" onClick={handleSyncAll} disabled={syncingAll}>
            <RefreshCw size={13} strokeWidth={1.75} className={syncingAll ? "animate-spin" : ""} />
            {syncingAll ? "Syncing…" : "Sync all"}
          </Button>
        </div>
      </div>
      </Panel>

      {/* Dominant composition: today's book */}
      <TodayQueue
        todayItems={todayItems}
        onOpenClient={openClient}
        onStartTopAction={startTopAction}
        startingClientId={startingId}
        hero
      />

      {missingCore > 0 && (
        <div className="mb-4 rounded-[var(--radius-md)] border border-kinexis-signal/30 bg-kinexis-signal/5 px-3 py-2 text-[12px] text-ink">
          <strong className="font-semibold">
            {missingCore} client{missingCore === 1 ? "" : "s"}
          </strong>{" "}
          missing a Success Contract. Mandate GSC + GA4 + HubSpot, then set the contract KPI so
          Prove tracks leads/revenue — not vanity CTR.
        </div>
      )}

      {/* Risk pulse — single thin strip, not a competing panel */}
      {atRisk > 0 && (
        <div className="mb-6 flex items-center gap-3">
          <div
            className="flex h-1.5 min-w-0 flex-1 overflow-hidden"
            style={{ borderRadius: "var(--radius-sm)" }}
            title={`${critical} critical · ${watch} watch · ${healthy} healthy${
              (noData ?? 0) > 0 ? ` · ${noData} no data` : ""
            }`}
          >
            {critical > 0 && (
              <div
                className="h-full bg-kinexis-risk"
                style={{ width: `${(critical / rows.length) * 100}%` }}
              />
            )}
            {watch > 0 && (
              <div
                className="h-full bg-kinexis-signal"
                style={{ width: `${(watch / rows.length) * 100}%` }}
              />
            )}
            {healthy > 0 && (
              <div
                className="h-full bg-kinexis-proof/50"
                style={{ width: `${(healthy / rows.length) * 100}%` }}
              />
            )}
          </div>
          <span className="text-muted shrink-0 text-[11px] tabular-nums">
            {atRisk} at risk / {rows.length}
          </span>
        </div>
      )}

      <CollapsibleSection label="Capacity & owners" defaultOpen>
        <BookCapacity
          openWork={capacity.openWork}
          overdueWork={capacity.overdueWork}
          owners={capacity.owners}
        />
      </CollapsibleSection>

      <CollapsibleSection label={`Client directory · ${sorted.length}`} defaultOpen>
        <PortfolioClientTable
          rows={rows}
          sorted={sorted}
          sortKey={sortKey}
          setSortKey={setSortKey}
          ownerFilter={ownerFilter}
          setOwnerFilter={setOwnerFilter}
          ownerOptions={ownerOptions}
          myBookName={myBookName}
          setMyBook={setMyBook}
          assigneePresets={assigneePresets}
          priorityOnly={priorityOnly}
          setPriorityOnly={setPriorityOnly}
          reportReadyOnly={reportReadyOnly}
          setReportReadyOnly={setReportReadyOnly}
          tableSearch={tableSearch}
          setTableSearch={setTableSearch}
          hasActiveFilters={hasActiveFilters}
          clearFilters={clearFilters}
          bulkMode={bulkMode}
          bulkSelected={bulkSelected}
          toggleBulkSelect={toggleBulkSelect}
          toggleAllVisible={toggleAllVisible}
          onOpenClient={openClient}
          onStartTopAction={startTopAction}
          startingClientId={startingId}
        />
      </CollapsibleSection>

      <CollapsibleSection label={`Wins & AI value · ${wins.length}`}>
        <PortfolioWinsPanel
          wins={wins}
          aiValue={aiValue}
          leads30={leads30}
          revenue30={revenue30}
          onOpenClient={openClient}
        />
      </CollapsibleSection>
    </div>
  );
}

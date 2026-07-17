"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import CommandChrome from "@/components/shell/CommandChrome";
import CommandPalette from "@/components/CommandPalette";
import { OverviewSkeleton } from "@/components/Skeleton";
import { ToastProvider, useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import SettingsView from "@/components/SettingsView";
import ClientWorkspace from "@/components/ClientWorkspace";
import ShellLoadingScreen from "@/components/shell/ShellLoadingScreen";
import ShellLoginGate from "@/components/shell/ShellLoginGate";
import MobileShellBar from "@/components/shell/MobileShellBar";
import ClientWorkspaceHeader from "@/components/shell/ClientWorkspaceHeader";
import PortfolioHomeContent from "@/components/shell/PortfolioHomeContent";
import ClientComparisonView from "@/components/ClientComparisonView";
import { OfflineBanner } from "@/components/shell/OfflineBanner";
import { KeyboardShortcuts } from "@/components/shell/KeyboardShortcuts";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { api, Insight } from "@/lib/api";
import { useShellNavigation, type ShellTab } from "@/hooks/useShellNavigation";
import { useClientData } from "@/hooks/useClientData";
import { useAppShellSession } from "@/hooks/useAppShellSession";
import { useInsightTaskActions } from "@/hooks/useInsightTaskActions";
import TaskCreateModal from "@/components/TaskCreateModal";
import { ReportSessionProvider, useReportSession } from "@/components/ReportSessionContext";

function AppHome() {
  const { success, error: toastError, info: toastInfo } = useToast();
  const {
    status: reportStatus,
    setStatus: setReportStatus,
    focusGenerateKey: reportFocusGenerateKey,
    requestGenerateFocus,
    resetForClient,
  } = useReportSession();
  const {
    selectedClientId,
    client,
    metrics,
    insights,
    tasks,
    datasources,
    loading,
    hasLoadedOnce,
    error,
    syncing,
    lastSyncResults,
    assigneePresets,
    loadClient,
    syncClient,
    setSelectedClientId,
    setClient,
    setInsights,
    setTasks,
    setDatasources,
    setHasLoadedOnce,
    setLastSyncResults,
  } = useClientData();
  const {
    activeTab,
    setActiveTab,
    detectSegment,
    setDetectSegment,
    exploreMode,
    setExploreMode,
    prescribeSegment,
    setPrescribeSegment,
    navigateShell,
    scrollToFixes,
    urlClientId,
    setShellClientId,
    copyDeepLink,
  } = useShellNavigation("portfolio");
  const {
    phase,
    theme,
    toggleTheme,
    clientList,
    handleConnected,
    handleSignOut,
    handleClientsLoaded,
    handleClientRemoved,
  } = useAppShellSession({
    urlClientId,
    selectedClientId,
    setSelectedClientId,
    setClient,
    setHasLoadedOnce,
    setDatasources,
    setActiveTab,
    setDetectSegment,
    setShellClientId,
    toastError,
  });
  const {
    showTaskModal,
    setShowTaskModal,
    taskForm,
    setTaskForm,
    creatingTask,
    resolving,
    resolveTarget,
    setResolveTarget,
    requestResolve,
    insightHasShippedWork,
    handleResolveInsight,
    handleBulkResolve,
    handleBulkAssign,
    openInCursor,
    handleQuickAssign,
    handleCreateTask,
    handleUpdateTask,
    handleDeleteTask,
  } = useInsightTaskActions({
    selectedClientId,
    client,
    tasks,
    datasources,
    setTasks,
    setInsights,
    setActiveTab,
    success,
    toastError,
    toastInfo,
  });
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [requestAddClient, setRequestAddClient] = useState(0);
  const mainRef = useRef<HTMLElement>(null);
  const [showIndustry, setShowIndustry] = useState(false);
  const [profilePanelSection, setProfilePanelSection] = useState<"profile" | "datasources">(
    "profile"
  );
  const [visitedSituation, setVisitedSituation] = useState(false);
  const [generatedReportOnce, setGeneratedReportOnce] = useState(false);
  const [showCompare, setShowCompare] = useState(false);

  useEffect(() => {
    if (!showTaskModal) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowTaskModal(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showTaskModal, setShowTaskModal]);

  useEffect(() => {
    setShellClientId(selectedClientId);
  }, [selectedClientId, setShellClientId]);

  useEffect(() => {
    resetForClient();
  }, [selectedClientId, resetForClient]);

  useEffect(() => {
    const el = mainRef.current;
    if (!el) return;
    const heading = el.querySelector<HTMLElement>("h1[id], h2[id], [role='heading'][id]");
    if (!heading) {
      el.focus({ preventScroll: true });
    }
    const timer = setTimeout(() => {
      const target = heading || el;
      target.focus({ preventScroll: true });
    }, 100);
    return () => clearTimeout(timer);
  }, [activeTab]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const meta = e.metaKey || e.ctrlKey;
      if (meta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandOpen((v) => !v);
        return;
      }
      if (meta && e.key === ",") {
        e.preventDefault();
        setActiveTab("settings");
        return;
      }
      if (
        e.key === "?" &&
        !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        setShortcutsOpen((v) => !v);
        return;
      }
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (!selectedClientId || activeTab === "portfolio" || activeTab === "settings") return;
      const tabIds: ShellTab[] = ["detect", "prescribe", "execute", "prove", "report"];
      const n = Number(e.key);
      if (n >= 1 && n <= tabIds.length) {
        e.preventDefault();
        const tabId = tabIds[n - 1];
        if (tabId) setActiveTab(tabId);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedClientId, activeTab, setActiveTab]);

  // In-app anomaly inbox. In Electron, desktop notifications + IPC own delivery
  // so we don't race-mark items delivered before the OS alert can show.
  useEffect(() => {
    let cancelled = false;
    const isElectron = Boolean(window.kinexis?.onInsightNotification);

    const poll = async () => {
      if (isElectron) return;
      try {
        const res = await api.notifications.pending();
        const items = res.items || [];
        if (cancelled || items.length === 0) return;
        for (const item of items.slice(0, 3)) {
          toastInfo(`${item.title}: ${item.body}`);
        }
        await api.notifications.markDelivered(items.map((i) => i.id));
      } catch {
        /* ignore when API down */
      }
    };
    void poll();
    const id = window.setInterval(poll, 60_000);
    const onElectron = (data: { title?: string; body?: string }) => {
      if (data?.body) toastInfo(`${data.title || "Alert"}: ${data.body}`);
    };
    let unsubscribe: (() => void) | undefined;
    try {
      unsubscribe = window.kinexis?.onInsightNotification?.(onElectron);
    } catch {
      /* browser */
    }
    return () => {
      cancelled = true;
      window.clearInterval(id);
      unsubscribe?.();
    };
  }, [toastInfo]);

  const handleIndustryChange = async (industry: string) => {
    if (!selectedClientId || !client) return;
    try {
      const updated = await api.clients.update(selectedClientId, { industry });
      setClient(updated);
      success("Industry updated");
    } catch {
      toastError("Failed to update industry");
    }
  };

  const handleProfileSave = async (data: {
    profile: Record<string, unknown>;
    owner: string;
    priority: number;
  }) => {
    if (!selectedClientId) return;
    try {
      const updated = await api.clients.update(selectedClientId, {
        profile_json: JSON.stringify(data.profile),
        owner: data.owner,
        priority: data.priority,
      });
      setClient(updated);
      success("Client profile saved");
    } catch {
      toastError("Failed to save profile");
    }
  };

  useEffect(() => {
    if (selectedClientId && phase === "app") {
      setHasLoadedOnce(false);
      void loadClient(selectedClientId);
    }
  }, [selectedClientId, loadClient, phase, setHasLoadedOnce]);

  const handleRefresh = useCallback(async () => {
    if (!selectedClientId) return;
    try {
      toastInfo("Sync started \u2014 pulling from connected sources");
      const result = await syncClient(selectedClientId);
      const failed = Object.entries(result.results || {})
        .filter(([, v]) => v !== "ok" && !String(v).startsWith("skipped"))
        .map(([k]) => k.toUpperCase());
      const insightNote =
        result.insightsCreated && result.insightsCreated > 0
          ? ` \u00b7 ${result.insightsCreated} new insight${result.insightsCreated === 1 ? "" : "s"}`
          : " \u00b7 0 new detections \u2014 data accumulates over 7-30 days";
      if (failed.length > 0) {
        toastError(`Sync partial: ${failed.join(", ")} failed${insightNote}`);
      } else {
        success(`Sync complete${insightNote}`);
      }
    } catch (e) {
      console.error("Sync failed", e);
      toastError(e instanceof Error ? e.message : "Sync failed");
    }
  }, [selectedClientId, syncClient, success, toastError, toastInfo]);

  const doneTasks = useMemo(() => tasks.filter((t) => t.status === "done"), [tasks]);
  const unprovenTasks = useMemo(() => doneTasks.filter((t) => !t.impact_outcome), [doneTasks]);
  const openTasksCount = useMemo(
    () => tasks.filter((t) => t.status !== "done" && t.status !== "skipped").length,
    [tasks]
  );

  useEffect(() => {
    if (selectedClientId && activeTab === "detect" && detectSegment === "health") {
      setVisitedSituation(true);
    }
  }, [selectedClientId, activeTab, detectSegment]);

  useEffect(() => {
    if (reportStatus === "ready") {
      setGeneratedReportOnce(true);
    }
  }, [reportStatus]);

  const insightById = useMemo(() => {
    const map = new Map<number, Insight>();
    insights.forEach((i) => map.set(i.id, i));
    return map;
  }, [insights]);

  const openIssues = useMemo(() => insights.filter((i) => !i.resolved).length, [insights]);

  const showContentSkeleton = loading && !hasLoadedOnce;

  const selectClient = (id: number, landing: "detect" | "fixes" | "execute" = "detect") => {
    setSelectedClientId(id);
    setShellClientId(id);
    if (landing === "fixes") {
      setActiveTab("prescribe");
    } else if (landing === "execute") {
      setActiveTab("execute");
    } else {
      setActiveTab("detect");
      setDetectSegment("health");
    }
    setHasLoadedOnce(false);
    setShowIndustry(false);
    setLastSyncResults(null);
  };

  const openClientSmart = (
    clientId: number,
    hint?: {
      open_insights?: number;
      open_tasks?: number;
      risk?: string;
      tab?: string;
      insight_id?: number;
      task_id?: number;
    }
  ) => {
    setSelectedClientId(clientId);
    setHasLoadedOnce(false);
    setShowIndustry(false);
    setLastSyncResults(null);
    if (hint?.tab) {
      navigateShell(hint.tab);
      return;
    }
    if (hint?.task_id || (hint?.open_tasks || 0) > 0) {
      setActiveTab("execute");
      return;
    }
    if (
      hint?.insight_id ||
      (hint?.open_insights || 0) > 0 ||
      hint?.risk === "critical" ||
      hint?.risk === "watch"
    ) {
      setActiveTab("prescribe");
      setPrescribeSegment("fixes");
      return;
    }
    setActiveTab("detect");
    setDetectSegment("health");
  };

  if (phase === "loading") {
    return <ShellLoadingScreen />;
  }

  if (phase === "login") {
    return <ShellLoginGate onReady={handleConnected} />;
  }

  return (
    <div className="app-shell shell-atmosphere flex flex-col overflow-hidden">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <OfflineBanner />
      <CommandChrome
        selectedClientId={selectedClientId}
        activeTab={activeTab}
        theme={theme}
        onToggleTheme={toggleTheme}
        onCommandPalette={() => setCommandOpen(true)}
        onSelectClient={(id) => selectClient(id)}
        onGoPortfolio={() => setActiveTab("portfolio")}
        onGoSettings={() => setActiveTab("settings")}
        onSignOut={handleSignOut}
        onClientsLoaded={handleClientsLoaded}
        onClientRemoved={handleClientRemoved}
        requestAddClient={requestAddClient}
      />

      <main
        id="main-content"
        ref={mainRef}
        className="min-h-0 min-w-0 flex-1 overflow-y-auto"
        tabIndex={-1}
      >
        <ErrorBoundary>
          <MobileShellBar
            clientName={client?.name}
            activeTab={activeTab}
            onOpenCommand={() => setCommandOpen(true)}
          />

          {showCompare ? (
            <ClientComparisonView
              clients={clientList.map((c) => ({ id: c.id, name: c.name }))}
              onClose={() => setShowCompare(false)}
            />
          ) : activeTab === "settings" ? (
            <div className="workspace-content animate-fade-up !max-w-3xl">
              <SettingsView />
            </div>
          ) : activeTab === "portfolio" || !selectedClientId ? (
            <PortfolioHomeContent
              clientCount={clientList.length}
              hasSynced={
                Boolean(selectedClientId) && Boolean(datasources.some((d) => d.last_synced_at))
              }
              hasGsc={
                Boolean(selectedClientId) && Boolean(datasources.some((d) => d.type === "gsc"))
              }
              hasGa4={
                Boolean(selectedClientId) && Boolean(datasources.some((d) => d.type === "ga4"))
              }
              hasHubspot={
                Boolean(selectedClientId) && Boolean(datasources.some((d) => d.type === "hubspot"))
              }
              hasContract={Boolean(
                client?.profile_json && String(client.profile_json).includes("success_contract")
              )}
              hasVisitedSituation={visitedSituation}
              hasCompletedFix={Boolean(selectedClientId) && doneTasks.length > 0}
              hasProvenWin={Boolean(
                selectedClientId &&
                tasks.some((t) => t.status === "done" && t.impact_outcome === "win")
              )}
              hasGeneratedReport={generatedReportOnce}
              onGoPortfolio={() => setActiveTab("portfolio")}
              onAddClient={() => setRequestAddClient((n) => n + 1)}
              onConnectCrm={() => setActiveTab("settings")}
              onSync={() => {
                if (selectedClientId) void handleRefresh();
                else {
                  toastInfo("Pick a client from the switcher, then sync from the war room");
                  setRequestAddClient((n) => n + 1);
                }
              }}
              onOpenSituation={() => {
                const id = selectedClientId ?? clientList[0]?.id;
                if (!id) {
                  setRequestAddClient((n) => n + 1);
                  return;
                }
                selectClient(id);
              }}
              onOpenFixQueue={() => {
                const id = selectedClientId ?? clientList[0]?.id;
                if (!id) {
                  setRequestAddClient((n) => n + 1);
                  return;
                }
                selectClient(id);
                setActiveTab("prescribe");
              }}
              onOpenProve={() => {
                const id = selectedClientId ?? clientList[0]?.id;
                if (!id) {
                  setRequestAddClient((n) => n + 1);
                  return;
                }
                selectClient(id);
                setActiveTab("prove");
              }}
              onOpenReport={() => {
                const id = selectedClientId ?? clientList[0]?.id;
                if (!id) {
                  setRequestAddClient((n) => n + 1);
                  return;
                }
                selectClient(id);
                setActiveTab("report");
              }}
              onSelectClient={(id) => selectClient(id)}
              onOpenClient={(clientId, hint) => openClientSmart(clientId, hint)}
              onCompare={() => setShowCompare(true)}
            />
          ) : (
            <div className="workspace-content">
              {error && (
                <div
                  className="animate-fade-up mb-4 border border-kinexis-risk/20 bg-kinexis-risk/10 px-4 py-3 text-sm text-kinexis-risk"
                  style={{ borderRadius: "var(--radius-md)" }}
                >
                  {error}
                </div>
              )}

              <ClientWorkspaceHeader
                client={client}
                selectedClientId={selectedClientId}
                loading={loading}
                hasLoadedOnce={hasLoadedOnce}
                openIssues={openIssues}
                datasources={datasources}
                syncing={syncing}
                lastSyncResults={lastSyncResults}
                showIndustry={showIndustry}
                profilePanelSection={profilePanelSection}
                activeTab={activeTab}
                openTasks={openTasksCount}
                doneTasks={doneTasks.length}
                unprovenTasks={unprovenTasks.length}
                reportStatus={reportStatus}
                onSync={() => void handleRefresh()}
                onToggleIndustry={() => setShowIndustry((v) => !v)}
                onProfileSectionChange={setProfilePanelSection}
                onIndustryChange={handleIndustryChange}
                onProfileSave={handleProfileSave}
                onDatasourcesChanged={setDatasources}
                onTabChange={(id) => setActiveTab(id)}
              />

              {showContentSkeleton ? (
                <OverviewSkeleton />
              ) : (
                <ClientWorkspace
                  activeTab={activeTab}
                  setActiveTab={setActiveTab}
                  selectedClientId={selectedClientId}
                  clientName={client?.name}
                  clientIndustry={client?.industry}
                  siteRelaunchedAt={client?.site_relaunched_at}
                  metrics={metrics}
                  insights={insights}
                  tasks={tasks}
                  datasources={datasources}
                  openIssues={openIssues}
                  insightById={insightById}
                  doneTasks={doneTasks}
                  assigneePresets={assigneePresets}
                  scrollToFixes={scrollToFixes}
                  onResolve={requestResolve}
                  onBulkResolve={handleBulkResolve}
                  onBulkAssign={handleBulkAssign}
                  onQuickAssign={(insight) => void handleQuickAssign(insight)}
                  onCreateTask={(insight) => setShowTaskModal(insight)}
                  onTaskCreated={(task) => {
                    setTasks((prev) => [task, ...prev]);
                    if (task.insight_id) {
                      setInsights((prev) =>
                        prev.map((i) => (i.id === task.insight_id ? { ...i, resolved: true } : i))
                      );
                    }
                    if (task.assigned_to === "Cursor") void openInCursor(task);
                  }}
                  onUpdateTask={handleUpdateTask}
                  onDeleteTask={handleDeleteTask}
                  onImpactOutcomeChange={(taskId, outcome) => {
                    setTasks((prev) =>
                      prev.map((t) => (t.id === taskId ? { ...t, impact_outcome: outcome } : t))
                    );
                    if (outcome === "win" && selectedClientId) {
                      const task = tasks.find((t) => t.id === taskId);
                      void api.levers
                        .list(selectedClientId, false)
                        .then((levers) => {
                          const linked =
                            (task?.lever_id != null
                              ? levers.find((l) => l.id === task.lever_id)
                              : undefined) ||
                            levers.find(
                              (l) =>
                                l.task_id === taskId ||
                                (task?.insight_id != null &&
                                  l.source_insight_ids?.includes(task.insight_id))
                            );
                          if (!linked) return;
                          return api.levers.setStatus(linked.id, {
                            status: "proven",
                            include_in_report: true,
                            impact_summary: `Win on task #${taskId}`,
                          });
                        })
                        .then((updated) => {
                          if (updated) success("Win packed into report draft");
                        })
                        .catch(() => {});
                    }
                  }}
                  reportFocusGenerateKey={reportFocusGenerateKey}
                  onReportStatusChange={setReportStatus}
                  detectSegment={detectSegment}
                  setDetectSegment={setDetectSegment}
                  exploreMode={exploreMode}
                  setExploreMode={setExploreMode}
                  prescribeSegment={prescribeSegment}
                  setPrescribeSegment={setPrescribeSegment}
                />
              )}
            </div>
          )}
        </ErrorBoundary>
      </main>

      <CommandPalette
        open={commandOpen}
        onClose={() => setCommandOpen(false)}
        clients={clientList}
        onSelectClient={(id) => selectClient(id)}
        onNavigate={navigateShell}
        hasClient={
          Boolean(selectedClientId) && activeTab !== "portfolio" && activeTab !== "settings"
        }
        clientName={client?.name}
        onSync={() => void handleRefresh()}
        onGeneratePlan={() => {
          setActiveTab("prescribe");
          setPrescribeSegment("ai_plan");
        }}
        onExportReport={() => {
          setActiveTab("report");
          requestGenerateFocus();
        }}
        onGenerateReport={() => {
          setActiveTab("report");
          requestGenerateFocus();
        }}
        onCopyDeepLink={async () => {
          const ok = await copyDeepLink();
          if (ok) success("Deep link copied");
        }}
        onStartFix={scrollToFixes}
        onOpenTopLever={() => {
          setActiveTab("detect");
          setDetectSegment("levers");
        }}
        onAssignTopFix={() => {
          const top = [...insights]
            .filter((i) => !i.resolved)
            .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))[0];
          if (!top) {
            toastError("No open fixes to assign");
            return;
          }
          void handleQuickAssign(top);
        }}
      />

      <KeyboardShortcuts open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />

      {showTaskModal && (
        <TaskCreateModal
          insight={showTaskModal}
          assigneePresets={assigneePresets}
          taskForm={taskForm}
          setTaskForm={setTaskForm}
          creating={creatingTask}
          onClose={() => !creatingTask && setShowTaskModal(null)}
          onCreate={() => void handleCreateTask()}
        />
      )}

      <ConfirmDialog
        open={resolveTarget != null}
        title={
          resolveTarget != null && insightHasShippedWork(resolveTarget)
            ? "Resolve shipped insight?"
            : "Mark as won't-fix?"
        }
        description={
          resolveTarget != null && insightHasShippedWork(resolveTarget)
            ? "Linked work is done. This clears it from the Fix queue (shipped)."
            : "No completed task is linked yet. Resolving marks this as won't-fix so the queue stays honest. Prefer Assign → Execute first when you will ship a fix."
        }
        confirmLabel={
          resolveTarget != null && insightHasShippedWork(resolveTarget)
            ? "Resolve (shipped)"
            : "Won't fix"
        }
        busy={resolving}
        onConfirm={() => void handleResolveInsight()}
        onCancel={() => !resolving && setResolveTarget(null)}
      />
    </div>
  );
}

export default function Home() {
  return (
    <ToastProvider>
      <ReportSessionProvider>
        <AppHome />
      </ReportSessionProvider>
    </ToastProvider>
  );
}

"use client";

import { useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { api, Insight, Task, DataSource, Client } from "@/lib/api";
import type { ShellTab } from "@/hooks/useShellNavigation";

const DEFAULT_ASSIGNEE = "Cursor";

function extractEvidenceText(message: string): string | undefined {
  const pieces: string[] = [];
  const ctrMatch = message.match(/CTR\s+([\d.]+%)\s*\([^)]*?expected\s*~?([\d.]+%)/i);
  const posMatch = message.match(/(?:pos|position)\s+([\d.]+)/i);
  const imprMatch = message.match(/([\d,.]+)\s*impr/i);
  const scoreMatch = message.match(/(\d{1,3})\s*\/\s*100\b/);
  const sessionsMatch = message.match(/([\d,.]+)\s*sessions/i);
  if (posMatch) pieces.push(`Position: ${posMatch[1]}`);
  if (ctrMatch) pieces.push(`CTR: ${ctrMatch[1]} (Expected: ${ctrMatch[2]})`);
  if (imprMatch) pieces.push(`Impressions: ${imprMatch[1]}`);
  if (scoreMatch) pieces.push(`Score: ${scoreMatch[1]}/100`);
  if (sessionsMatch) pieces.push(`Sessions: ${sessionsMatch[1]}`);
  return pieces.length ? pieces.join(" | ") : undefined;
}

export interface UseInsightTaskActionsOptions {
  selectedClientId: number | null;
  client: Client | null;
  tasks: Task[];
  datasources: DataSource[];
  setTasks: Dispatch<SetStateAction<Task[]>>;
  setInsights: Dispatch<SetStateAction<Insight[]>>;
  setActiveTab: (tab: ShellTab | ((prev: ShellTab) => ShellTab)) => void;
  success: (
    message: string,
    options?: { action?: { label: string; onClick: () => void | Promise<void> }; duration?: number }
  ) => void;
  toastError: (message: string) => void;
  toastInfo: (message: string) => void;
}

/** Resolve / assign / Cursor-open handlers extracted from the app shell. */
export function useInsightTaskActions({
  selectedClientId,
  client,
  tasks,
  datasources,
  setTasks,
  setInsights,
  setActiveTab,
  success,
  toastError,
  toastInfo: _toastInfo,
}: UseInsightTaskActionsOptions) {
  const [showTaskModal, setShowTaskModal] = useState<Insight | null>(null);
  const [taskForm, setTaskForm] = useState({ assigned_to: "", due_date: "" });
  const [creatingTask, setCreatingTask] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolveTarget, setResolveTarget] = useState<number | null>(null);

  const clientStaleDays = useMemo(() => {
    const synced = datasources.map((d) => d.last_synced_at).filter((t): t is string => Boolean(t));
    if (!synced.length) return 999;
    const latest = new Date(Math.max(...synced.map((s) => new Date(s).getTime())));
    return Math.max(0, Math.floor((Date.now() - latest.getTime()) / (1000 * 60 * 60 * 24)));
  }, [datasources]);

  const requestResolve = (insightId: number) => {
    setResolveTarget(insightId);
  };

  const insightHasShippedWork = (insightId: number) =>
    tasks.some((t) => t.insight_id === insightId && t.status === "done");

  const handleResolveInsight = async (forceWontFix = false) => {
    if (resolveTarget == null) return;
    const targetId = resolveTarget;
    const shipped = insightHasShippedWork(targetId);
    const reason = forceWontFix ? "wont_fix" : shipped ? "shipped" : "wont_fix";
    setResolving(true);
    try {
      await api.insights.resolve(targetId, reason);
      setInsights((prev) => prev.map((i) => (i.id === targetId ? { ...i, resolved: true } : i)));
      success(reason === "wont_fix" ? "Marked won't-fix" : "Insight resolved (shipped)", {
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await api.insights.unresolve(targetId);
              setInsights((prev) =>
                prev.map((i) => (i.id === targetId ? { ...i, resolved: false } : i))
              );
              success("Insight restored to Fix queue");
            } catch {
              toastError("Failed to undo resolve");
            }
          },
        },
      });
      setResolveTarget(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to resolve insight");
    } finally {
      setResolving(false);
    }
  };

  const handleBulkResolve = async (ids: number[]) => {
    if (ids.length === 0) return;
    try {
      await Promise.all(
        ids.map((id) =>
          api.insights.resolve(id, insightHasShippedWork(id) ? "shipped" : "wont_fix")
        )
      );
      setInsights((prev) => prev.map((i) => (ids.includes(i.id) ? { ...i, resolved: true } : i)));
      success(`Resolved ${ids.length} insight${ids.length === 1 ? "" : "s"}`, {
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await Promise.all(ids.map((id) => api.insights.unresolve(id)));
              setInsights((prev) =>
                prev.map((i) => (ids.includes(i.id) ? { ...i, resolved: false } : i))
              );
              success("Restored to Fix queue");
            } catch {
              toastError("Failed to undo bulk resolve");
            }
          },
        },
      });
    } catch {
      toastError("Failed to resolve selected insights");
    }
  };

  const openInCursor = async (
    task: Task,
    extra?: {
      recommendedAction?: string;
      message?: string;
      targetQuery?: string;
      targetUrl?: string;
      evidence?: string;
      playbookPattern?: string;
    }
  ) => {
    if (!window.kinexis?.openCursorForTask) {
      return;
    }
    try {
      const title = task.result_notes?.split("\n")?.[0] || `Task ${task.id}`;
      const recAction = extra?.recommendedAction || task.result_notes || "";
      // Extract FROM→TO copy from the recommended action for the brief
      const fromToParts = recAction
        .split("\n")
        .filter((l) => l.includes("FROM") && l.includes("TO"))
        .map((l) => l.trim());
      const fromToCopy = fromToParts.length ? fromToParts.join("\n") : undefined;
      const result = await window.kinexis.openCursorForTask(task.id, {
        title,
        message: extra?.message || task.result_notes || undefined,
        recommendedAction: recAction || undefined,
        notes: task.result_notes || undefined,
        clientName: client?.name || undefined,
        targetQuery: extra?.targetQuery || task.target_query || undefined,
        targetUrl: extra?.targetUrl || task.target_url || undefined,
        evidence: extra?.evidence || undefined,
        playbookPattern: extra?.playbookPattern || task.playbook_pattern || undefined,
        fromToCopy,
      });
      if (result.ok) {
        success("Opened in editor");
      } else {
        toastError(result.error || "Could not open editor");
      }
    } catch {
      toastError("Could not open editor");
    }
  };

  const handleBulkAssign = async (picked: Insight[]) => {
    if (!selectedClientId || picked.length === 0) return;
    if (clientStaleDays >= 3) {
      toastError(`Sync required before assign — data is ${clientStaleDays}d stale`);
      return;
    }
    setCreatingTask(true);
    try {
      const created: Task[] = [];
      const resolvedIds: number[] = [];
      for (const insight of picked) {
        const notes = [
          insight.recommended_action || insight.message.slice(0, 200),
          `Severity: ${insight.severity}`,
        ].join("\n");
        const newTask = await api.tasks.create({
          client_id: selectedClientId,
          insight_id: insight.id,
          assigned_to: DEFAULT_ASSIGNEE,
          result_notes: notes,
        });
        created.push(newTask);
        resolvedIds.push(insight.id);
        api.insights.resolve(insight.id).catch((e) => {
          console.warn("Failed to resolve insight after assign", e);
          toastError("Assigned, but could not mark insight resolved");
        });
      }
      setTasks((prev) => [...created, ...prev]);
      setInsights((prev) =>
        prev.map((i) => (resolvedIds.includes(i.id) ? { ...i, resolved: true } : i))
      );
      success(`Assigned ${created.length} fix${created.length === 1 ? "" : "es"}`);
      setActiveTab("execute");
    } catch {
      toastError("Failed to assign selected insights");
    } finally {
      setCreatingTask(false);
    }
  };

  const handleQuickAssign = async (insight: Insight) => {
    if (!selectedClientId) return;
    if (clientStaleDays >= 3) {
      toastError(`Sync required before assign — data is ${clientStaleDays}d stale`);
      return;
    }
    setCreatingTask(true);
    try {
      const metricHint =
        insight.type === "ctr_opportunity" || insight.type === "ctr_gap"
          ? "Watch: gsc.ctr, gsc.clicks"
          : insight.type === "content_opportunity"
            ? "Watch: gsc.clicks, gsc.impressions"
            : insight.type === "cro_opportunity" || insight.type === "bounce_cro_alert"
              ? "Watch: ga4.key_events, ga4.sessions"
              : insight.type.startsWith("pagespeed")
                ? "Watch: gsc.clicks, ga4.sessions"
                : "Watch primary metrics in Prove after completion";
      const notes = [
        insight.recommended_action || insight.message.slice(0, 200),
        `Severity: ${insight.severity}`,
        metricHint,
      ].join("\n");
      let newTask = await api.tasks.create({
        client_id: selectedClientId,
        insight_id: insight.id,
        assigned_to: DEFAULT_ASSIGNEE,
        result_notes: notes,
      });
      // Capture Prove baseline immediately (in_progress triggers snapshot)
      try {
        newTask = await api.tasks.update(newTask.id, { status: "in_progress" });
      } catch {
        /* non-fatal — task still created */
      }
      setTasks((prev) => [newTask, ...prev]);
      setInsights((prev) => prev.map((i) => (i.id === insight.id ? { ...i, resolved: true } : i)));
      api.insights.resolve(insight.id).catch((e) => {
        console.warn("Failed to resolve insight after assign", e);
        toastError("Assigned, but could not mark insight resolved");
      });
      success("Assigned — baseline captured");
      void openInCursor(newTask, {
        recommendedAction: insight.recommended_action ?? undefined,
        message: insight.message,
        targetQuery: insight.target_query ?? undefined,
        targetUrl: insight.target_url ?? undefined,
        evidence: extractEvidenceText(insight.message),
      });
      setActiveTab("execute");
    } catch {
      toastError("Failed to create work item");
    } finally {
      setCreatingTask(false);
    }
  };

  const handleCreateTask = async () => {
    if (!showTaskModal || !selectedClientId) return;
    if (clientStaleDays >= 3) {
      toastError(`Sync required before assign — data is ${clientStaleDays}d stale`);
      return;
    }
    setCreatingTask(true);
    try {
      const assignee = taskForm.assigned_to || DEFAULT_ASSIGNEE;
      const notes = showTaskModal.recommended_action || showTaskModal.message.slice(0, 200);
      const newTask = await api.tasks.create({
        client_id: selectedClientId,
        insight_id: showTaskModal.id,
        assigned_to: assignee,
        due_date: taskForm.due_date || undefined,
        result_notes: notes,
      });
      setTasks((prev) => [newTask, ...prev]);
      setInsights((prev) =>
        prev.map((i) => (i.id === showTaskModal.id ? { ...i, resolved: true } : i))
      );
      api.insights.resolve(showTaskModal.id).catch((e) => {
        console.warn("Failed to resolve insight after task create", e);
        toastError("Task created, but could not mark insight resolved");
      });
      setShowTaskModal(null);
      setTaskForm({ assigned_to: "", due_date: "" });
      if (assignee === "Cursor") {
        success("Assigned — opening editor");
        void openInCursor(newTask, {
          recommendedAction: showTaskModal.recommended_action ?? undefined,
          message: showTaskModal.message,
          targetQuery: showTaskModal.target_query ?? undefined,
          targetUrl: showTaskModal.target_url ?? undefined,
          evidence: extractEvidenceText(showTaskModal.message),
        });
      } else {
        success("Work item created — open Execute to track it");
      }
      setActiveTab("execute");
    } catch {
      toastError("Failed to create work item");
    } finally {
      setCreatingTask(false);
    }
  };

  const handleUpdateTask = async (taskId: number, updates: Partial<Task>) => {
    try {
      const updated = await api.tasks.update(taskId, updates);
      setTasks((prev) => prev.map((t) => (t.id === taskId ? updated : t)));
      if (updates.status === "done" && updated.insight_id) {
        setInsights((prev) =>
          prev.map((i) => (i.id === updated.insight_id ? { ...i, resolved: true } : i))
        );
      }
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to update task");
    }
  };

  const handleDeleteTask = async (taskId: number) => {
    try {
      await api.tasks.delete(taskId);
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to delete task");
    }
  };

  return {
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
  };
}

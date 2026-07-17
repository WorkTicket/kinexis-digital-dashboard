"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  Zap,
  Clock,
  Plus,
  SkipForward,
  ExternalLink,
  AlertTriangle,
} from "lucide-react";
import { api, Task } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { motion } from "@/lib/motion";

type Action = {
  title: string;
  category: string;
  priority_score: number;
  why_it_matters?: string;
  estimated_impact: string;
  effort: string;
  steps: string[];
  metrics_to_watch: string[];
  expected_timeline: string;
  evidence?: string;
  success_metric?: string;
  playbook_pattern?: string;
  target_url?: string;
  target_query?: string;
  current_state?: Record<string, string>;
  proposed_changes?: Record<string, string>;
  insight_id?: number;
};

function normalizeAction(raw: Partial<Action> | null | undefined): Action {
  const a = raw || {};
  const asStringMap = (v: unknown): Record<string, string> | undefined => {
    if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
    const out: Record<string, string> = {};
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      if (typeof val === "string" && val.trim()) out[k] = val;
    }
    return Object.keys(out).length ? out : undefined;
  };
  return {
    title: typeof a.title === "string" && a.title.trim() ? a.title : "Untitled action",
    category: typeof a.category === "string" && a.category ? a.category : "analytics",
    priority_score: Number.isFinite(Number(a.priority_score)) ? Number(a.priority_score) : 0,
    why_it_matters: a.why_it_matters,
    estimated_impact:
      typeof a.estimated_impact === "string" && a.estimated_impact ? a.estimated_impact : "",
    effort: typeof a.effort === "string" && a.effort ? a.effort : "medium",
    steps: Array.isArray(a.steps) ? a.steps.filter((s) => typeof s === "string") : [],
    metrics_to_watch: Array.isArray(a.metrics_to_watch)
      ? a.metrics_to_watch.filter((m) => typeof m === "string")
      : [],
    expected_timeline:
      typeof a.expected_timeline === "string" && a.expected_timeline
        ? a.expected_timeline
        : "2–4 weeks",
    evidence: a.evidence,
    success_metric: a.success_metric,
    playbook_pattern: a.playbook_pattern,
    target_url: typeof a.target_url === "string" ? a.target_url : undefined,
    target_query: typeof a.target_query === "string" ? a.target_query : undefined,
    current_state: asStringMap(a.current_state),
    proposed_changes: asStringMap(a.proposed_changes),
    insight_id: typeof (a as any).insight_id === "number" ? (a as any).insight_id : undefined,
  };
}

type Props = {
  clientId: number;
  assigneePresets?: string[];
  onTaskCreated?: (task: Task) => void;
  onGoToExecute?: () => void;
};

function assigneeForPlaybook(pattern?: string, fallback = "Unassigned"): string {
  if (!pattern) return fallback;
  const humanPatterns = new Set(["leads_revenue_leak", "error_spike_alert"]);
  if (humanPatterns.has(pattern)) return "Human";
  return fallback;
}

const categoryColors: Record<string, string> = {
  content: "!bg-transparent !text-kinexis-focus !border-kinexis-focus/30",
  technical_seo: "!bg-transparent !text-ink-secondary !border-[color:var(--border-default)]",
  cro: "!bg-transparent !text-kinexis-focus !border-kinexis-focus/25",
  speed: "!bg-transparent !text-kinexis-signal !border-kinexis-signal/30",
  link_building: "!bg-transparent !text-kinexis-signal !border-kinexis-signal/25",
  ux: "!bg-transparent !text-kinexis-focus !border-kinexis-focus/20",
  local_seo: "!bg-transparent !text-kinexis-signal !border-kinexis-signal/25",
  analytics: "!bg-transparent !text-ink-secondary !border-[color:var(--border-default)]",
};

const effortTone: Record<string, "brand" | "warning" | "danger"> = {
  low: "brand",
  medium: "warning",
  high: "danger",
};

const SKIP_STORAGE_PREFIX = "kinexis-skipped-plan-";

function loadSkipped(planId: number): Set<string> {
  try {
    const raw = localStorage.getItem(`${SKIP_STORAGE_PREFIX}${planId}`);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((v) => typeof v === "string"));
  } catch {
    return new Set();
  }
}

function saveSkipped(planId: number, skipped: Set<string>) {
  try {
    localStorage.setItem(`${SKIP_STORAGE_PREFIX}${planId}`, JSON.stringify([...skipped]));
  } catch {
    // storage full — silently degrade
  }
}

function ScorePill({ score, impact }: { score: number; impact: string }) {
  const color =
    score >= 80
      ? "border-kinexis-proof/40 text-kinexis-proof"
      : score >= 50
        ? "border-kinexis-signal/40 text-kinexis-signal"
        : "border-kinexis-risk/40 text-kinexis-risk";
  return (
    <div className="flex shrink-0 items-center gap-2">
      <div
        className={`flex h-7 w-7 items-center justify-center border ${color} font-mono-data text-[11px] font-semibold`}
        style={{ borderRadius: "var(--radius-sm)" }}
      >
        {score}
      </div>
      {impact && (
        <span className="hidden whitespace-nowrap text-[11px] font-medium text-kinexis-proof sm:inline">
          {impact}
        </span>
      )}
    </div>
  );
}

export default function ActionBoard({
  clientId,
  assigneePresets,
  onTaskCreated,
  onGoToExecute,
}: Props) {
  const { success, error } = useToast();
  const [plan, setPlan] = useState<{
    id: number;
    title: string;
    content: Action[];
    created_at: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [confirmRegen, setConfirmRegen] = useState(false);
  const [creatingIdx, setCreatingIdx] = useState<number | null>(null);
  const [handledItems, setHandledItems] = useState<Map<number, "assigned" | "skipped">>(new Map());
  const [skippedTitles, setSkippedTitles] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const [cursorAvailable, setCursorAvailable] = useState(false);
  const [generationFailed, setGenerationFailed] = useState(false);

  useEffect(() => {
    setCursorAvailable(Boolean(window.kinexis?.openCursorForTask));
  }, []);

  const loadPlan = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    setLoadError(null);
    try {
      const data = await api.actions.getLatestPlan(clientId, { signal });
      if (signal.aborted) return;
      if (data.status !== "none") {
        const content = Array.isArray(data.content)
          ? data.content.map((item) => normalizeAction(item as Partial<Action>))
          : [];
        const planData = {
          id: data.id,
          title: data.title,
          content,
          created_at: data.created_at,
        };
        setPlan(planData);
        setSkippedTitles(loadSkipped(data.id));
        setGenerationFailed(false);
      } else {
        setPlan(null);
        setSkippedTitles(new Set());
        setGenerationFailed(false);
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setLoadError(e instanceof Error ? e.message : "Failed to load AI plan");
        error("Failed to load AI plan");
      }
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [clientId, error]);

  useEffect(() => {
    setLoading(true);
    loadPlan();
    return () => abortRef.current?.abort();
  }, [loadPlan]);

  const generatePlan = async (isRegen: boolean) => {
    setGenerating(true);
    setGenerationFailed(false);
    try {
      const res = await api.actions.generatePlan(clientId);
      if (res.status !== "generated") {
        setGenerationFailed(true);
        error(res.message || "AI plan generation failed — check Ollama is running");
        // Clear old plan so stale cached content isn't mistaken for a fresh generation
        setPlan(null);
        return;
      }
      await loadPlan();
      setHandledItems(new Map());
      setGenerationFailed(false);
      success(isRegen ? "AI plan regenerated" : "AI plan generated");
      setConfirmRegen(false);
    } catch (e) {
      setGenerationFailed(true);
      const timedOut =
        (e instanceof DOMException && e.name === "AbortError") ||
        (e instanceof Error && e.message.toLowerCase().includes("abort"));
      error(
        timedOut
          ? "AI timed out — first Ollama run can take a few minutes. Try again."
          : "Failed to generate AI plan"
      );
    } finally {
      setGenerating(false);
    }
  };

  const sorted = useMemo(
    () => (plan ? [...plan.content].sort((a, b) => b.priority_score - a.priority_score) : []),
    [plan]
  );

  const visibleActions = useMemo(
    () => sorted.filter((a) => !skippedTitles.has(a.title)),
    [sorted, skippedTitles]
  );

  const createWorkItem = async (action: Action, idx: number) => {
    setCreatingIdx(idx);
    try {
      const steps = action.steps || [];
      const stepsPreview = steps
        .slice(0, 4)
        .map((s, i) => `${i + 1}. ${s}`)
        .join("\n");
      const changeLines = action.proposed_changes
        ? Object.entries(action.proposed_changes)
            .map(([k, v]) => `${k}: ${v}`)
            .join("\n")
        : "";
      const notes = [
        action.title,
        action.target_url ? `Page: ${action.target_url}` : "",
        action.target_query ? `Query: ${action.target_query}` : "",
        changeLines ? `Ship this copy:\n${changeLines}` : "",
        action.evidence ? `Evidence: ${action.evidence}` : "",
        action.why_it_matters || "",
        action.success_metric ? `Moves: ${action.success_metric}` : "",
        stepsPreview,
      ]
        .filter(Boolean)
        .join("\n\n")
        .slice(0, 2000);
      const assignee = assigneeForPlaybook(
        action.playbook_pattern,
        assigneePresets?.[0] || "Unassigned"
      );
      const task = await api.tasks.create({
        client_id: clientId,
        insight_id: action.insight_id,
        assigned_to: assignee,
        result_notes: notes,
        playbook_pattern: action.playbook_pattern || undefined,
        action_plan_id: plan?.id,
        target_query: action.target_query || undefined,
        target_url: action.target_url || undefined,
      });
      if (action.insight_id) {
        api.insights.resolve(action.insight_id).catch((e) => {
          console.warn("Failed to resolve insight after assign", e);
          error("Work item created, but could not mark insight resolved");
        });
      }
      setHandledItems((prev) => new Map(prev).set(idx, "assigned"));

      const isCursor = assignee === "Cursor" && cursorAvailable;
      if (isCursor) {
        const win = window as any;
        if (win.kinexis?.openCursorForTask && task) {
          win.kinexis.openCursorForTask(task.id, {
            clientName: "",
            playbookPattern: action.playbook_pattern || "",
            title: action.title,
            targetUrl: action.target_url || "",
            targetQuery: action.target_query || "",
            recommendedAction: action.why_it_matters || "",
            evidence: action.evidence || "",
            notes: action.why_it_matters || "",
            message: action.why_it_matters || "",
            fromToCopy:
              [
                ...(action.current_state
                  ? Object.entries(action.current_state).map(([k, v]) => `FROM (${k}): ${v}`)
                  : []),
                ...(action.proposed_changes
                  ? Object.entries(action.proposed_changes).map(([k, v]) => `TO (${k}): ${v}`)
                  : []),
              ].join("\n") || "",
          });
        }
        success("Assigned — track progress in Execute", {
          action: {
            label: "Go to Execute",
            onClick: () => onGoToExecute?.(),
          },
        });
      } else {
        success("Work item created — open Execute to track it");
      }
      onTaskCreated?.(task);
    } catch {
      error("Failed to create work item");
    } finally {
      setCreatingIdx(null);
    }
  };

  const skipWorkItem = (action: Action, idx: number) => {
    if (!plan) return;
    setHandledItems((prev) => new Map(prev).set(idx, "skipped"));
    const next = new Set(skippedTitles).add(action.title);
    setSkippedTitles(next);
    saveSkipped(plan.id, next);
    success("Skipped — won't reappear until next regeneration");
  };

  if (loading) {
    return <LoadingState label="Loading board…" variant="board" className="animate-fade-up" />;
  }

  if (loadError && !plan) {
    return (
      <ErrorState
        title="AI plan unavailable"
        description={loadError}
        onRetry={() => {
          setLoading(true);
          void loadPlan();
        }}
        className="animate-fade-up"
      />
    );
  }

  if (!plan) {
    return (
      <EmptyState
        className="animate-fade-up"
        title="No AI plan yet"
        description="Generate a prioritized plan from this client's insights and metrics — ranked by impact vs effort, with plain-English why it matters."
        action={
          <Button
            onClick={() => void generatePlan(false)}
            disabled={generating}
            className={generating ? motion.busy : undefined}
          >
            {generating ? "Generating…" : "Generate AI plan"}
          </Button>
        }
      />
    );
  }

  return (
    <div className="animate-fade-up">
      {plan.created_at &&
        (() => {
          const planDate = new Date(plan.created_at);
          const hoursSince = (Date.now() - planDate.getTime()) / (1000 * 60 * 60);
          if (hoursSince > 24) {
            return (
              <div className="panel mb-4 flex items-start gap-3 p-3">
                <AlertTriangle size={16} className="mt-0.5 shrink-0 text-kinexis-signal" />
                <div>
                  <p className="text-[13px] font-medium text-ink">
                    Cached plan from {plan.created_at.slice(0, 10)}
                  </p>
                  <p className="text-muted mt-0.5 text-xs">
                    This plan is over 24 hours old. Regenerate for fresh AI analysis of current
                    metrics.
                  </p>
                </div>
              </div>
            );
          }
          return null;
        })()}
      {generationFailed && (
        <div className="panel mb-4 flex items-start gap-3 p-3">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-kinexis-risk" />
          <div>
            <p className="text-[13px] font-medium text-ink">Generation failed</p>
            <p className="text-muted mt-0.5 text-xs">
              Check that Ollama is running, or sync new data first. Old plan was cleared.
            </p>
          </div>
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="section-label">AI plan</h2>
          <p className="section-title">
            {visibleActions.length} prioritized actions
            {plan.created_at ? ` · ${String(plan.created_at).slice(0, 10)}` : ""}
          </p>
        </div>
        <Button
          variant="soft"
          size="sm"
          onClick={() => setConfirmRegen(true)}
          disabled={generating}
          className={generating ? motion.busy : undefined}
        >
          <Zap size={12} />
          {generating ? "Generating…" : "Regenerate"}
        </Button>
      </div>

      <div className="space-y-2">
        {visibleActions.map((action, idx) => {
          const isAssigned = handledItems.get(idx) === "assigned";
          return (
            <Panel
              key={`${action.title}-${idx}`}
              padding={false}
              className={`overflow-hidden ${
                isAssigned ? "opacity-70" : "hover:border-[color:var(--border-strong)]"
              } ${motion.micro} ${motion.loadIn} ${motion.staggerClass(idx % 4)}`}
            >
              <div className="flex items-stretch">
                <div className="flex min-w-0 flex-1 items-center gap-3 p-4">
                  <ScorePill score={action.priority_score} impact={action.estimated_impact} />
                  <div className="min-w-0 flex-1">
                    <div className="mb-0.5 flex flex-wrap items-center gap-2">
                      <Badge
                        className={categoryColors[action.category] || categoryColors.analytics}
                      >
                        {action.category.replace(/_/g, " ")}
                      </Badge>
                      <Badge tone={effortTone[action.effort] || "default"}>{action.effort}</Badge>
                    </div>
                    <p className="text-[13px] font-medium leading-snug text-ink">{action.title}</p>
                    {action.target_query && (
                      <p className="text-muted font-mono-data mt-0.5 truncate text-[11px]">
                        Query: &ldquo;{action.target_query}&rdquo;
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1 px-3">
                  {isAssigned ? (
                    <div className="flex items-center gap-2 px-2 text-[12px] font-medium text-kinexis-focus">
                      <span className="h-1.5 w-1.5 rounded-full bg-kinexis-focus" />
                      In Execute
                      <ExternalLink size={10} />
                    </div>
                  ) : (
                    <>
                      <Button
                        size="sm"
                        onClick={() => void createWorkItem(action, idx)}
                        disabled={creatingIdx === idx}
                        title={
                          cursorAvailable &&
                          assigneeForPlaybook(action.playbook_pattern) === "Cursor"
                            ? "Assign and open in editor"
                            : "Create work item"
                        }
                      >
                        <Plus size={12} />
                        {creatingIdx === idx ? "…" : "Assign"}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => skipWorkItem(action, idx)}
                        className="!text-muted hover:!bg-kinexis-risk/10"
                        title="Skip — won't reappear until regeneration"
                      >
                        <SkipForward size={12} />
                        Skip
                      </Button>
                    </>
                  )}
                </div>
              </div>

              <div className="border-t border-[color:var(--border-subtle)] px-4 pb-3">
                <CollapsibleSection label="plan details" defaultOpen={false} className="!mt-0">
                  <div className="space-y-3">
                    {action.target_url && (
                      <p className="font-mono-data text-[11px] text-kinexis-focus">
                        Page: {action.target_url}
                      </p>
                    )}
                    {action.why_it_matters && (
                      <p className="text-xs leading-relaxed text-ink-secondary">
                        {action.why_it_matters}
                      </p>
                    )}
                    {action.evidence && (
                      <p className="text-muted text-[11px] italic leading-relaxed">
                        Evidence: {action.evidence}
                      </p>
                    )}

                    {(action.current_state || action.proposed_changes) && (
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {action.current_state && (
                          <div>
                            <p className="text-label mb-2">Current on page</p>
                            <ul className="space-y-1">
                              {Object.entries(action.current_state).map(([k, v]) => (
                                <li
                                  key={k}
                                  className="text-[12px] leading-relaxed text-ink-secondary"
                                >
                                  <span className="text-muted font-mono-data">{k}:</span> {v}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {action.proposed_changes && (
                          <div>
                            <p className="text-label mb-2">Ship this copy</p>
                            <ul className="space-y-1">
                              {Object.entries(action.proposed_changes).map(([k, v]) => (
                                <li key={k} className="text-[12px] leading-relaxed text-ink">
                                  <span className="font-mono-data text-kinexis-focus">{k}:</span>{" "}
                                  {v}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}

                    {(action.steps || []).length > 0 && (
                      <div>
                        <p className="text-label mb-2">Execution steps</p>
                        <ol className="space-y-1">
                          {action.steps.map((step, si) => (
                            <li
                              key={si}
                              className="flex items-start gap-2 text-[12px] leading-relaxed text-ink-secondary"
                            >
                              <span className="text-muted font-mono-data mt-0.5 w-4 shrink-0 text-xs">
                                {String(si + 1).padStart(2, "0")}
                              </span>
                              {step}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}

                    <div className="flex flex-wrap gap-4">
                      {(action.metrics_to_watch || []).length > 0 && (
                        <div>
                          <p className="text-label mb-1">Success metrics</p>
                          <div className="flex flex-wrap gap-1">
                            {action.metrics_to_watch.map((m, mi) => (
                              <Badge key={mi} tone="default" className="!font-mono-data">
                                {m}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      <div>
                        <p className="text-label mb-1">Effort · Timeline</p>
                        <span className="text-muted flex items-center gap-1 text-xs">
                          <Clock size={10} /> {action.effort} · {action.expected_timeline}
                        </span>
                      </div>
                    </div>
                  </div>
                </CollapsibleSection>
              </div>
            </Panel>
          );
        })}

        {visibleActions.length === 0 && sorted.length > 0 && (
          <EmptyState
            title="All actions skipped"
            description="All plan items have been skipped. Regenerate to get a fresh plan."
            action={
              <Button variant="soft" size="sm" onClick={() => setConfirmRegen(true)}>
                Regenerate plan
              </Button>
            }
          />
        )}
      </div>

      <ConfirmDialog
        open={confirmRegen}
        title="Regenerate AI plan?"
        description="This replaces the current plan with a newly generated one. Skipped items will be reset."
        confirmLabel="Regenerate"
        danger
        busy={generating}
        onConfirm={() => void generatePlan(true)}
        onCancel={() => !generating && setConfirmRegen(false)}
      />
    </div>
  );
}

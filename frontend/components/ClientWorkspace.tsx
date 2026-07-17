"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import NextSteps from "@/components/NextSteps";
import ActionBoard from "@/components/ActionBoard";
import ActiveLeversView from "@/components/ActiveLeversView";
import ImpactView from "@/components/ImpactView";
import SuccessContractCard from "@/components/SuccessContractCard";
import ActiveTestsPanel from "@/components/ActiveTestsPanel";
import WorkBoard from "@/components/WorkBoard";
import ChartsView from "@/components/ChartsView";
import BriefsView from "@/components/BriefsView";
import ContentInventory from "@/components/ContentInventory";
import { Insight, Metric, Task, DataSource, api } from "@/lib/api";
import type { HealthImprovement } from "@/lib/metrics";

const GROWTH_PLAYBOOK_MAP: Record<string, string> = {
  "raise-visibility": "content_opportunity",
  "raise-ctr": "ctr_gap",
  "raise-cvr": "cro_opportunity",
  "raise-efficiency": "ads_spend_low_leads",
  "raise-technical": "pagespeed_improve",
  visibility: "content_opportunity",
  ctr: "ctr_gap",
  cvr: "cro_opportunity",
  efficiency: "ads_spend_low_leads",
  technical: "pagespeed_improve",
};
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { LoadingState } from "@/components/ui/LoadingState";
import { Badge } from "@/components/ui/Badge";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { CheckCircle2, Trash2, ChevronDown, ArrowRight } from "lucide-react";
import type { ShellTab, PrescribeSegment } from "@/hooks/useShellNavigation";
import type { DetectSegment, ExploreMode } from "@/hooks/useShellNavigation";
import { STAGE_BLURB } from "@/lib/glossary";
import ConfirmDialog from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type DigDeeperPanel =
  | null
  | "charts"
  | "funnel"
  | "levers"
  | "rankings"
  | "opportunities"
  | "inventory"
  | "campaigns"
  | "learning";

const overviewFallback = <LoadingState label="Loading overview" variant="overview" />;
const reportFallback = <LoadingState label="Loading report library..." variant="cards" />;
const funnelFallback = <LoadingState label="Loading funnel..." variant="cards" />;

const OverviewView = dynamic(() => import("@/components/OverviewView"), {
  loading: () => overviewFallback,
  ssr: false,
});
const ReportView = dynamic(() => import("@/components/ReportView"), {
  loading: () => reportFallback,
  ssr: false,
});
const FunnelView = dynamic(() => import("@/components/FunnelView"), {
  loading: () => funnelFallback,
  ssr: false,
});
const RankingsView = dynamic(() => import("@/components/RankingsView"), {
  loading: () => funnelFallback,
  ssr: false,
});
const CampaignsView = dynamic(() => import("@/components/CampaignsView"), {
  loading: () => funnelFallback,
  ssr: false,
});
const LearningLoopView = dynamic(() => import("@/components/LearningLoopView"), {
  loading: () => funnelFallback,
  ssr: false,
});

type CausalVerdict = {
  verdict?: string;
  causal_evidence_label?: string;
  matched_control?: Record<string, unknown> | null;
  bootstrap_ci?: {
    ci_lower?: number | null;
    ci_upper?: number | null;
    median_effect?: number | null;
    ci_excludes_zero?: boolean;
    ci_level?: number;
  };
};

type ImpactPayload = {
  status: string;
  message?: string;
  outcome?: string;
  auto_outcome?: string;
  outcome_manual?: boolean;
  confidence?: string;
  evidence_label?: string;
  confidence_note?: string;
  caution_notes?: string[];
  checked_at?: string;
  metrics_improved?: number;
  metrics_declined?: number;
  avg_primary_metric_change?: number;
  primary_metric?: string;
  proof_copy?: string;
  window_days?: number;
  causal_verdict?: CausalVerdict | null;
  details?: {
    metric: string;
    before: number;
    after: number;
    change_pct: number | null;
    is_primary?: boolean;
  }[];
};

type Props = {
  activeTab: ShellTab;
  setActiveTab: (t: ShellTab) => void;
  selectedClientId: number;
  clientName?: string;
  clientIndustry?: string;
  siteRelaunchedAt?: string | null;
  metrics: Metric[];
  insights: Insight[];
  tasks: Task[];
  datasources: DataSource[];
  openIssues: number;
  insightById: Map<number, Insight>;
  doneTasks: Task[];
  assigneePresets: string[];
  scrollToFixes: () => void;
  onResolve: (insightId: number) => void;
  onBulkResolve?: (ids: number[]) => void | Promise<void>;
  onBulkAssign?: (insights: Insight[]) => void | Promise<void>;
  onQuickAssign: (insight: Insight) => void;
  onCreateTask: (insight: Insight) => void;
  onTaskCreated: (task: Task) => void;
  onUpdateTask: (taskId: number, data: Partial<Task>) => Promise<void>;
  onDeleteTask?: (taskId: number) => Promise<void>;
  onImpactOutcomeChange?: (taskId: number, outcome: string | null) => void;
  reportFocusGenerateKey?: number;
  onReportStatusChange?: (status: string) => void;
  detectSegment?: DetectSegment;
  setDetectSegment?: (s: DetectSegment) => void;
  exploreMode?: ExploreMode;
  setExploreMode?: (m: ExploreMode) => void;
  prescribeSegment?: PrescribeSegment;
  setPrescribeSegment?: (s: PrescribeSegment) => void;
};

function useImpactWindowDays(): number {
  const [days, setDays] = useState(14);
  useEffect(() => {
    let cancelled = false;
    api.settings
      .get()
      .then((s) => {
        if (!cancelled && s.impact_window_days) setDays(s.impact_window_days);
      })
      .catch((e) => {
        console.warn("Failed to load impact window setting", e);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return days;
}

function ProveImpactList({
  doneTasks,
  insightById,
  impactWindowDays,
  onOutcomeChange,
  onDeleteTask,
}: {
  doneTasks: Task[];
  insightById: Map<number, Insight>;
  impactWindowDays: number;
  onOutcomeChange?: (taskId: number, outcome: string | null) => void;
  onDeleteTask?: (taskId: number) => Promise<void>;
}) {
  const { success, error: toastError } = useToast();
  const [impacts, setImpacts] = useState<Record<string, ImpactPayload>>({});
  const [batchLoading, setBatchLoading] = useState(true);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState(false);
  const taskIdsKey = doneTasks.map((t) => t.id).join(",");

  useEffect(() => {
    let cancelled = false;
    const ids = taskIdsKey
      ? taskIdsKey
          .split(",")
          .map((id) => Number(id))
          .filter((n) => Number.isFinite(n))
      : [];
    if (ids.length === 0) {
      setImpacts({});
      setBatchError(null);
      setBatchLoading(false);
      return;
    }
    setBatchLoading(true);
    setBatchError(null);
    void api.actions
      .getImpactBatch(ids)
      .then((data) => {
        if (!cancelled) setImpacts(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setImpacts({});
          setBatchError(e instanceof Error ? e.message : "Failed to load impact batch");
        }
      })
      .finally(() => {
        if (!cancelled) setBatchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [taskIdsKey]);

  const handleDelete = async () => {
    if (!deleteTarget || !onDeleteTask) return;
    setDeleting(true);
    try {
      await onDeleteTask(deleteTarget.id);
      success("Work item deleted");
      setDeleteTarget(null);
    } catch {
      toastError("Failed to delete");
    } finally {
      setDeleting(false);
    }
  };

  const cumulative = useMemo(() => {
    const vals = Object.values(impacts).filter((i) => i.status === "complete");
    const wins = vals.filter((i) => i.outcome === "win").length;
    const losses = vals.filter((i) => i.outcome === "loss").length;
    const flats = vals.filter((i) => i.outcome === "flat").length;
    const totalImproved = vals.reduce((sum, i) => sum + (i.metrics_improved || 0), 0);
    const totalDeclined = vals.reduce((sum, i) => sum + (i.metrics_declined || 0), 0);
    const avgLift =
      vals.length > 0
        ? vals.reduce((sum, i) => sum + (i.avg_primary_metric_change || 0), 0) / vals.length
        : null;
    return {
      complete: vals.length,
      pending: Object.keys(impacts).length - vals.length,
      wins,
      losses,
      flats,
      totalImproved,
      totalDeclined,
      avgLift,
    };
  }, [impacts]);

  if (batchLoading && Object.keys(impacts).length === 0) {
    return <LoadingState label="Loading impact..." variant="cards" />;
  }

  return (
    <div className="animate-state-settle">
      {cumulative.complete > 0 && (
        <div className="mb-5 flex flex-wrap items-end gap-x-6 gap-y-2 border-b border-[color:var(--border-subtle)] pb-4">
          <div>
            <p className="text-muted text-[11px] font-medium">Win rate</p>
            <p className="font-mono-data text-[28px] font-semibold tabular-nums text-ink">
              {cumulative.complete > 0
                ? Math.round((cumulative.wins / cumulative.complete) * 100)
                : 0}
              %
            </p>
          </div>
          <div>
            <p className="text-muted text-[11px] font-medium">Wins / losses</p>
            <p className="font-mono-data text-[20px] font-semibold tabular-nums">
              <span className="text-kinexis-proof">{cumulative.wins}</span>
              <span className="text-muted"> / </span>
              <span className="text-kinexis-risk">{cumulative.losses}</span>
            </p>
          </div>
          <div>
            <p className="text-muted text-[11px] font-medium">Avg lift</p>
            <p
              className={`font-mono-data text-[20px] font-semibold tabular-nums ${
                (cumulative.avgLift ?? 0) > 0
                  ? "text-kinexis-proof"
                  : (cumulative.avgLift ?? 0) < 0
                    ? "text-kinexis-risk"
                    : "text-ink"
              }`}
            >
              {cumulative.avgLift != null
                ? `${cumulative.avgLift > 0 ? "+" : ""}${cumulative.avgLift.toFixed(1)}%`
                : "\u2014"}
            </p>
          </div>
          <p className="text-muted ml-auto text-[11px]">{cumulative.complete} proven</p>
        </div>
      )}
      {batchError && Object.keys(impacts).length === 0 && (
        <div
          className="mb-4 border border-kinexis-risk/20 bg-kinexis-risk/10 px-3 py-2 text-xs text-kinexis-risk"
          style={{ borderRadius: "var(--radius-md)" }}
        >
          {batchError}
        </div>
      )}
      <div className="divide-y divide-[color:var(--border-subtle)]">
        {doneTasks.map((task) => {
          const linked = insightById.get(task.insight_id ?? -1);
          const impact = impacts[String(task.id)];
          const outcome = impact?.outcome || task.impact_outcome;
          const title =
            linked?.recommended_action ||
            linked?.message ||
            (task.result_notes ? task.result_notes.slice(0, 100) : null) ||
            "Completed work";
          const verdictTone =
            outcome === "win"
              ? "text-kinexis-proof"
              : outcome === "loss"
                ? "text-kinexis-risk"
                : outcome === "flat"
                  ? "text-kinexis-signal"
                  : "text-muted";
          return (
            <div key={task.id} className="queue-row !px-0 py-4">
              <div className="min-w-0 flex-1 space-y-3">
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <CheckCircle2 size={15} className="shrink-0 text-kinexis-proof" />
                    <span className="truncate text-sm font-semibold text-ink">{title}</span>
                    {outcome && (
                      <span
                        className={`text-[11px] font-bold uppercase tracking-wide ${verdictTone}`}
                      >
                        {outcome}
                      </span>
                    )}
                  </div>
                  {onDeleteTask && (
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(task)}
                      className="icon-btn text-muted shrink-0 hover:!text-kinexis-risk"
                      title="Delete work item"
                      aria-label="Delete work item"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
                <ImpactView
                  taskId={task.id}
                  taskStatus={task.status}
                  initialData={impact}
                  skipInitialFetch={Boolean(impact)}
                  impactWindowDays={impactWindowDays}
                  onOutcomeChange={onOutcomeChange}
                />
              </div>
            </div>
          );
        })}
      </div>
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete work item"
          description={
            deleteTarget
              ? `Permanently remove this completed win? Impact data will also be lost.`
              : ""
          }
        confirmLabel={deleting ? "Deleting..." : "Delete"}
        danger
        busy={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />
    </div>
  );
}

function EvidenceRail({
  active,
  onChange,
}: {
  active: DigDeeperPanel;
  onChange: (p: DigDeeperPanel) => void;
}) {
  const items: { id: Exclude<DigDeeperPanel, null>; label: string }[] = [
    { id: "charts", label: "Charts" },
    { id: "funnel", label: "Funnel" },
    { id: "levers", label: "Levers" },
    { id: "campaigns", label: "Campaigns" },
    { id: "rankings", label: "Rankings" },
    { id: "opportunities", label: "Opportunities" },
    { id: "learning", label: "Learning" },
    { id: "inventory", label: "Inventory" },
  ];
  return (
    <div className="mt-8 border-t border-[color:var(--border-subtle)] pt-5">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="section-label text-muted text-[11px] font-semibold tracking-wide">Evidence</p>
        <p className="text-muted text-[11px]">Open only what you need to brief the next move</p>
      </div>
      <div className="evidence-rail">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => onChange(active === item.id ? null : item.id)}
            className={`evidence-chip ${active === item.id ? "evidence-chip-active" : ""}`}
          >
            {item.label}
            <ChevronDown
              size={11}
              className={`transition-transform ${active === item.id ? "rotate-180" : ""}`}
            />
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ClientWorkspace({
  activeTab,
  setActiveTab,
  selectedClientId,
  clientName,
  clientIndustry,
  metrics,
  insights,
  tasks,
  datasources,
  insightById,
  doneTasks,
  assigneePresets,
  scrollToFixes,
  onResolve,
  onBulkResolve,
  onBulkAssign,
  onQuickAssign,
  onCreateTask,
  onTaskCreated,
  onUpdateTask,
  onDeleteTask,
  onImpactOutcomeChange,
  reportFocusGenerateKey = 0,
  onReportStatusChange,
  exploreMode = "rankings",
  prescribeSegment: prescribeSegmentProp,
  setPrescribeSegment: setPrescribeSegmentProp,
  siteRelaunchedAt,
}: Props) {
  const { success, error: toastError } = useToast();
  const impactWindowDays = useImpactWindowDays();

  const overdueTasksCount = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return tasks.filter(
      (t) =>
        t.status !== "done" && t.status !== "skipped" && t.due_date && new Date(t.due_date) < today
    ).length;
  }, [tasks]);

  const [exploreDays, setExploreDays] = useState(30);
  const [digDeeper, setDigDeeper] = useState<DigDeeperPanel>(null);
  const [showAiPlan, setShowAiPlan] = useState(false);
  const [showBriefs, setShowBriefs] = useState(false);
  const [localPrescribe, setLocalPrescribe] = useState<PrescribeSegment>("fixes");
  const prescribeSegment = prescribeSegmentProp ?? localPrescribe;
  const setPrescribeSegment = setPrescribeSegmentProp ?? setLocalPrescribe;

  // Open Dig deeper when legacy explore/charts deep links arrive
  useEffect(() => {
    if (activeTab === "charts") {
      setDigDeeper("charts");
      setActiveTab("detect");
      return;
    }
    if (activeTab === "detect" && exploreMode && digDeeper === null) {
      // Only auto-open when URL carried dig/explore intent via exploreMode from rankings/opps
      if (exploreMode === "opportunities" || exploreMode === "inventory") {
        setDigDeeper(exploreMode);
      }
    }
  }, [activeTab, exploreMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Prescribe: open panels from legacy segment deep links
  useEffect(() => {
    if (activeTab !== "prescribe") return;
    if (prescribeSegment === "ai_plan") setShowAiPlan(true);
    if (prescribeSegment === "briefs") setShowBriefs(true);
  }, [activeTab, prescribeSegment]);

  const staleDays = useMemo(() => {
    const synced = datasources.map((d) => d.last_synced_at).filter((t): t is string => Boolean(t));
    if (!synced.length) return 999;
    const latest = new Date(Math.max(...synced.map((s) => new Date(s).getTime())));
    const diff = Date.now() - latest.getTime();
    return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
  }, [datasources]);

  const daysSinceRelaunch = useMemo(() => {
    if (!siteRelaunchedAt) return null;
    const relaunch = new Date(siteRelaunchedAt);
    const diff = Date.now() - relaunch.getTime();
    return Math.max(0, Math.floor(diff / (1000 * 60 * 60 * 24)));
  }, [siteRelaunchedAt]);

  const createGrowthTask = async (play: HealthImprovement) => {
    try {
      const notes = [
        play.detail,
        "",
        "Steps:",
        ...play.steps.map((s, i) => `${i + 1}. ${s}`),
        "",
        `Success metric: ${play.metric}`,
        `Est. ROI: ${play.estimatedROI}`,
      ].join("\n");
      const task = await api.tasks.create({
        client_id: selectedClientId,
        result_notes: `${play.title}\n\n${notes}`,
        playbook_pattern:
          GROWTH_PLAYBOOK_MAP[play.id] ||
          GROWTH_PLAYBOOK_MAP[play.id.replace(/^raise-/, "")] ||
          "content_opportunity",
      });
      onTaskCreated(task);
      setActiveTab("execute");
      success(`Created task: ${play.title}`);
    } catch {
      toastError("Couldn't create growth task");
    }
  };

  /** Detect never creates work — always land on Prescribe Fix queue. */
  const openFixQueue = () => {
    setPrescribeSegment("fixes");
    scrollToFixes();
  };

  const digDeeperContent = () => {
    if (digDeeper === "charts") {
      return <ChartsView metrics={metrics} clientId={selectedClientId} />;
    }
    if (digDeeper === "funnel") {
      return <FunnelView clientId={selectedClientId} onPrescribeLeak={() => openFixQueue()} />;
    }
    if (digDeeper === "levers") {
      return (
        <ActiveLeversView
          clientId={selectedClientId}
          onPrescribe={() => openFixQueue()}
          onAssign={() => openFixQueue()}
          onComplete={() => setActiveTab("execute")}
          onProve={() => setActiveTab("prove")}
          onReport={() => setActiveTab("report")}
        />
      );
    }
    if (digDeeper === "inventory") return <ContentInventory metrics={metrics} />;
    if (digDeeper === "campaigns") {
      return <CampaignsView clientId={selectedClientId} onPrescribe={() => openFixQueue()} />;
    }
    if (digDeeper === "learning") {
      return <LearningLoopView clientId={selectedClientId} />;
    }
    if (digDeeper === "rankings") {
      return (
        <RankingsView
          clientId={selectedClientId}
          days={exploreDays}
          onDaysChange={setExploreDays}
        />
      );
    }
    if (digDeeper === "opportunities") {
      const openOpps = insights.filter((i) => !i.resolved && i.kind === "opportunity");
      const byType: Record<string, number> = {};
      for (const i of openOpps) byType[i.type] = (byType[i.type] || 0) + 1;
      return (
        <Panel padding="lg">
          <p className="mb-3 text-sm font-semibold text-ink">Growth opportunities detected</p>
          {openOpps.length === 0 ? (
            <p className="text-muted text-sm">
              No open opportunities. Sync data to generate insights.
            </p>
          ) : (
            <>
              <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Object.entries(byType)
                  .slice(0, 9)
                  .map(([type, count]) => (
                    <div
                      key={type}
                      className="flex items-center justify-between rounded-md border border-[color:var(--border-subtle)] bg-surface-lighter/40 p-3"
                    >
                      <span className="truncate text-xs text-ink-secondary">
                        {type.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs font-semibold text-kinexis-proof">{count}</span>
                    </div>
                  ))}
              </div>
              <Button variant="soft" size="sm" onClick={openFixQueue}>
                Open Fix queue
              </Button>
            </>
          )}
        </Panel>
      );
    }
    return null;
  };

  return (
    <>
      {(activeTab === "detect" || activeTab === "charts") && (
        <div className="animate-fade-up">
          <OverviewView
            metrics={metrics}
            insights={insights}
            clientId={selectedClientId}
            clientName={clientName}
            industry={clientIndustry}
            overdueTasks={overdueTasksCount}
            staleDays={staleDays === 999 ? null : staleDays}
            daysSinceRelaunch={daysSinceRelaunch}
            onStartFix={openFixQueue}
            onOpenFunnel={() => setDigDeeper("funnel")}
          />
          <EvidenceRail active={digDeeper} onChange={setDigDeeper} />
          {digDeeper && <div className="animate-fade-up mt-4">{digDeeperContent()}</div>}
        </div>
      )}

      {activeTab === "prescribe" && (
        <div className="animate-fade-up space-y-5">
          <div className="mission-hero !mb-2">
            <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
              Prescribe
            </p>
            <h2 className="text-display text-[24px] leading-tight sm:text-[28px]">Fix queue</h2>
            <p className="text-muted mt-2 max-w-xl text-[13px] leading-relaxed">
              {STAGE_BLURB.prescribe}
            </p>
          </div>
          <NextSteps
            id="fix-queue"
            insights={insights}
            clientId={selectedClientId}
            assigneePresets={assigneePresets}
            staleDays={staleDays === 999 ? null : staleDays}
            tasks={tasks}
            onResolve={onResolve}
            onBulkResolve={onBulkResolve}
            onBulkAssign={onBulkAssign}
            onQuickAssign={onQuickAssign}
            onCreateTask={onCreateTask}
            onOpenActions={() => {
              setShowAiPlan(true);
              setPrescribeSegment("ai_plan");
            }}
            onCreateGrowthTask={(play) => void createGrowthTask(play)}
          />
          <CollapsibleSection
            key={`ai-plan-${showAiPlan || prescribeSegment === "ai_plan"}`}
            label="AI Plan"
            defaultOpen={showAiPlan || prescribeSegment === "ai_plan"}
          >
            <ActionBoard
              clientId={selectedClientId}
              assigneePresets={assigneePresets}
              onTaskCreated={onTaskCreated}
              onGoToExecute={() => setActiveTab("execute")}
            />
          </CollapsibleSection>
          <CollapsibleSection
            key={`briefs-${showBriefs || prescribeSegment === "briefs"}`}
            label="Briefs"
            defaultOpen={showBriefs || prescribeSegment === "briefs"}
          >
            <BriefsView clientId={selectedClientId} insights={insights} />
          </CollapsibleSection>
        </div>
      )}

      {activeTab === "execute" && (
        <div className="animate-fade-up">
          <div className="mission-hero !mb-4">
            <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
              Execute
            </p>
            <h2 className="text-display text-[24px] leading-tight sm:text-[28px]">Work queue</h2>
            <p className="text-muted mt-2 max-w-xl text-[13px] leading-relaxed">
              {STAGE_BLURB.execute}
            </p>
          </div>
          <WorkBoard
            tasks={tasks}
            insightById={insightById}
            onUpdateTask={onUpdateTask}
            onDeleteTask={onDeleteTask}
            onGoToFixes={scrollToFixes}
            onGoToProve={() => setActiveTab("prove")}
            assigneePresets={assigneePresets}
          />
        </div>
      )}

      {activeTab === "prove" && (
        <div className="animate-fade-up space-y-4">
          <div className="mission-hero !mb-2 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
                Prove
              </p>
              <h2 className="text-display text-[24px] leading-tight sm:text-[28px]">
                Measured impact
              </h2>
              <p className="text-muted mt-2 max-w-xl text-[13px] leading-relaxed">
                {STAGE_BLURB.prove}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="signal">{impactWindowDays}+ day window</Badge>
              <Button variant="soft" size="sm" onClick={() => setActiveTab("report")}>
                Pack into Report
                <ArrowRight size={13} />
              </Button>
            </div>
          </div>
          {doneTasks.length === 0 ? (
            <EmptyState
              title="No completed work yet"
              description="Assign fixes from Prescribe, complete them in the Work queue, then measure here."
              action={
                <Button variant="soft" size="sm" onClick={scrollToFixes}>
                  Open Fix queue
                </Button>
              }
            />
          ) : (
            <ProveImpactList
              doneTasks={doneTasks}
              insightById={insightById}
              impactWindowDays={impactWindowDays}
              onOutcomeChange={onImpactOutcomeChange}
              onDeleteTask={onDeleteTask}
            />
          )}
          <CollapsibleSection label="Success contract & active tests" defaultOpen={false}>
            <SuccessContractCard clientId={selectedClientId} />
            <ActiveTestsPanel clientId={selectedClientId} />
          </CollapsibleSection>
        </div>
      )}

      {activeTab === "report" && (
        <div className="animate-fade-up">
          <ReportView
            clientId={selectedClientId}
            clientName={clientName}
            focusGenerateKey={reportFocusGenerateKey}
            onStatusChange={onReportStatusChange}
          />
        </div>
      )}
    </>
  );
}

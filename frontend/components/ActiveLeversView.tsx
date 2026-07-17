"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, TrendingUp, Zap, BarChart3 } from "lucide-react";
import { api, GrowthLever } from "@/lib/api";
import LeverThreadCard from "@/components/LeverThreadCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { useToast } from "@/components/Toast";

type Props = {
  clientId: number;
  onPrescribe: (lever: GrowthLever) => void;
  onAssign: (lever: GrowthLever) => void;
  onComplete: (lever: GrowthLever) => void;
  onProve: (lever: GrowthLever) => void;
  onReport: (lever: GrowthLever) => void;
};

export default function ActiveLeversView({
  clientId,
  onPrescribe,
  onAssign: _onAssign,
  onComplete,
  onProve,
  onReport,
}: Props) {
  const { success, error: toastError } = useToast();
  const [levers, setLevers] = useState<GrowthLever[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const rows = await api.levers.list(clientId, true);
      setLevers(rows);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load levers");
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    void load();
  }, [load]);

  const active = useMemo(() => levers.filter((l) => l.status !== "dismissed"), [levers]);

  const summary = useMemo(() => {
    const total = active.length;
    const byImpact = {
      high: active.filter((l) => (l.impact_score ?? 0) >= 70).length,
      medium: active.filter((l) => {
        const s = l.impact_score ?? 0;
        return s >= 40 && s < 70;
      }).length,
      low: active.filter((l) => (l.impact_score ?? 0) < 40 && (l.impact_score ?? 0) > 0).length,
      unknown: active.filter((l) => l.impact_score == null).length,
    };
    const byConfidence = {
      high: active.filter((l) => (l.confidence_label || "").toLowerCase().includes("high")).length,
      medium: active.filter((l) => (l.confidence_label || "").toLowerCase().includes("med")).length,
      low: active.filter((l) => (l.confidence_label || "").toLowerCase().includes("low")).length,
      unlabeled: active.filter((l) => !l.confidence_label).length,
    };
    const topImpact = active.reduce((max, l) => Math.max(max, l.impact_score ?? 0), 0);
    const avgImpact =
      total > 0 ? active.reduce((sum, l) => sum + (l.impact_score ?? 0), 0) / total : 0;
    return { total, byImpact, byConfidence, topImpact, avgImpact };
  }, [active]);

  const handleAction = async (lever: GrowthLever, action: string) => {
    // Dig-deeper Levers are read-only diagnosis — never create tasks here
    if (action === "open_fix_queue" || action === "prescribe" || action === "assign") {
      onPrescribe(lever);
      return;
    }
    if (action === "complete") {
      onComplete(lever);
      return;
    }
    if (action === "prove") {
      onProve(lever);
      return;
    }
    if (action === "report") {
      setBusyId(lever.id);
      try {
        await api.levers.setStatus(lever.id, {
          status: "proven",
          include_in_report: true,
        });
        success("Added to report pack");
        onReport(lever);
        await load();
      } catch (e) {
        toastError(e instanceof Error ? e.message : "Failed to add to report");
      } finally {
        setBusyId(null);
      }
      return;
    }
    if (action === "dismiss") {
      const previousStatus = lever.status;
      setBusyId(lever.id);
      try {
        await api.levers.setStatus(lever.id, { status: "dismissed" });
        success("Problem dismissed", {
          action: {
            label: "Undo",
            onClick: async () => {
              try {
                await api.levers.setStatus(lever.id, { status: previousStatus });
                success("Problem restored");
                await load();
              } catch {
                toastError("Failed to undo dismiss");
              }
            },
          },
        });
        await load();
      } catch (e) {
        toastError(e instanceof Error ? e.message : "Failed to dismiss");
      } finally {
        setBusyId(null);
      }
    }
  };

  if (loading) {
    return <LoadingState label="Loading levers…" variant="cards" />;
  }

  if (loadError) {
    return (
      <ErrorState title="Levers unavailable" description={loadError} onRetry={() => void load()} />
    );
  }

  return (
    <div className="animate-fade-up space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="section-label">Problems</h2>
          <p className="section-title mt-1">
            Impact-ranked open issues. Open Fix queue to Assign — work is created only there.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => void load()}>
          <RefreshCw size={12} />
          Refresh
        </Button>
      </div>

      {active.length > 0 && (
        <Panel className="overflow-hidden !p-0" padding={false}>
          <div className="grid grid-cols-2 gap-px bg-[color:var(--border-subtle)] sm:grid-cols-4">
            <div className="bg-surface px-4 py-3">
              <p className="text-muted text-[11px] font-medium">Total open</p>
              <p className="font-mono-data mt-0.5 text-[18px] font-semibold text-ink">
                {summary.total}
              </p>
            </div>
            <div className="bg-surface px-4 py-3">
              <p className="text-muted text-[11px] font-medium">Avg impact</p>
              <p className="font-mono-data mt-0.5 text-[18px] font-semibold text-ink">
                {summary.avgImpact > 0 ? Math.round(summary.avgImpact) : "—"}
              </p>
            </div>
            <div className="bg-surface px-4 py-3">
              <p className="text-muted text-[11px] font-medium">Highest</p>
              <p className="font-mono-data mt-0.5 text-[18px] font-semibold text-kinexis-proof">
                {summary.topImpact > 0 ? summary.topImpact : "—"}
              </p>
            </div>
            <div className="bg-surface px-4 py-3">
              <p className="text-muted text-[11px] font-medium">Confidence</p>
              <div className="mt-1 flex items-center gap-2">
                {summary.byConfidence.high > 0 && (
                  <Badge tone="proof" className="!px-2 !py-0.5 !text-xs">
                    {summary.byConfidence.high} high
                  </Badge>
                )}
                {summary.byConfidence.medium > 0 && (
                  <Badge tone="momentum" className="!px-2 !py-0.5 !text-xs">
                    {summary.byConfidence.medium} med
                  </Badge>
                )}
                {summary.byConfidence.low > 0 && (
                  <Badge tone="warning" className="!px-2 !py-0.5 !text-xs">
                    {summary.byConfidence.low} low
                  </Badge>
                )}
              </div>
            </div>
          </div>
          {active.length > 0 && (
            <div className="border-t border-[color:var(--border-subtle)] bg-surface-lighter/50 px-4 py-3">
              <div className="text-muted flex items-center gap-3 text-[12px]">
                <span className="flex items-center gap-1">
                  <Zap size={11} className="text-kinexis-proof" />
                  {summary.byImpact.high} high-impact
                </span>
                <span className="flex items-center gap-1">
                  <TrendingUp size={11} className="text-kinexis-signal" />
                  {summary.byImpact.medium} medium
                </span>
                <span className="flex items-center gap-1">
                  <BarChart3 size={11} />
                  {summary.byImpact.low + summary.byImpact.unknown} low/unscored
                </span>
              </div>
            </div>
          )}
        </Panel>
      )}

      {active.length === 0 ? (
        <EmptyState
          title="No problems detected yet"
          description="Sync client data so we can find the biggest growth levers from funnel leaks and ranked insights."
          action={
            <Button variant="soft" size="sm" onClick={() => void load()}>
              Find problems
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {active.map((lever) => (
            <LeverThreadCard
              key={lever.id}
              lever={lever}
              busy={busyId === lever.id}
              onAction={handleAction}
            />
          ))}
        </div>
      )}
    </div>
  );
}

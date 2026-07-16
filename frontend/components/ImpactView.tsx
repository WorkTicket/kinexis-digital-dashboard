"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { TrendingUp, TrendingDown, Minus, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { LoadingState } from "@/components/ui/LoadingState";
import { ErrorState } from "@/components/ui/ErrorState";
import { motion } from "@/lib/motion";

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

type ImpactData = {
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
  funnel_proof?: {
    metric: string;
    label: string;
    before: number;
    after: number;
    change_pct: number | null;
  }[];
  revenue_story?: string | null;
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
  taskId: number;
  taskStatus: string;
  /** Prefetched impact from batch endpoint — skips the per-card fetch. */
  initialData?: ImpactData | null;
  skipInitialFetch?: boolean;
  impactWindowDays?: number;
  onOutcomeChange?: (taskId: number, outcome: string | null) => void;
};

function metricLabel(metric: string) {
  return metric
    .replace("gsc.clicks", "Google visits")
    .replace("gsc.impressions", "Search appearances")
    .replace("gsc.ctr", "Click rate")
    .replace("ga4.sessions", "Website visits")
    .replace("ga4.key_events", "Conversions")
    .replace("hubspot.leads", "Leads")
    .replace("hubspot.opportunities", "Opportunities")
    .replace("hubspot.closed_won", "Deals won")
    .replace("hubspot.revenue", "Revenue")
    .replace("paid.clicks", "Paid clicks")
    .replace("paid.conversions", "Paid conversions")
    .replace("paid.conversion_value", "Paid value")
    .replace("paid.cost", "Paid spend")
    .replace("ads_csv.clicks", "Paid clicks")
    .replace("ads_csv.conversions", "Ad conversions")
    .replace("ads_csv.conversion_value", "Ad value")
    .replace("ads_csv.cost", "Ad spend")
    .replace("google_ads.clicks", "Google Ads clicks")
    .replace("google_ads.conversions", "Google Ads conversions")
    .replace("google_ads.conversion_value", "Google Ads value")
    .replace("google_ads.cost", "Google Ads spend")
    .replace("meta_ads.clicks", "Meta Ads clicks")
    .replace("meta_ads.conversions", "Meta Ads conversions")
    .replace("meta_ads.conversion_value", "Meta Ads value")
    .replace("meta_ads.cost", "Meta Ads spend");
}

function liftTone(pct: number | null | undefined): "proof" | "danger" | "default" {
  if (pct == null) return "default";
  if (pct > 0) return "proof";
  if (pct < 0) return "danger";
  return "default";
}

function formatChange(pct: number | null) {
  if (pct === null || pct === undefined) return null;
  const icon =
    pct > 0 ? <TrendingUp size={12} /> : pct < 0 ? <TrendingDown size={12} /> : <Minus size={12} />;
  return (
    <Badge tone={liftTone(pct)} className="!font-mono-data gap-0.5">
      {icon}
      {pct > 0 ? "+" : ""}
      {pct.toFixed(1)}%
    </Badge>
  );
}

function outcomeTone(outcome?: string): "proof" | "danger" | "default" {
  if (outcome === "win") return "proof";
  if (outcome === "loss") return "danger";
  return "default";
}

function causalVerdictPlainEnglish(cv: CausalVerdict): string {
  if (cv.verdict === "causal_win") {
    return "Causal check suggests a real lift — the confidence interval excludes zero.";
  }
  if (cv.verdict === "causal_loss") {
    return "Causal check suggests a real decline — the confidence interval excludes zero.";
  }
  if (cv.verdict === "inconclusive") {
    return "Causal check is inconclusive — the change could still be noise.";
  }
  return cv.causal_evidence_label || "Causal check ran, but the verdict is unclear.";
}

export default function ImpactView({
  taskId,
  taskStatus,
  initialData = null,
  skipInitialFetch = false,
  impactWindowDays: impactWindowDaysProp,
  onOutcomeChange,
}: Props) {
  const { error: toastError, success } = useToast();
  const [impact, setImpact] = useState<ImpactData | null>(initialData ?? null);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(!skipInitialFetch && !initialData);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [settingOutcome, setSettingOutcome] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadImpact = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setFetching(true);
    setFetchError(null);
    try {
      const data = await api.actions.getImpact(taskId, { signal: controller.signal });
      if (!controller.signal.aborted) setImpact(data);
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        if (!controller.signal.aborted) {
          setFetchError(e instanceof Error ? e.message : "Failed to load impact");
        }
      }
    } finally {
      if (!controller.signal.aborted) setFetching(false);
    }
  }, [taskId]);

  const runRecheck = async () => {
    setLoading(true);
    try {
      await api.actions.recheckImpact(taskId);
      await loadImpact();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Recheck failed");
    } finally {
      setLoading(false);
    }
  };

  const markOutcome = async (outcome: "win" | "loss" | "flat" | "auto") => {
    setSettingOutcome(true);
    try {
      const data = await api.actions.setImpactOutcome(taskId, outcome);
      setImpact((prev) => ({ ...(prev || { status: data.status }), ...data }));
      const nextOutcome =
        outcome === "auto" ? (data.outcome ?? data.auto_outcome ?? null) : outcome;
      onOutcomeChange?.(taskId, nextOutcome);
      success(outcome === "auto" ? "Using automatic outcome" : `Marked as ${outcome}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to set outcome");
    } finally {
      setSettingOutcome(false);
    }
  };

  useEffect(() => {
    if (initialData) {
      setImpact(initialData);
      setFetching(false);
    }
  }, [initialData]);

  useEffect(() => {
    if (taskStatus !== "done") return;
    if (skipInitialFetch) return;
    void loadImpact();
    return () => abortRef.current?.abort();
  }, [taskStatus, loadImpact, skipInitialFetch]);

  if (taskStatus !== "done") return null;

  if (fetching && !impact) {
    return (
      <Panel className="mt-2" padding="sm">
        <LoadingState label="Loading impact…" variant="spinner" />
      </Panel>
    );
  }

  if (fetchError && !impact) {
    return (
      <div className="mt-2">
        <ErrorState
          title="Impact unavailable"
          description={fetchError}
          onRetry={() => void loadImpact()}
          className="!py-6"
        />
      </div>
    );
  }

  const windowDays = impact?.window_days ?? impactWindowDaysProp ?? 14;

  if (!impact) {
    return (
      <Panel className="mt-2" padding="sm">
        <p className="text-muted text-xs leading-relaxed">
          Baseline captured. Recheck after the configured {windowDays}-day window (Settings →
          Impact), or run Recheck now if enough post-work data exists.
        </p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void runRecheck()}
          disabled={loading}
          className="mt-2 !text-kinexis-focus hover:!text-kinexis-focus/80"
        >
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          Recheck now
        </Button>
      </Panel>
    );
  }

  const waiting =
    impact.status === "pending" ||
    impact.status === "waiting" ||
    impact.status === "ready" ||
    impact.status === "too_early" ||
    Boolean(impact.message && /waiting|too early|baseline|Recheck/i.test(impact.message || ""));

  return (
    <Panel className="animate-fade-up animate-state-settle mt-2" padding="sm">
      <div className="mb-2.5 flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="section-label mb-0">Impact report</span>
          {impact.status === "complete" && impact.outcome && (
            <Badge tone={outcomeTone(impact.outcome)}>
              {impact.outcome}
              {impact.outcome_manual ? " (manual)" : ""}
            </Badge>
          )}
          {impact.status === "complete" && impact.confidence && (
            <span title={impact.confidence_note || "Sample-size evidence, not causal proof"}>
              <Badge tone="default">
                {impact.evidence_label || `${impact.confidence} evidence`}
              </Badge>
            </span>
          )}
          {waiting && impact.status !== "complete" && (
            <Badge tone="warning">
              {impact.status === "ready" ? "ready to recheck" : "waiting"}
            </Badge>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void runRecheck()}
          disabled={loading}
          className={`!text-kinexis-focus hover:!text-kinexis-focus/80${loading ? ` ${motion.busy}` : ""}`}
        >
          <RefreshCw size={10} className={loading ? "animate-spin" : ""} />
          Recheck
        </Button>
      </div>

      {impact.status === "no_data" || (waiting && !impact.details?.length) ? (
        <div className="space-y-2">
          <div
            className="inline-flex items-center gap-2 border border-kinexis-signal/30 px-2.5 py-1.5 text-[11px] text-kinexis-signal"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            Evidence timeline · {windowDays}+ days after completion
          </div>
          {impact.primary_metric && (
            <p className="text-[13px] font-semibold text-ink">
              Will prove against:{" "}
              <span className="text-kinexis-focus">{impact.primary_metric}</span>
              <span className="text-muted ml-1 text-[11px] font-normal">
                (Success Contract KPI when configured)
              </span>
            </p>
          )}
          <p className="text-muted text-xs leading-relaxed">
            {impact.message ||
              `Baseline is set. Come back after ~${windowDays} days of post-work data, then recheck.`}
          </p>
        </div>
      ) : (
        <>
          {impact.avg_primary_metric_change !== undefined && (
            <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <Badge
                tone={liftTone(impact.avg_primary_metric_change)}
                className="!text-metric !px-2 !py-1 !text-lg !font-normal"
              >
                {(impact.avg_primary_metric_change || 0) >= 0 ? "+" : ""}
                {impact.avg_primary_metric_change}%
              </Badge>
              <span className="text-muted text-xs">
                {impact.primary_metric
                  ? `contract/primary · ${impact.primary_metric}`
                  : "avg. primary change"}
              </span>
              <Badge tone="brand">{impact.metrics_improved} improved</Badge>
              <Badge tone="danger">{impact.metrics_declined} declined</Badge>
            </div>
          )}

          {impact.proof_copy && (
            <p
              className="text-muted mb-3 border border-[color:var(--border-subtle)] px-3 py-2 text-xs leading-relaxed"
              style={{ borderRadius: "var(--radius-md)" }}
            >
              {impact.proof_copy}
            </p>
          )}
          {impact.revenue_story && (
            <p className="mb-3 text-xs font-medium text-kinexis-proof">{impact.revenue_story}</p>
          )}
          {impact.funnel_proof && impact.funnel_proof.length > 0 && (
            <div className="mb-3">
              <p className="text-label mb-2">Organic → revenue funnel</p>
              <div className="metric-grid grid-cols-2 sm:grid-cols-4">
                {impact.funnel_proof.map((step) => (
                  <div key={step.metric} className="metric-tile min-w-0 !p-3">
                    <p className="text-label truncate">{step.label}</p>
                    <p className="font-mono-data mt-1 text-[13px] text-ink">
                      {step.after?.toLocaleString?.() ?? step.after}
                    </p>
                    {step.change_pct != null && (
                      <p
                        className={`font-mono-data mt-0.5 text-[11px] ${
                          step.change_pct >= 0 ? "text-kinexis-proof" : "text-kinexis-risk"
                        }`}
                      >
                        {step.change_pct > 0 ? "+" : ""}
                        {step.change_pct}%
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {impact.confidence_note && (
            <p className="text-muted mb-2 text-xs leading-relaxed">{impact.confidence_note}</p>
          )}
          {impact.causal_verdict && (
            <div
              className="mb-3 space-y-1 border border-[color:var(--border-subtle)] px-3 py-2.5"
              style={{ borderRadius: "var(--radius-md)" }}
            >
              <p className="text-label">Causal verdict</p>
              <p className="text-sm leading-relaxed text-ink">
                {causalVerdictPlainEnglish(impact.causal_verdict)}
              </p>
              {impact.causal_verdict.causal_evidence_label && (
                <p className="text-muted text-xs leading-relaxed">
                  {impact.causal_verdict.causal_evidence_label}
                  {impact.causal_verdict.matched_control ? " · matched control used" : ""}
                </p>
              )}
              {impact.causal_verdict.bootstrap_ci?.median_effect != null && (
                <p className="font-mono-data text-xs text-ink-secondary">
                  Median effect {impact.causal_verdict.bootstrap_ci.median_effect > 0 ? "+" : ""}
                  {impact.causal_verdict.bootstrap_ci.median_effect}
                  {impact.causal_verdict.bootstrap_ci.ci_lower != null &&
                  impact.causal_verdict.bootstrap_ci.ci_upper != null
                    ? ` · CI [${impact.causal_verdict.bootstrap_ci.ci_lower}, ${impact.causal_verdict.bootstrap_ci.ci_upper}]`
                    : ""}
                </p>
              )}
            </div>
          )}
          {impact.caution_notes && impact.caution_notes.length > 0 && (
            <ul className="mb-3 space-y-1">
              {impact.caution_notes.map((note) => (
                <li key={note} className="text-[11px] leading-relaxed text-kinexis-signal/90">
                  {note}
                </li>
              ))}
            </ul>
          )}

          {impact.message && impact.status !== "complete" && (
            <p className="text-muted mb-2 text-xs leading-relaxed">{impact.message}</p>
          )}

          {impact.details && (
            <div className="space-y-2">
              {impact.details.slice(0, 8).map((d, i) => (
                <div
                  key={i}
                  className="border border-[color:var(--border-subtle)] px-3 py-2.5"
                  style={{ borderRadius: "var(--radius-md)" }}
                >
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="truncate text-[11px] font-medium text-ink-secondary">
                      {metricLabel(d.metric)}
                      {d.is_primary ? (
                        <Badge tone="brand" className="ml-1.5 !px-1 !py-0 !text-xs">
                          primary
                        </Badge>
                      ) : null}
                    </span>
                    {formatChange(d.change_pct)}
                  </div>
                  <div className="grid min-w-0 grid-cols-1 items-end gap-2 min-[380px]:grid-cols-[1fr_auto_1fr]">
                    <div>
                      <p className="text-muted mb-0.5 text-[11px] font-semibold">Before</p>
                      <p className="font-mono-data text-sm text-ink-secondary">
                        {d.before?.toLocaleString?.() ?? d.before ?? "—"}
                      </p>
                    </div>
                    <span className="text-muted pb-0.5 text-xs" aria-hidden>
                      →
                    </span>
                    <div className="text-right">
                      <p className="text-muted mb-0.5 text-[11px] font-semibold">After</p>
                      <p className="font-mono-data text-sm text-ink">
                        {d.after?.toLocaleString?.() ?? d.after}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {(impact.status === "complete" || Boolean(impact.details?.length)) && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-[color:var(--border-subtle)] pt-2.5">
              <span className="text-muted mr-1 text-xs">Mark:</span>
              {(["win", "loss", "flat"] as const).map((o) => (
                <Button
                  key={o}
                  variant={impact.outcome === o && impact.outcome_manual ? "soft" : "ghost"}
                  size="sm"
                  disabled={settingOutcome}
                  onClick={() => void markOutcome(o)}
                  className={
                    impact.outcome === o && impact.outcome_manual
                      ? "!border-kinexis-focus/40"
                      : undefined
                  }
                >
                  {o}
                </Button>
              ))}
              {impact.outcome_manual && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={settingOutcome}
                  onClick={() => void markOutcome("auto")}
                >
                  Use auto
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

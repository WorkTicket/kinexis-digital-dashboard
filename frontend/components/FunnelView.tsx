"use client";

import { useCallback, useState, useEffect, useRef } from "react";
import { ArrowDown } from "lucide-react";
import { api, FunnelReport } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Button } from "@/components/ui/Button";
import { Stat } from "@/components/ui/Stat";
import { Panel } from "@/components/ui/Panel";
import { CHART } from "@/lib/chartTheme";

type Props = {
  clientId: number;
  onSync?: () => void;
  /** Turn a leak into work in Prescribe / Execute */
  onPrescribeLeak?: (leak: { stage: string; cause: string; fix: string; leak_pct: number }) => void;
};

export default function FunnelView({ clientId, onSync, onPrescribeLeak }: Props) {
  const [funnel, setFunnel] = useState<FunnelReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    api.actions
      .getFunnel(clientId, { signal: controller.signal })
      .then((d) => {
        if (!controller.signal.aborted) setFunnel(d);
      })
      .catch((e) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        console.warn(e);
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Failed to load funnel");
          setFunnel(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [clientId]);

  useEffect(() => {
    const cleanup = load();
    return cleanup;
  }, [load]);

  if (loading) {
    return <LoadingState label="Loading funnel…" variant="cards" className="animate-fade-up" />;
  }

  if (error) {
    return (
      <ErrorState
        title="Funnel unavailable"
        description={error}
        onRetry={() => load()}
        className="animate-fade-up"
      />
    );
  }

  const totals = funnel?.totals;
  const hasAny =
    Boolean(totals) &&
    ((totals!.impressions || 0) > 0 ||
      (totals!.leads || 0) > 0 ||
      (totals!.paid_impressions || 0) > 0 ||
      (totals!.revenue || 0) > 0);

  if (!hasAny || !funnel || !totals) {
    return (
      <EmptyState
        className="animate-fade-up"
        title="No funnel data yet"
        description="Sync GSC/GA4 for organic, add Ads CSV for paid, and HubSpot for leads → revenue."
        action={
          <Button
            variant="soft"
            onClick={
              onSync ??
              (() => {
                void api.metrics
                  .sync(clientId)
                  .then(() => load())
                  .catch(console.error);
              })
            }
          >
            Sync data now
          </Button>
        }
      />
    );
  }

  const leaks = funnel.leaks ?? [];
  const rates = funnel.rates ?? ({} as FunnelReport["rates"]);

  const stageConfigs: { label: string; value: number; color: string }[] = [
    { label: "Impressions", value: totals.impressions || 0, color: CHART.focusSoft },
    { label: "Clicks", value: totals.clicks || 0, color: CHART.focus },
    { label: "Sessions", value: totals.sessions || 0, color: CHART.momentum },
    { label: "Web conversions", value: totals.conversions || 0, color: CHART.proof },
  ];
  if (funnel.has_crm || (totals.leads || 0) > 0) {
    stageConfigs.push({
      label: "Leads",
      value: totals.leads || 0,
      color: CHART.proof,
    });
  }
  if (funnel.has_crm || (totals.revenue || 0) > 0 || (totals.closed_won || 0) > 0) {
    stageConfigs.push({
      label: "Revenue",
      value: Math.round(totals.revenue || 0),
      color: CHART.signal,
    });
  }

  const maxVal = Math.max(...stageConfigs.map((s) => s.value), 1);
  const barWidth = (val: number) => Math.max((val / maxVal) * 100, 2);

  return (
    <div className="animate-fade-up">
      <div className="mb-5">
        <h2 className="section-label">Funnel diagnosis</h2>
        <p className="section-title">
          Full acquisition-to-revenue pipeline — stage-by-stage conversion rates, biggest leaks, and
          exactly what to fix at each drop-off.
        </p>
        {(funnel.has_paid || funnel.has_crm) && (
          <p className="text-muted mt-1.5 text-xs">
            {funnel.has_paid && (
              <span>
                Paid spend ${Math.round(totals.ad_cost || 0).toLocaleString()}
                {(totals.paid_clicks || 0) > 0 &&
                  ` · ${totals.paid_clicks!.toLocaleString()} paid clicks`}
              </span>
            )}
            {funnel.has_paid && funnel.has_crm && <span> · </span>}
            {funnel.has_crm && (
              <span>
                {(totals.leads || 0).toLocaleString()} leads
                {(totals.revenue || 0) > 0 &&
                  ` · $${Math.round(totals.revenue!).toLocaleString()} revenue`}
              </span>
            )}
          </p>
        )}
      </div>

      {totals.leads || totals.revenue ? (
        <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat
            label="Cost per lead"
            value={
              (totals.leads || 0) > 0 && totals.ad_cost
                ? `$${Math.round(totals.ad_cost / totals.leads!).toLocaleString()}`
                : "—"
            }
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
          <Stat
            label="Cost per click"
            value={
              (totals.paid_clicks || 0) > 0 && totals.ad_cost
                ? `$${(totals.ad_cost / totals.paid_clicks!).toFixed(2)}`
                : "—"
            }
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
          <Stat
            label="ROAS"
            value={
              totals.ad_cost && (totals.revenue || 0) > 0
                ? `${(totals.revenue! / totals.ad_cost!).toFixed(1)}x`
                : "—"
            }
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
          <Stat
            label="Rev / session"
            value={
              (totals.sessions || 0) > 0 && (totals.revenue || 0) > 0
                ? `$${(totals.revenue! / totals.sessions!).toFixed(2)}`
                : "—"
            }
            className="!min-w-0 !p-3 [&_.text-metric]:!mt-1 [&_.text-metric]:!text-[0.95rem]"
          />
        </div>
      ) : null}

      <Panel className="mb-4" padding="lg">
        <div className="space-y-5">
          {stageConfigs.map((stage, idx) => (
            <div key={stage.label}>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-muted text-[12px] font-medium">{stage.label}</span>
                <span
                  className="font-mono-data text-[13px] font-medium"
                  style={{ color: stage.color }}
                >
                  {stage.label === "Revenue"
                    ? `$${stage.value.toLocaleString()}`
                    : stage.value.toLocaleString()}
                </span>
              </div>
              <div className="progress-track !h-1.5">
                <div
                  className="progress-fill motion-bar"
                  style={{
                    width: `${barWidth(stage.value)}%`,
                    backgroundColor: stage.color,
                  }}
                />
              </div>
              {idx < stageConfigs.length - 1 &&
                (() => {
                  const next = stageConfigs[idx + 1];
                  if (!next) return null;
                  const crossSource = stage.label === "Clicks" && next.label === "Sessions";
                  const revenueStage = stage.label === "Revenue" || next.label === "Revenue";
                  const convert =
                    !revenueStage && stage.value > 0 ? (next.value / stage.value) * 100 : null;
                  const unreliable = convert != null && crossSource && next.value > stage.value;
                  const shown = convert == null ? null : unreliable ? null : Math.min(convert, 100);
                  const drop = shown != null ? Math.max(0, 100 - shown) : null;
                  return (
                    <div className="my-1 flex justify-center">
                      <div className="text-muted font-mono-data flex items-center gap-1 text-xs">
                        <ArrowDown size={10} />
                        <span>
                          {unreliable
                            ? "cross-source — not a CVR"
                            : shown != null
                              ? `${shown.toFixed(1)}% convert`
                              : "—"}
                          {" · "}
                          {drop != null ? `${drop.toFixed(1)}% drop` : "—"}
                        </span>
                      </div>
                    </div>
                  );
                })()}
            </div>
          ))}
        </div>
      </Panel>

      {leaks.length > 0 && (
        <div className="space-y-2">
          <h3 className="section-label mb-1">Biggest leaks — what to fix</h3>
          <p className="text-muted mb-3 text-xs leading-relaxed">
            Work top-down. The largest drop is usually the highest-ROI fix.
          </p>
          {leaks.map((leak, idx) => (
            <Panel key={idx} padding="md">
              <div className="flex items-start gap-3">
                <div
                  className="font-mono-data flex h-6 w-6 shrink-0 items-center justify-center border border-kinexis-risk/30 text-[11px] font-medium text-kinexis-risk"
                  style={{ borderRadius: "var(--radius-sm)" }}
                >
                  {String(idx + 1).padStart(2, "0")}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-ink">{leak.stage}</p>
                  <p className="font-mono-data mt-0.5 text-xs text-kinexis-risk">
                    {leak.leak_pct}% lost
                    {leak.lost_clicks
                      ? ` · ${leak.lost_clicks.toLocaleString()} potential clicks`
                      : ""}
                    {leak.lost_sessions
                      ? ` · ${leak.lost_sessions.toLocaleString()} potential sessions`
                      : ""}
                    {leak.lost_conversions
                      ? ` · ${leak.lost_conversions.toLocaleString()} potential conversions`
                      : ""}
                  </p>
                  <p className="text-muted mt-2 text-xs leading-relaxed">
                    <span className="text-muted">Why: </span>
                    {leak.cause}
                  </p>
                  <div
                    className="mt-2.5 border border-[color:var(--border-subtle)] px-3 py-3"
                    style={{ borderRadius: "var(--radius-md)" }}
                  >
                    <p className="text-label mb-1 text-kinexis-focus">Do this</p>
                    <p className="text-xs leading-relaxed text-ink">{leak.fix}</p>
                    {onPrescribeLeak && leak.fix && (
                      <Button
                        variant="soft"
                        size="sm"
                        className="mt-2"
                        onClick={() =>
                          onPrescribeLeak({
                            stage: leak.stage,
                            cause: leak.cause || "",
                            fix: leak.fix || "",
                            leak_pct: leak.leak_pct,
                          })
                        }
                      >
                        Open Fix queue
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          ))}
        </div>
      )}

      {(rates.overall_conversion_pct ?? 0) > 0 && (
        <Panel className="mt-4 flex items-center justify-between" padding="md">
          <span className="text-muted text-xs">Overall · impression → conversion</span>
          <span className="text-metric text-lg text-kinexis-focus">
            {(rates.overall_conversion_pct ?? 0).toFixed(2)}%
          </span>
        </Panel>
      )}
    </div>
  );
}

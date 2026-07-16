"use client";

import AnalystNotes, { parseNarrative, isNarrativeSpam } from "@/components/AnalystNotes";
import { Panel } from "@/components/ui/Panel";
import { ReportCover } from "@/components/report/ReportCover";
import { ReportLoopNarrative } from "@/components/report/ReportLoopNarrative";
import { fmtChange, changeToneClass } from "@/components/report/reportUtils";
import type { SuccessReport, GrowthLever, ReportAgency } from "@/lib/api";
import { generateAiContext } from "@/components/report/reportUtils";

type Props = {
  report: SuccessReport;
  provenLevers: GrowthLever[];
  agency: ReportAgency;
  periodLabel: string;
  stale?: boolean;
};

export function ReportDocument({ report, provenLevers, agency, periodLabel, stale }: Props) {
  const funnel = report.funnel;
  const proof = report.commercial_proof;
  const opps = report.opportunities;
  const workDone = report.work?.tasks_completed || 0;
  const leversReady = provenLevers.length;
  const openLeft = report.work?.insights_open || 0;
  const readiness = Math.min(
    100,
    Math.round(
      (leversReady > 0 ? 40 : 0) +
        (workDone > 0 ? 35 : 0) +
        (report.narrative ? 15 : 0) +
        (openLeft === 0 ? 10 : 0)
    )
  );

  return (
    <article
      data-theme="light"
      className="theme-report report-document animate-state-settle overflow-hidden border border-[color:var(--border-default)] bg-[var(--surface)]"
      style={{
        ["--report-accent" as string]: agency.accent,
        borderRadius: "var(--radius-lg)",
      }}
    >
      <ReportCover report={report} agency={agency} periodLabel={periodLabel} />

      <div className="report-body space-y-8 px-5 py-8 sm:px-10 sm:py-10">
        <div
          className="report-no-print border-[color:var(--report-accent)]/30 flex flex-wrap items-center justify-between gap-4 border p-4"
          style={{ borderRadius: "var(--radius-lg)" }}
        >
          <div>
            <p className="text-[12px] font-semibold" style={{ color: agency.accent }}>
              {report.from_cache ? "Saved report" : "Freshly generated"}
              {stale ? " · stale data" : ""}
            </p>
            <p className="mt-1 text-sm text-ink">
              {leversReady} proven lever{leversReady === 1 ? "" : "s"} · {workDone} completed work
              item{workDone === 1 ? "" : "s"} · {openLeft} still open
            </p>
          </div>
          <div className="text-right">
            <p className="font-mono text-2xl" style={{ color: agency.accent }}>
              {readiness}%
            </p>
            <p className="text-muted text-[11px]">report readiness</p>
          </div>
        </div>

        <ReportLoopNarrative report={report} provenLevers={provenLevers} />

        {(() => {
          const narrative = report.narrative ? parseNarrative(report.narrative) : null;
          const bodyOk = Boolean(narrative?.body) && !isNarrativeSpam(narrative!.body);
          const hasNarrative =
            narrative && (narrative.priorities.length > 0 || Boolean(narrative.headline) || bodyOk);
          if (!hasNarrative && !report.narrative) return null;
          return (
            <Panel
              padding="lg"
              className="report-section-break !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
            >
              <h3 className="mb-3 font-display text-base font-semibold text-[var(--kinexis-ink)]">
                Executive summary
              </h3>
              <AnalystNotes content={report.narrative || ""} />
            </Panel>
          );
        })()}

        <section className="report-detail report-section-break">
          <h3 className="report-detail-title">Executive KPIs</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {report.kpis.map((k) => (
              <div
                key={k.key}
                className="border border-[color:var(--border-default)] bg-[var(--surface-light)] p-4"
                style={{ borderRadius: "var(--radius-lg)" }}
              >
                <p className="text-muted text-[11px] font-medium">{k.label}</p>
                <p className="mt-1 font-mono text-xl text-[var(--kinexis-ink)]">
                  {k.current != null
                    ? k.current.toLocaleString(undefined, { maximumFractionDigits: 2 })
                    : "—"}
                </p>
                <p className={`mt-1 font-mono text-xs ${changeToneClass(k.change_pct, k.key)}`}>
                  {fmtChange(k.change_pct)} vs prior
                </p>
              </div>
            ))}
          </div>
        </section>

        {proof && (proof.has_crm || proof.leads > 0 || proof.revenue > 0 || proof.clicks > 0) && (
          <Panel
            padding="lg"
            className="report-section-break !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
          >
            <h3 className="mb-1 text-sm font-semibold text-[var(--kinexis-ink)]">
              Commercial proof
            </h3>
            <p className="text-muted mb-3 text-xs">{proof.story}</p>
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              {(
                [
                  ["Clicks", proof.clicks],
                  ["Sessions", proof.sessions],
                  ["Leads", proof.leads],
                  ["Revenue", proof.revenue],
                ] as const
              ).map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-lg border border-[color:var(--border-default)] bg-[var(--surface)] px-3 py-2"
                >
                  <p className="text-muted text-[12px] font-medium">{label}</p>
                  <p className="mt-1 font-mono text-ink">
                    {label === "Revenue"
                      ? `$${Number(value).toLocaleString()}`
                      : Number(value).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {funnel && (funnel.stages?.length ?? 0) > 0 && (
          <Panel
            padding="lg"
            className="report-section-break !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
          >
            <h3 className="mb-3 text-sm font-semibold text-[var(--kinexis-ink)]">
              Conversion funnel
            </h3>
            {funnel.stages.some((s) => s.unreliable) && (
              <p className="text-muted mb-3 text-xs">
                Click → Session compares search/ad clicks to all-channel sessions. When sessions
                exceed clicks, the conversion rate is withheld — it is not a real funnel metric.
              </p>
            )}
            <div className="mb-4 space-y-2">
              {funnel.stages.map((s) => (
                <div
                  key={s.stage}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[color:var(--border-default)] bg-[var(--surface)] px-3 py-2 text-sm"
                >
                  <span className="text-ink-secondary">{s.stage}</span>
                  <span className="text-muted font-mono text-xs">
                    {s.entered.toLocaleString()} → {s.exited.toLocaleString()}
                    {s.unreliable || s.conversion_rate == null
                      ? " · rate n/a (cross-source)"
                      : ` · ${s.conversion_rate}% · drop ${s.dropoff}%`}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {opps &&
          (opps.rising_queries?.length > 0 ||
            opps.ctr_underperformers?.length > 0 ||
            opps.landing_pages?.length > 0) && (
            <Panel
              padding="lg"
              className="report-section-break space-y-5 !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
            >
              <h3 className="text-sm font-semibold text-[var(--kinexis-ink)]">
                Opportunities detail
              </h3>
              {opps.rising_queries.length > 0 && (
                <div>
                  <p className="text-muted mb-2 text-xs">Rising queries</p>
                  <ul className="space-y-1.5">
                    {opps.rising_queries.slice(0, 5).map((r) => (
                      <li
                        key={r.query}
                        className="flex justify-between gap-3 text-sm text-ink-secondary"
                      >
                        <span className="truncate">{r.query}</span>
                        <span className="shrink-0 font-mono text-[var(--kinexis-proof)]">
                          +{r.growth_pct}%
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {opps.ctr_underperformers.length > 0 && (
                <div>
                  <p className="text-muted mb-2 text-xs">CTR underperformers</p>
                  <ul className="space-y-1.5">
                    {opps.ctr_underperformers.slice(0, 5).map((r) => (
                      <li
                        key={r.page}
                        className="flex justify-between gap-3 text-sm text-ink-secondary"
                      >
                        <span className="truncate">{r.page}</span>
                        <span className="shrink-0 font-mono text-[var(--kinexis-signal)]">
                          {r.gap_pct}% gap
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {opps.landing_pages.length > 0 && (
                <div>
                  <p className="text-muted mb-2 text-xs">Landing pages</p>
                  <ul className="space-y-1.5">
                    {opps.landing_pages.slice(0, 5).map((r) => (
                      <li
                        key={r.page}
                        className="flex justify-between gap-3 text-sm text-ink-secondary"
                      >
                        <span className="truncate">{r.page}</span>
                        <span className="text-muted shrink-0 font-mono">
                          {r.cvr}% CVR · {r.sessions} sess
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Panel>
          )}

        {report.campaigns && report.campaigns.length > 0 && (
          <Panel
            padding="lg"
            className="report-section-break !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
          >
            <h3 className="mb-3 text-sm font-semibold text-[var(--kinexis-ink)]">Paid campaigns</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted border-b border-[color:var(--border-default)] text-left text-[11px]">
                    <th className="py-2 pr-3 font-medium">Campaign</th>
                    <th className="py-2 pr-3 font-medium">Clicks</th>
                    <th className="py-2 pr-3 font-medium">Spend</th>
                    <th className="py-2 pr-3 font-medium">Conv.</th>
                    <th className="py-2 font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {report.campaigns.map((c) => (
                    <tr key={c.campaign} className="border-b border-[color:var(--border-subtle)]">
                      <td className="max-w-[220px] truncate py-2 pr-3 text-ink-secondary">
                        {c.campaign}
                      </td>
                      <td className="py-2 pr-3 font-mono">{c.clicks.toLocaleString()}</td>
                      <td className="py-2 pr-3 font-mono">${c.cost.toLocaleString()}</td>
                      <td className="py-2 pr-3 font-mono">{c.conversions}</td>
                      <td className="py-2 font-mono">${c.conversion_value.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {report.next_actions.length > 0 && (
          <Panel
            padding="lg"
            className="report-section-break !border-[color:var(--border-default)] !bg-[var(--surface-light)]"
          >
            <h3 className="mb-3 text-sm font-semibold text-[var(--kinexis-ink)]">
              Opportunities next
            </h3>
            <ul className="space-y-2">
              {report.next_actions.map((a, i) => (
                <li key={i} className="text-sm text-ink-secondary">
                  <span className="font-medium text-[var(--kinexis-ink)]">
                    {a.title || "Action"}
                  </span>
                  {(a.why_it_matters || a.estimated_impact) && (
                    <span className="text-muted"> — {a.why_it_matters || a.estimated_impact}</span>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <details className="report-section-break group cursor-pointer">
          <summary className="flex items-center gap-2 text-xs font-medium text-[var(--kinexis-mist)] transition-colors hover:text-ink-secondary">
            <span className="inline-block text-[15px] leading-none transition-transform group-open:rotate-90">
              &#9656;
            </span>
            AI analysis data — expand for structured context
          </summary>
          <div className="mt-3 max-h-[600px] overflow-auto whitespace-pre-wrap rounded-lg border border-[color:var(--border-subtle)] bg-[var(--surface)] p-4 font-mono text-[11px] leading-relaxed text-ink-dim">
            {generateAiContext(report, provenLevers)}
          </div>
        </details>

        <footer className="report-doc-footer flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--border-default)] pt-4 text-[11px] text-[var(--kinexis-mist)]">
          <span>{agency.name} · Confidential</span>
          <span>
            {report.client.name} · {report.generated_at}
          </span>
        </footer>
      </div>
    </article>
  );
}

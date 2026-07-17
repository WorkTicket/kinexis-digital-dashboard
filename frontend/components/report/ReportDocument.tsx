"use client";

import AnalystNotes, { parseNarrative, isNarrativeSpam } from "@/components/AnalystNotes";
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
  const narrative = report.narrative ? parseNarrative(report.narrative) : null;
  const bodyOk = Boolean(narrative?.body) && !isNarrativeSpam(narrative!.body);
  const hasNarrative =
    narrative && (narrative.priorities.length > 0 || Boolean(narrative.headline) || bodyOk);
  const showExecutiveSummary = hasNarrative || Boolean(report.narrative);
  const headlineKpis = report.kpis.slice(0, 4);
  const hasProof =
    proof && (proof.has_crm || proof.leads > 0 || proof.revenue > 0 || proof.clicks > 0);
  const hasFunnel = funnel && (funnel.stages?.length ?? 0) > 0;
  const hasOpps =
    opps &&
    (opps.rising_queries?.length > 0 ||
      opps.ctr_underperformers?.length > 0 ||
      opps.landing_pages?.length > 0);
  const hasCampaigns = report.campaigns && report.campaigns.length > 0;
  const hasNextActions = report.next_actions.length > 0;
  const hasAppendix = hasFunnel || hasOpps || hasCampaigns || hasNextActions;

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

      <div className="report-body space-y-12">
        {/* ── Narrative ── */}
        <section className="report-slide">
          <p className="report-slide-eyebrow">Performance story</p>
          <h2 className="report-slide-heading font-display font-normal">The loop this period</h2>
          <ReportLoopNarrative report={report} provenLevers={provenLevers} />
        </section>

        {showExecutiveSummary && (
          <section className="report-slide report-section-break">
            <p className="report-slide-eyebrow">Executive summary</p>
            <div className="report-analyst-notes">
              <AnalystNotes content={report.narrative || ""} />
            </div>
          </section>
        )}

        {/* ── Proof ── */}
        {(headlineKpis.length > 0 || hasProof) && (
          <section className="report-slide report-section-break">
            <p className="report-slide-eyebrow">Proof</p>
            <h2 className="report-slide-heading font-display font-normal">What moved</h2>

            {headlineKpis.length > 0 && (
              <div className="report-kpi-grid mb-12">
                {headlineKpis.map((k) => (
                  <div key={k.key}>
                    <p className="report-kpi-label">{k.label}</p>
                    <p className="report-kpi-value">
                      {k.current != null
                        ? k.current.toLocaleString(undefined, { maximumFractionDigits: 2 })
                        : "—"}
                    </p>
                    <p className={`report-kpi-delta ${changeToneClass(k.change_pct, k.key)}`}>
                      {fmtChange(k.change_pct)} vs prior
                    </p>
                  </div>
                ))}
              </div>
            )}

            {hasProof && (
              <div>
                <h3 className="report-detail-title">Commercial proof</h3>
                {proof!.story && <p className="report-proof-story">{proof!.story}</p>}
                <div className="report-proof-metrics">
                  {(
                    [
                      ["Clicks", proof!.clicks],
                      ["Sessions", proof!.sessions],
                      ["Leads", proof!.leads],
                      ["Revenue", proof!.revenue],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <p className="report-proof-metric-label">{label}</p>
                      <p className="report-proof-metric-value">
                        {label === "Revenue"
                          ? `$${Number(value).toLocaleString()}`
                          : Number(value).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        {/* ── Appendix ── */}
        {hasAppendix && (
          <section className="report-slide report-section-break report-appendix">
            <p className="report-slide-eyebrow">Appendix</p>
            <h2 className="report-slide-heading font-display font-normal">Supporting detail</h2>

            {hasFunnel && (
              <div className="report-appendix-block">
                <h3 className="report-appendix-title">Conversion funnel</h3>
                {funnel!.stages.some((s) => s.unreliable) && (
                  <p className="text-muted mb-4 text-xs leading-relaxed">
                    Click → Session compares search/ad clicks to all-channel sessions. When sessions
                    exceed clicks, the conversion rate is withheld — it is not a real funnel metric.
                  </p>
                )}
                <div>
                  {funnel!.stages.map((s) => (
                    <div key={s.stage} className="report-appendix-row">
                      <span>{s.stage}</span>
                      <span className="text-muted font-mono text-xs">
                        {s.entered.toLocaleString()} → {s.exited.toLocaleString()}
                        {s.unreliable || s.conversion_rate == null
                          ? " · rate n/a (cross-source)"
                          : ` · ${s.conversion_rate}% · drop ${s.dropoff}%`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {hasOpps && (
              <div className="report-appendix-block">
                <h3 className="report-appendix-title">Opportunities detail</h3>
                {opps!.rising_queries.length > 0 && (
                  <div className="mb-4">
                    <p className="text-muted mb-2 text-xs">Rising queries</p>
                    {opps!.rising_queries.slice(0, 5).map((r) => (
                      <div key={r.query} className="report-appendix-row">
                        <span className="truncate">{r.query}</span>
                        <span className="shrink-0 font-mono text-[var(--kinexis-proof)]">
                          +{r.growth_pct}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {opps!.ctr_underperformers.length > 0 && (
                  <div className="mb-4">
                    <p className="text-muted mb-2 text-xs">CTR underperformers</p>
                    {opps!.ctr_underperformers.slice(0, 5).map((r) => (
                      <div key={r.page} className="report-appendix-row">
                        <span className="truncate">{r.page}</span>
                        <span className="shrink-0 font-mono text-[var(--kinexis-signal)]">
                          {r.gap_pct}% gap
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {opps!.landing_pages.length > 0 && (
                  <div>
                    <p className="text-muted mb-2 text-xs">Landing pages</p>
                    {opps!.landing_pages.slice(0, 5).map((r) => (
                      <div key={r.page} className="report-appendix-row">
                        <span className="truncate">{r.page}</span>
                        <span className="text-muted shrink-0 font-mono">
                          {r.cvr}% CVR · {r.sessions} sess
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {hasCampaigns && (
              <div className="report-appendix-block">
                <h3 className="report-appendix-title">Paid campaigns</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-muted border-b border-[color:var(--border-subtle)] text-left text-[11px]">
                        <th className="py-2 pr-3 font-medium">Campaign</th>
                        <th className="py-2 pr-3 font-medium">Clicks</th>
                        <th className="py-2 pr-3 font-medium">Spend</th>
                        <th className="py-2 pr-3 font-medium">Conv.</th>
                        <th className="py-2 font-medium">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.campaigns!.map((c) => (
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
              </div>
            )}

            {hasNextActions && (
              <div className="report-appendix-block">
                <h3 className="report-appendix-title">Opportunities next</h3>
                <ul className="space-y-3">
                  {report.next_actions.map((a, i) => (
                    <li key={i} className="text-sm text-ink-secondary">
                      <span className="font-medium text-[var(--kinexis-ink)]">
                        {a.title || "Action"}
                      </span>
                      {(a.why_it_matters || a.estimated_impact) && (
                        <span className="text-muted">
                          {" "}
                          — {a.why_it_matters || a.estimated_impact}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}

        <details className="report-no-print group cursor-pointer px-0 py-4">
          <summary className="flex items-center gap-2 text-xs font-medium text-[var(--kinexis-mist)] transition-colors hover:text-ink-secondary">
            <span className="inline-block text-[15px] leading-none transition-transform group-open:rotate-90">
              {"\u25B8"}
            </span>
            AI analysis data — expand for structured context
          </summary>
          <div
            className="mt-3 max-h-[600px] overflow-auto whitespace-pre-wrap border border-[color:var(--border-subtle)] bg-[var(--surface)] p-4 font-mono text-[11px] leading-relaxed text-ink-dim"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            {generateAiContext(report, provenLevers)}
          </div>
        </details>

        <footer className="report-doc-footer flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--kinexis-mist)]">
          <span>
            {agency.name} · Confidential
            {stale ? " · stale data" : ""}
            {report.from_cache ? " · saved" : ""}
          </span>
          <span>
            {report.client.name} · {report.generated_at}
          </span>
        </footer>
      </div>
    </article>
  );
}

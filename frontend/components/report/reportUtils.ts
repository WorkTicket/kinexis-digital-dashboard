import type { SuccessReport, ReportAgency, ReportReadinessChecklist, GrowthLever } from "@/lib/api";

export const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const FOCUS_FALLBACK = "var(--kinexis-proof)";

export function prevMonth(d = new Date()) {
  const m = d.getMonth(); // 0-indexed (0=Jan, 11=Dec)
  if (m === 0) return { year: d.getFullYear() - 1, month: 12 }; // December previous year
  return { year: d.getFullYear(), month: m }; // 1-indexed month (1=Jan..12=Dec)
}

export function fmtChange(ch: number | null | undefined) {
  if (ch == null) return "—";
  return `${ch >= 0 ? "+" : ""}${ch}%`;
}

/** Lower-is-better (rank) or spend metrics — green when the number drops. */
const INVERSE_KEY_RE = /\.(position|cost|bounce_rate)$/i;

export function isInverseMetric(key: string | null | undefined) {
  if (!key) return false;
  return INVERSE_KEY_RE.test(key);
}

/** Tone class for a change: proof (good), risk (bad), or muted. */
export function changeToneClass(
  changePct: number | null | undefined,
  key?: string | null,
  favorable?: boolean | null
) {
  if (changePct == null) return "text-muted";
  let good = favorable;
  if (good == null) {
    if (changePct === 0) return "text-muted";
    good = isInverseMetric(key) ? changePct < 0 : changePct > 0;
  }
  if (good === true) return "text-[var(--kinexis-proof)]";
  if (good === false) return "text-[var(--kinexis-risk)]";
  return "text-muted";
}

export function resolveAgency(report: SuccessReport | null): ReportAgency {
  if (report?.agency) return report.agency;
  const brand = report?.client.brand_color || FOCUS_FALLBACK;
  return {
    name: "Kinexis",
    accent: brand.startsWith("#") ? brand : FOCUS_FALLBACK,
    logo_url: "",
    is_white_label: false,
  };
}

export function readinessScore(checklist: ReportReadinessChecklist | undefined) {
  if (!checklist) return 0;
  const keys: (keyof ReportReadinessChecklist)[] = [
    "data_synced",
    "work_or_proof",
    "has_saved_report",
    "narrative_ready",
  ];
  return Math.round((keys.filter((k) => checklist[k]).length / keys.length) * 100);
}

export function exportBlocked(checklist: ReportReadinessChecklist | undefined) {
  if (!checklist) return true;
  return !(checklist.data_synced && checklist.work_or_proof && checklist.narrative_ready);
}

function kpiDirection(changePct: number | null): string {
  if (changePct == null) return "no prior data";
  const dir = changePct > 0 ? "up" : changePct < 0 ? "down" : "flat";
  const mag = Math.abs(changePct);
  if (mag < 5) return `stable (${changePct >= 0 ? "+" : ""}${changePct}%)`;
  if (mag < 15) return `slightly ${dir} (${changePct >= 0 ? "+" : ""}${changePct}%)`;
  if (mag < 30) return `${dir} (${changePct >= 0 ? "+" : ""}${changePct}%)`;
  return `sharply ${dir} (${changePct >= 0 ? "+" : ""}${changePct}%)`;
}

export function generateAiContext(report: SuccessReport, provenLevers: GrowthLever[]): string {
  const sections: string[] = [];

  sections.push(`# Client Success Report: ${report.client.name}`);
  sections.push(`Industry: ${report.client.industry}`);
  sections.push(`Period: ${report.period.start} → ${report.period.end} (${report.period.days}d)`);
  sections.push(`Generated: ${report.generated_at}`);
  sections.push(`Report type: ${report.report_kind ?? "success"}`);
  sections.push("");

  const kpis = report.kpis;
  if (kpis.length > 0) {
    sections.push("## Key Performance Indicators");
    sections.push("| Metric | Current | Previous | Change | Direction |");
    sections.push("|--------|---------|----------|--------|-----------|");
    for (const k of kpis) {
      const cur = k.current.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const prev = k.previous.toLocaleString(undefined, { maximumFractionDigits: 2 });
      const ch = k.change_pct != null ? `${k.change_pct >= 0 ? "+" : ""}${k.change_pct}%` : "—";
      const dir = kpiDirection(k.change_pct);
      sections.push(`| ${k.label} (${k.source}) | ${cur} | ${prev} | ${ch} | ${dir} |`);
    }
    sections.push("");
  }

  const funnel = report.funnel;
  if (funnel?.stages?.length) {
    sections.push("## Conversion Funnel");
    sections.push("| Stage | Entered | Exited | Drop-off | Conv. Rate |");
    sections.push("|-------|---------|--------|----------|------------|");
    for (const s of funnel.stages) {
      const dropoff = s.dropoff != null ? `${s.dropoff}%` : "—";
      const cvr = s.conversion_rate != null ? `${s.conversion_rate}%` : "n/a";
      sections.push(
        `| ${s.stage} | ${s.entered.toLocaleString()} | ${s.exited.toLocaleString()} | ${dropoff} | ${cvr} |`
      );
    }
    sections.push("");

    if (funnel.biggest_leak) {
      sections.push(
        `**Biggest leak:** ${funnel.biggest_leak.stage} (${funnel.biggest_leak.dropoff}% drop-off)`
      );
      sections.push("");
    }

    if (funnel.leaks?.length) {
      sections.push("### Leak Analysis & Fixes");
      for (const leak of funnel.leaks) {
        sections.push(`- **${leak.stage}** (${leak.leak_pct}% leak)`);
        sections.push(`  - Cause: ${leak.cause}`);
        sections.push(`  - Fix: ${leak.fix}`);
        if (leak.lost_revenue)
          sections.push(`  - Lost revenue: $${leak.lost_revenue.toLocaleString()}`);
      }
      sections.push("");
    }

    if (funnel.growth_lever) {
      const gl = funnel.growth_lever;
      sections.push("### Growth Lever");
      sections.push(`- **${gl.title || gl.stage || "Primary lever"}**`);
      if (gl.cause) sections.push(`  - Cause: ${gl.cause}`);
      if (gl.fix) sections.push(`  - Fix: ${gl.fix}`);
      if (gl.leak_pct != null) sections.push(`  - Leak size: ${gl.leak_pct}%`);
      sections.push("");
    }
  }

  const opps = report.opportunities;
  if (opps) {
    sections.push("## Growth Opportunities");

    if (opps.rising_queries?.length) {
      sections.push("### Rising Search Queries");
      sections.push("| Query | Growth |");
      sections.push("|-------|--------|");
      for (const r of opps.rising_queries.slice(0, 10)) {
        sections.push(`| ${r.query} | +${r.growth_pct}% |`);
      }
      sections.push("");
    }

    if (opps.ctr_underperformers?.length) {
      sections.push("### CTR Underperformers (fix titles/metas)");
      sections.push("| Page | CTR Gap |");
      sections.push("|------|---------|");
      for (const r of opps.ctr_underperformers.slice(0, 10)) {
        sections.push(`| ${r.page} | ${r.gap_pct}% gap |`);
      }
      sections.push("");
    }

    if (opps.landing_pages?.length) {
      sections.push("### Landing Page Conversion Rates");
      sections.push("| Page | Sessions | CVR |");
      sections.push("|------|----------|-----|");
      for (const r of opps.landing_pages.slice(0, 10)) {
        sections.push(`| ${r.page} | ${r.sessions} | ${r.cvr}% |`);
      }
      sections.push("");
    }
  }

  if (report.campaigns?.length) {
    sections.push("## Paid Campaigns");
    sections.push("| Campaign | Clicks | Spend | Conv. | Value |");
    sections.push("|----------|--------|-------|-------|-------|");
    for (const c of report.campaigns) {
      sections.push(
        `| ${c.campaign} | ${c.clicks.toLocaleString()} | $${c.cost.toLocaleString()} | ${c.conversions} | $${c.conversion_value.toLocaleString()} |`
      );
    }
    sections.push("");
  }

  if (report.commercial_proof) {
    const p = report.commercial_proof;
    sections.push("## Commercial Proof");
    sections.push(`- **Clicks:** ${p.clicks.toLocaleString()}`);
    sections.push(`- **Sessions:** ${p.sessions.toLocaleString()}`);
    sections.push(`- **Leads:** ${p.leads.toLocaleString()}`);
    sections.push(`- **Revenue:** $${p.revenue.toLocaleString()}`);
    if (p.opportunities) sections.push(`- **Opportunities:** ${p.opportunities}`);
    if (p.closed_won) sections.push(`- **Closed-won:** ${p.closed_won}`);
    if (p.story) sections.push(`- **Story:** ${p.story}`);
    sections.push("");
  }

  if (report.work) {
    const w = report.work;
    sections.push("## Work Completed");
    sections.push(`- Tasks completed: ${w.tasks_completed}`);
    sections.push(`- Insights resolved: ${w.insights_resolved}`);
    sections.push(`- Insights still open: ${w.insights_open}`);
    if (w.briefs_created) sections.push(`- Content briefs created: ${w.briefs_created}`);
    if (w.completed_items?.length) {
      sections.push("- Completed items:");
      for (const item of w.completed_items) {
        sections.push(`  - ${item.label}`);
      }
    }
    sections.push("");
  }

  if (report.impact_wins?.length) {
    sections.push("## Impact / Wins");
    for (const w of report.impact_wins) {
      sections.push(`- **${w.label}**: +${w.avg_primary_metric_change}% avg improvement`);
      if (w.proof_copy) sections.push(`  - ${w.proof_copy}`);
    }
    sections.push("");
  }

  if (provenLevers?.length) {
    sections.push("## Proven Growth Levers");
    for (const l of provenLevers) {
      sections.push(`- **${l.title}**`);
      if (l.impact_summary) sections.push(`  - Impact: ${l.impact_summary}`);
      if (l.cause) sections.push(`  - Cause: ${l.cause}`);
      if (l.fix) sections.push(`  - Fix: ${l.fix}`);
      if (l.confidence_label) sections.push(`  - Confidence: ${l.confidence_label}`);
    }
    sections.push("");
  }

  if (report.next_actions?.length) {
    sections.push("## Recommended Next Actions");
    for (const a of report.next_actions) {
      const title = a.title || "Action";
      const impact = a.estimated_impact ? ` [Impact: ${a.estimated_impact}]` : "";
      const why = a.why_it_matters ? ` — ${a.why_it_matters}` : "";
      const priority = a.priority_score != null ? ` (priority: ${a.priority_score})` : "";
      sections.push(`- ${title}${priority}${impact}${why}`);
    }
    sections.push("");
  }

  const declining = kpis.filter((k) => (k.change_pct ?? 0) < -5);
  const improving = kpis.filter((k) => (k.change_pct ?? 0) > 5);
  const stable = kpis.filter((k) => k.change_pct == null || Math.abs(k.change_pct) <= 5);

  sections.push("## Health Assessment & Fix Recommendations");

  if (declining.length > 0) {
    sections.push("### Declining Metrics — Needs Attention");
    for (const k of declining) {
      sections.push(`- **${k.label}**: ${k.current} (${kpiDirection(k.change_pct)})`);
    }
    sections.push("");
  }

  if (improving.length > 0) {
    sections.push("### Improving Metrics — Compound the Wins");
    for (const k of improving) {
      sections.push(`- **${k.label}**: ${k.current} (${kpiDirection(k.change_pct)})`);
    }
    sections.push("");
  }

  if (stable.length > 0) {
    sections.push("### Stable Metrics — Maintain");
    for (const k of stable) {
      sections.push(`- **${k.label}**: ${k.current}`);
    }
    sections.push("");
  }

  if (funnel?.leaks?.length) {
    sections.push("### Priority Fixes by Funnel Stage");
    for (const leak of funnel.leaks) {
      sections.push(`1. **${leak.stage}** (${leak.leak_pct}% loss): ${leak.fix}`);
    }
    sections.push("");
  }

  sections.push("### Opportunity-Specific Recommendations");
  if (kpis.some((k) => k.key === "ctr" && (k.change_pct ?? 0) < -5)) {
    sections.push(
      "- **Improve CTR**: Rewrite page titles with front-loaded keywords, add compelling meta descriptions, implement FAQ/HowTo structured data for rich results"
    );
  }
  if (kpis.some((k) => k.key === "clicks" && (k.change_pct ?? 0) < -10)) {
    sections.push(
      "- **Recover search clicks**: Publish content targeting declining keywords, audit content gaps vs competitors, build backlinks to priority pages"
    );
  }
  if (kpis.some((k) => k.key === "sessions" && (k.change_pct ?? 0) < -10)) {
    sections.push(
      "- **Increase site traffic**: Promote recent content via email/newsletter, share on social channels, refresh outdated cornerstone content"
    );
  }
  if (kpis.some((k) => k.key === "conversions" && (k.change_pct ?? 0) < -10)) {
    sections.push(
      "- **Boost conversions**: Add clear CTAs above the fold, reduce form friction, add trust signals (testimonials, case studies) near conversion points"
    );
  }
  if (report.opportunities?.ctr_underperformers?.length) {
    sections.push(
      "- **Fix CTR underperformers**: Optimize titles/metas for specific pages with largest CTR gaps (see CTR Underperformers table above)"
    );
  }
  if (report.opportunities?.rising_queries?.length) {
    sections.push(
      "- **Capitalize on rising queries**: Create or expand content around growing search terms to capture increasing demand"
    );
  }
  if (
    declining.length === 0 &&
    report.opportunities?.ctr_underperformers?.length === 0 &&
    report.opportunities?.rising_queries?.length === 0
  ) {
    sections.push(
      "- No critical issues detected. Focus on testing new channels and scaling what works."
    );
  }
  sections.push("");

  sections.push("---");
  sections.push(`_AI-generated analysis from ${report.client.name} success report_`);

  return sections.join("\n");
}

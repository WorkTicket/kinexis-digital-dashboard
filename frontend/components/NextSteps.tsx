"use client";

import { useEffect, useMemo, useState } from "react";
import { api, Insight, Task } from "@/lib/api";
import { insightKind, type HealthImprovement } from "@/lib/metrics";
import { EmptyState } from "@/components/ui/EmptyState";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { Input } from "@/components/ui/Input";
import {
  ArrowRight,
  Lightbulb,
  Plus,
  Zap,
  Clock,
  TrendingUp,
  Flag,
} from "lucide-react";

type FixEffectiveness = {
  fix_type: string;
  wins: number;
  total: number;
  win_rate: number | null;
  median_lift_pct: number | null;
  measured: boolean;
};

function formatRoiBadge(
  insightType: string,
  typical?: string,
  byType?: Record<string, FixEffectiveness>
): { label: string; measured: boolean } | null {
  const stats = byType?.[insightType];
  if (stats?.measured && stats.win_rate != null) {
    const pct = Math.round(stats.win_rate * 100);
    const lift = stats.median_lift_pct != null ? ` · median +${stats.median_lift_pct}%` : "";
    return {
      label: `Measured: ${pct}% win rate · ${stats.total} fixes${lift}`,
      measured: true,
    };
  }
  const typicalLabel = formatTypicalRoi(typical);
  if (!typicalLabel) return null;
  return { label: typicalLabel, measured: false };
}

function concreteSteps(insight: Insight): string[] | null {
  const raw = (insight.recommended_action || "").trim();
  if (!raw) return null;
  const looksConcrete =
    /^on\s+https?:\/\//i.test(raw) ||
    /FROM\s+"/i.test(raw) ||
    /change\s+<title>/i.test(raw) ||
    /target page:/i.test(insight.message || "") ||
    /priority page:/i.test(insight.message || "") ||
    /worst pages?:/i.test(insight.message || "") ||
    /^\d+\)\s+on\s+https?:\/\//im.test(raw);
  if (!looksConcrete && !raw.includes("\n")) return null;
  const lines = raw
    .split(/\n+/)
    .map((l) => l.replace(/^\d+[).]\s*/, "").trim())
    .filter((l) => l.length > 8 && !/^on\s+https?:\/\//i.test(l));
  const onLine = raw.split(/\n+/).find((l) => /^on\s+https?:\/\//i.test(l.trim()));
  const steps = [...(onLine ? [onLine.trim()] : []), ...lines.filter((l) => l !== onLine?.trim())];
  return steps.length >= 2 ? steps : null;
}

/** ROI strings in PLAYBOOKS are historical ranges, not client-measured promises. */
function formatTypicalRoi(label?: string): string | null {
  if (!label) return null;
  if (/typical:|estimate/i.test(label)) return label;
  return `Typical: ${label} (estimate)`;
}

function confidenceMeta(insight: Insight): {
  label: string;
  tone: "proof" | "signal" | "warning" | "risk" | "default";
  title: string;
} | null {
  const tier = (insight.confidence_tier || "").toLowerCase();
  if (!tier) return null;
  const n =
    insight.sample_size != null
      ? ` · ${insight.sample_size.toLocaleString()} samples`
      : "";
  const caveat = insight.algorithmic_caveat ? " · overlaps a known algorithm update" : "";
  const title = `Evidence confidence${n}${caveat}`;
  if (tier === "high") return { label: "High conf", tone: "proof", title };
  if (tier === "medium") return { label: "Med conf", tone: "signal", title };
  if (tier === "low") return { label: "Low conf", tone: "warning", title };
  if (tier === "insufficient") return { label: "Thin sample", tone: "risk", title };
  return { label: tier, tone: "default", title };
}

export const PLAYBOOKS: Record<
  string,
  { title: string; metric: string; steps: string[]; effort: string; estimatedROI?: string }
> = {
  content_opportunity: {
    title: "Win the rising query",
    metric: "Impressions \u2192 clicks & rankings",
    effort: "2\u20134 hrs",
    estimatedROI: "+15\u201340% clicks",
    steps: [
      "Open GSC \u2192 Performance \u2192 filter to this query; note current page & position.",
      "Audit the ranking URL: does H1/title match the query intent?",
      "Add a dedicated section or landing page targeting the query (800\u20131500 words).",
      "Internal-link from 2\u20133 related pages; resubmit URL in GSC.",
      "Recheck impressions & position in 14 days.",
    ],
  },
  ctr_opportunity: {
    title: "Lift CTR with better SERP copy",
    metric: "CTR & clicks",
    effort: "30\u201360 min",
    estimatedROI: "+5\u201320% CTR",
    steps: [
      "Search the query in an incognito window; screenshot top 3 titles/metas.",
      "Rewrite title (\u226460 chars) with primary keyword + benefit/number.",
      "Rewrite meta (\u2264155 chars) with a clear CTA and differentiator.",
      "Deploy; request indexing; compare CTR in 7\u201314 days.",
    ],
  },
  ctr_gap: {
    title: "Fix severe CTR leak",
    metric: "CTR & clicks",
    effort: "30\u201360 min",
    estimatedROI: "+10\u201330% CTR",
    steps: [
      "Confirm the query has meaningful volume (\u22651k impr/month) in GSC.",
      "SERP-check vs top 3: title length, benefit, numbers, year.",
      "Rewrite title (\u226460 chars) and meta (\u2264155 chars) with a clear CTA.",
      "Deploy; request indexing; compare CTR in 7\u201314 days.",
    ],
  },
  decline_alert: {
    title: "Stop the traffic drop",
    metric: "Clicks / impressions",
    effort: "1\u20132 hrs",
    estimatedROI: "Recover 30\u201370% of lost traffic",
    steps: [
      "Open the worst dropped URL named in this insight (not the whole site).",
      "Confirm HTTP 200, no accidental noindex, canonical not pointing away.",
      "GSC URL Inspection \u2192 request indexing if excluded or soft-404.",
      "Fix 404/redirect chains; restore thinned content on that exact page.",
      "Repeat for the next dropped URLs listed; remeasure site clicks in 7 days.",
    ],
  },
  zero_click_alert: {
    title: "Turn impressions into clicks",
    metric: "Clicks from high-impression queries",
    effort: "1 hr",
    estimatedROI: "+5\u201315% of impression volume",
    steps: [
      "SERP-check the query: featured snippet, PAA, or knowledge panel?",
      "If snippet-owned: structure content to win the snippet (lists, tables, FAQ).",
      "If poor snippet: improve title/meta and add rich results markup where relevant.",
      "Track clicks on that query for 2 weeks.",
    ],
  },
  cro_opportunity: {
    title: "Convert high-traffic pages",
    metric: "Conversion rate",
    effort: "2\u20136 hrs",
    estimatedROI: "+10\u201350% CVR",
    steps: [
      "Open the page + Clarity recordings for that URL.",
      "Map the primary CTA above the fold; remove competing CTAs.",
      "Shorten forms (fewer fields) or add trust signals near the CTA.",
      "A/B test headline or CTA copy for 2 weeks.",
      "Watch key_events / CVR on that landing page.",
    ],
  },
  error_spike_alert: {
    title: "Clean up bad traffic",
    metric: "Sessions & threat rate",
    effort: "45\u201390 min",
    estimatedROI: "Prevent traffic quality penalties",
    steps: [
      "Cloudflare \u2192 Security Events: note attack/bot patterns.",
      "Tighten WAF / bot fight mode for abusive ASNs or paths.",
      "Confirm real users still pass (challenge vs block).",
      "Re-check GA4 sessions next week.",
    ],
  },
  pagespeed_urgent: {
    title: "Fix Core Web Vitals (urgent)",
    metric: "Mobile performance & rankings",
    effort: "half day+",
    estimatedROI: "+5\u201315% organic traffic",
    steps: [
      "Run PageSpeed Insights on the URL (mobile).",
      "Compress/resize hero images; serve WebP/AVIF.",
      "Defer non-critical JS; remove unused CSS.",
      "Enable caching / CDN; retest until score \u226570.",
    ],
  },
  pagespeed_improve: {
    title: "Improve page speed",
    metric: "LCP / TBT",
    effort: "1\u20133 hrs",
    estimatedROI: "+3\u20138% organic traffic",
    steps: [
      "Focus on Largest Contentful Paint and Total Blocking Time.",
      "Lazy-load below-fold media; preload the LCP image.",
      "Retest mobile score; aim for 70+.",
    ],
  },
  mobile_ctr_gap: {
    title: "Close the mobile CTR gap",
    metric: "Mobile CTR",
    effort: "1\u20132 hrs",
    estimatedROI: "+10\u201325% mobile CTR",
    steps: [
      "Open the highest-click page named in this insight on a phone SERP (incognito).",
      "Shorten the title if truncated vs desktop; tighten meta for mobile.",
      "Fix tap targets, font size, sticky header covering content on that live URL.",
      "Run mobile PageSpeed on the same URL; fix LCP if weak.",
      "Recheck GSC mobile CTR for that URL in 14 days.",
    ],
  },
  bing_opportunity: {
    title: "Open the Bing channel",
    metric: "Bing clicks",
    effort: "30 min",
    estimatedROI: "+5\u201315% total search traffic",
    steps: [
      "Add the site in Bing Webmaster Tools.",
      "Import from Google Search Console (one-click).",
      "Submit sitemap; verify crawl stats in a week.",
    ],
  },
  bing_underperform: {
    title: "Grow Bing share",
    metric: "Bing vs Google clicks",
    effort: "1 hr",
    estimatedROI: "+10\u201330% Bing traffic",
    steps: [
      "Bing Webmaster \u2192 Crawl errors; fix blocked resources.",
      "Resubmit sitemap; check Index Explorer coverage.",
      "Ensure robots.txt allows Bingbot.",
    ],
  },
  bounce_cro_alert: {
    title: "Fix bounce + conversion leak",
    metric: "Bounce rate & CVR",
    effort: "2\u20134 hrs",
    estimatedROI: "+10\u201330% CVR",
    steps: [
      "Open the exact landing URL in this insight + 5 Clarity recordings for it.",
      "Align hero message with the ad/search query that sent traffic to that URL.",
      "Move primary CTA higher; cut clutter above the fold on that page.",
      "Fix load delays >3s on mobile for that URL.",
      "Re-measure bounce + key_events on that URL in 14 days.",
    ],
  },
  ads_spend_low_leads: {
    title: "Fix ads \u2192 leads leak",
    metric: "Ad cost vs CRM leads",
    effort: "1\u20133 hrs",
    estimatedROI: "2\u20135x ROAS improvement",
    steps: [
      "Open the top landing URL named in this insight.",
      "Submit a test lead \u2014 confirm a HubSpot contact with UTMs is created.",
      "Match the primary CTA/form to the ad promise above the fold on that URL.",
      "Pause campaigns still sending traffic here with zero CRM leads.",
      "Remeasure leads vs spend in 7 days.",
    ],
  },
  pause_weak_campaign: {
    title: "Pause zero-conversion campaign",
    metric: "Ad cost vs conversions",
    effort: "15\u201345 min",
    estimatedROI: "Stop wasted spend",
    steps: [
      "Open the named campaign in Google/Meta Ads (or Ads CSV source).",
      "Pause the campaign or cut budget 80% immediately.",
      "Open the top ad landing URL and submit a test conversion/form.",
      "Confirm GA4 key_event + CRM lead fire with the campaign UTM.",
      "Rebuild creative/keywords only after tracking is verified; remeasure in 7 days.",
    ],
  },
  verify_tracking: {
    title: "Verify conversion tracking",
    metric: "GA4 key_events + CRM leads",
    effort: "30\u201390 min",
    estimatedROI: "Restore measurable ROI",
    steps: [
      "From each active ad, open the final landing URL and submit a test form.",
      "Confirm a HubSpot contact is created with UTMs matching the campaign.",
      "Open GA4 DebugView and trigger the form — confirm the key_event fires.",
      "Fix broken tags/pixels before changing bids or creative.",
      "Remeasure leads vs spend in 14 days.",
    ],
  },
  crux_lcp_failing: {
    title: "Fix real-user LCP (CrUX)",
    metric: "CrUX LCP p75",
    effort: "2\u20136 hrs",
    estimatedROI: "+CWV + rankings",
    steps: [
      "Confirm the failing URL in PageSpeed field data (CrUX), not just lab score.",
      "Optimize LCP element: image compression, preload, server TTFB.",
      "Defer non-critical JS/CSS competing with the LCP resource.",
      "Re-check CrUX after 28 days (field window) and lab PSI for leading indicator.",
    ],
  },
  crux_cls_failing: {
    title: "Fix real-user CLS (CrUX)",
    metric: "CrUX CLS p75",
    effort: "1\u20133 hrs",
    estimatedROI: "+UX stability",
    steps: [
      "Identify shifting elements (ads, fonts, images without dimensions).",
      "Reserve space with width/height or aspect-ratio; preload fonts.",
      "Avoid inserting content above existing content after load.",
      "Re-check CrUX CLS after the next 28-day field window.",
    ],
  },
  crux_inp_failing: {
    title: "Fix real-user INP (CrUX)",
    metric: "CrUX INP p75",
    effort: "2\u20136 hrs",
    estimatedROI: "+interaction UX",
    steps: [
      "Profile main-thread long tasks on the failing URL (Chrome Performance).",
      "Break up heavy JS; defer third-party scripts; reduce hydration cost.",
      "Prefer event handlers that yield quickly; avoid layout thrash.",
      "Re-check CrUX INP after the next field window.",
    ],
  },
  leads_revenue_leak: {
    title: "Fix leads \u2192 revenue handoff",
    metric: "Leads vs closed revenue",
    effort: "2\u20134 hrs",
    estimatedROI: "+20\u201350% close rate",
    steps: [
      "In HubSpot, open the last 10 leads and note each source landing URL.",
      "For the top landing URL: check if the page offer matches what sales can close.",
      "Enforce same-day speed-to-lead SLA and log first-touch time.",
      "Remeasure closed_won and revenue in 14 days.",
    ],
  },
  organic_leads_leak: {
    title: "Fix organic \u2192 leads leak",
    metric: "Organic traffic vs CRM leads",
    effort: "1\u20133 hrs",
    estimatedROI: "+15\u201340% lead gen",
    steps: [
      "Open the top organic URL by clicks named in this insight.",
      "Submit the contact form \u2014 confirm HubSpot contact + thank-you/key_event.",
      "Put one clear CTA above the fold matching search intent on that URL.",
      "Add a mid-page CTA if the page ranks for informational queries.",
      "Remeasure HubSpot leads vs GSC clicks in 14 days.",
    ],
  },
  crawl_broken_pages: {
    title: "Fix broken crawled pages",
    metric: "Indexability & crawl health",
    effort: "1\u20132 hrs",
    estimatedROI: "Recover lost index coverage",
    steps: [
      "Open each HTTP-error URL listed in this insight.",
      "Restore content or 301 to the closest relevant live URL (not homepage dump).",
      "Remove dead links from nav/sitemap pointing at those URLs.",
      "Request indexing on the final live URLs; re-crawl in 7 days.",
    ],
  },
  crawl_missing_title: {
    title: "Add missing page titles",
    metric: "SERP titles",
    effort: "30\u201390 min",
    estimatedROI: "+5\u201315% CTR on those pages",
    steps: [
      "Open each URL listed as missing <title>.",
      "Add a unique title \u226460 chars with primary keyword + brand on that exact page.",
      "Deploy and request indexing for each fixed URL.",
      "Verify titles in live source and SERP.",
    ],
  },
  crawl_missing_h1: {
    title: "Add missing H1s",
    metric: "On-page headings",
    effort: "30\u201390 min",
    estimatedROI: "+3\u201310% rankings on those pages",
    steps: [
      "Open each URL listed as missing H1.",
      "Add one clear H1 matching that page\u2019s search intent (not logo text).",
      "Ensure only one H1 per page; deploy.",
      "Remeasure rankings for the affected URLs.",
    ],
  },
  crawl_thin_content: {
    title: "Expand thin pages",
    metric: "Content depth",
    effort: "2\u20134 hrs",
    estimatedROI: "+10\u201325% traffic to those pages",
    steps: [
      "Open each thin URL with its word count from this insight.",
      "Expand unique content + FAQ/H2 sections that answer the ranking query.",
      "Do not pad with fluff; deploy + request indexing.",
      "Recheck rankings in 14 days.",
    ],
  },
  crawl_missing_meta: {
    title: "Add missing meta descriptions",
    metric: "SERP CTR",
    effort: "30\u201390 min",
    estimatedROI: "+5\u201310% CTR on those pages",
    steps: [
      "Open each URL listed as missing meta description.",
      "Write a unique meta \u2264155 chars with keyword + CTA on that page.",
      "Deploy; monitor CTR for those URLs in GSC.",
    ],
  },
  crawl_missing_schema: {
    title: "Add structured data markup",
    metric: "Rich results & visibility",
    effort: "1\u20132 hrs",
    estimatedROI: "+10\u201320% CTR via rich snippets",
    steps: [
      "Identify the page type (LocalBusiness, Article, Product, FAQ, etc.).",
      "Generate JSON-LD schema matching the page content.",
      "Add to <head> and validate with Google Rich Results Test.",
      "Deploy; request re-indexing. Monitor rich-result appearance in 14 days.",
    ],
  },
};

const severityOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
const effortMinutes: Record<string, number> = {
  "30 min": 30,
  "30\u201360 min": 45,
  "30\u201390 min": 60,
  "45\u201390 min": 67,
  "1 hr": 60,
  "1\u20132 hrs": 90,
  "1\u20133 hrs": 120,
  "2\u20134 hrs": 180,
  "2\u20136 hrs": 240,
  "half day+": 240,
};

type SeverityFilter = "all" | "high" | "medium" | "low";
type KindFilter = "problem" | "opportunity";
type QuickFilter = "all" | "quick_wins" | "high_impact" | "urgent";

function severityTone(severity: string): "danger" | "warning" | "default" {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "default";
}

function impactLabel(score: number): { label: string; tone: "proof" | "warning" | "danger" } {
  if (score >= 80) return { label: "Very High", tone: "proof" };
  if (score >= 60) return { label: "High", tone: "proof" };
  if (score >= 40) return { label: "Medium", tone: "warning" };
  return { label: "Low", tone: "danger" };
}

type Props = {
  insights: Insight[];
  clientId?: number;
  assigneePresets?: string[];
  /** Days since last datasource sync; ≥3 blocks Assign */
  staleDays?: number | null;
  tasks?: Task[];
  onCreateTask: (insight: Insight) => void;
  onQuickAssign?: (insight: Insight) => void;
  onResolve: (id: number) => void;
  onBulkResolve?: (ids: number[]) => void | Promise<void>;
  onBulkAssign?: (insights: Insight[]) => void | Promise<void>;
  onOpenActions?: () => void;
  /** Create a freeform task from a score-driven growth play */
  onCreateGrowthTask?: (play: HealthImprovement) => void;
  id?: string;
};

function GrowthPlaysPanel({
  improvements,
  healthScore,
  onOpenActions,
  onCreateGrowthTask,
  id,
}: {
  improvements: HealthImprovement[];
  healthScore: number;
  onOpenActions?: () => void;
  onCreateGrowthTask?: (play: HealthImprovement) => void;
  id?: string;
}) {
  return (
    <div id={id} className="animate-fade-up animate-fade-up-delay-2 mb-8">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-label text-kinexis-signal">Score-driven growth plays</p>
          <p className="text-muted mt-0.5 text-[13px]">
            Health is {Math.round(healthScore)}/100 with no open incident alerts. These plays target
            the weakest pillars so agents can still raise the score.
          </p>
        </div>
        {onOpenActions && (
          <Button variant="soft" size="sm" onClick={onOpenActions}>
            <ArrowRight size={12} /> Generate AI plan
          </Button>
        )}
      </div>
      <div className="space-y-2">
        {improvements.map((play, idx) => (
          <div key={play.id} className="panel motion-micro overflow-hidden p-4">
            <div className="flex items-start gap-3">
              <span className="font-mono-data flex h-7 w-7 shrink-0 items-center justify-center bg-surface-lighter text-[12px] font-semibold text-kinexis-focus">
                {idx + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[14px] font-medium text-ink">{play.title}</p>
                  <Badge tone="signal">{play.effort}</Badge>
                  <span className="text-muted text-[11px]">{play.metric}</span>
                </div>
                <p className="text-muted mt-1 text-[12px] leading-relaxed">{play.detail}</p>
                {play.estimatedROI && (
                  <p className="mt-2 flex items-center gap-1 text-[11px] font-medium text-kinexis-proof">
                    <TrendingUp size={11} />
                    {formatTypicalRoi(play.estimatedROI)}
                  </p>
                )}
                <CollapsibleSection
                  label={`${play.steps.length} step${play.steps.length === 1 ? "" : "s"}`}
                  defaultOpen={idx === 0}
                  className="!mt-2"
                >
                  <ol className="mb-3 list-decimal space-y-2 pl-5">
                    {play.steps.map((step, si) => (
                      <li key={si} className="text-[12px] leading-relaxed text-ink-dim">
                        {step}
                      </li>
                    ))}
                  </ol>
                  {onCreateGrowthTask && (
                    <Button size="sm" onClick={() => onCreateGrowthTask(play)}>
                      <Zap size={11} /> Assign
                    </Button>
                  )}
                </CollapsibleSection>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function NextSteps({
  insights,
  clientId,
  assigneePresets = [],
  staleDays = null,
  tasks = [],
  onCreateTask,
  onQuickAssign,
  onResolve,
  onBulkResolve,
  onBulkAssign,
  onOpenActions,
  onCreateGrowthTask,
  id,
}: Props) {
  const [kindFilter, setKindFilter] = useState<KindFilter>("problem");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [effectivenessByType, setEffectivenessByType] = useState<Record<string, FixEffectiveness>>(
    {}
  );

  const assignBlocked = staleDays != null && staleDays >= 3;
  const shippedInsightIds = useMemo(
    () =>
      new Set(tasks.filter((t) => t.status === "done" && t.insight_id).map((t) => t.insight_id!)),
    [tasks]
  );

  useEffect(() => {
    let cancelled = false;
    void api.actions
      .fixEffectiveness()
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, FixEffectiveness> = {};
        for (const row of res.fixes || []) {
          map[row.fix_type] = row;
        }
        setEffectivenessByType(map);
      })
      .catch(() => {
        if (!cancelled) setEffectivenessByType({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const guardedQuickAssign = (insight: Insight) => {
    if (assignBlocked || !onQuickAssign) return;
    onQuickAssign(insight);
  };

  const guardedCreateTask = (insight: Insight) => {
    if (assignBlocked) return;
    onCreateTask(insight);
  };

  const { totalOpen, unresolved } = useMemo(() => {
    const problems = insights.filter((i) => !i.resolved && insightKind(i) === "problem").length;
    const q = search.trim().toLowerCase();
    let list = [...insights]
      .filter((i) => !i.resolved)
      .filter((i) => insightKind(i) === kindFilter)
      .filter((i) => severityFilter === "all" || i.severity === severityFilter);

    if (quickFilter === "quick_wins") {
      list = list.filter((i) => {
        const book = PLAYBOOKS[i.type];
        const mins = book ? (effortMinutes[book.effort] ?? 120) : 120;
        return mins <= 60 && (i.priority_score ?? 0) >= 40;
      });
    } else if (quickFilter === "high_impact") {
      list = list.filter((i) => (i.priority_score ?? 0) >= 70);
    } else if (quickFilter === "urgent") {
      list = list.filter((i) => i.severity === "high");
    }

    if (q) {
      list = list.filter((i) => {
        return (
          i.message.toLowerCase().includes(q) ||
          (i.recommended_action || "").toLowerCase().includes(q) ||
          i.type.toLowerCase().includes(q) ||
          i.severity.toLowerCase().includes(q)
        );
      });
    }

    list.sort((a, b) => {
      const scoreDiff = (b.priority_score ?? 0) - (a.priority_score ?? 0);
      if (scoreDiff !== 0) return scoreDiff;
      return (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9);
    });

    return {
      totalOpen:
        problems + insights.filter((i) => !i.resolved && insightKind(i) === "opportunity").length,
      unresolved: list,
    };
  }, [insights, kindFilter, severityFilter, quickFilter, search]);

  const [apiTopPlay, setApiTopPlay] = useState<HealthImprovement | null>(null);
  const [apiHealthScore, setApiHealthScore] = useState<number | null>(null);

  useEffect(() => {
    if (!clientId) {
      setApiTopPlay(null);
      setApiHealthScore(null);
      return;
    }
    let cancelled = false;
    api.health
      .forClient(clientId)
      .then((res) => {
        if (cancelled) return;
        const score =
          typeof res.health_score === "number" && Number.isFinite(res.health_score)
            ? res.health_score
            : null;
        setApiHealthScore(score);
        if (res.top_action?.title) {
          setApiTopPlay({
            id: "api-top-action",
            areaId: "visibility",
            title: res.top_action.title,
            detail: res.top_action.detail || "",
            steps: [],
            effort: res.top_action.effort || "medium",
            estimatedROI: "",
            metric: "",
          });
        } else {
          setApiTopPlay(null);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setApiTopPlay(null);
        setApiHealthScore(null);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const openProblems = useMemo(
    () => insights.filter((i) => !i.resolved && insightKind(i) === "problem").length,
    [insights]
  );

  const showGrowthPlays = Boolean(
    apiHealthScore != null &&
    apiHealthScore > 0 &&
    apiHealthScore < 85 &&
    apiTopPlay &&
    openProblems === 0
  );

  const visible = unresolved;

  const toggleSelected = (insightId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(insightId)) next.delete(insightId);
      else next.add(insightId);
      return next;
    });
  };

  const toggleSelectVisible = () => {
    const ids = visible.map((i) => i.id);
    const allOn = ids.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      if (allOn) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  };

  const runBulkResolve = async () => {
    if (!onBulkResolve || selected.size === 0) return;
    setBulkBusy(true);
    try {
      await onBulkResolve([...selected]);
      setSelected(new Set());
    } finally {
      setBulkBusy(false);
    }
  };

  const runBulkAssign = async () => {
    if (!onBulkAssign || selected.size === 0 || assignBlocked) return;
    const picks = unresolved.filter((i) => selected.has(i.id));
    setBulkBusy(true);
    try {
      await onBulkAssign(picks);
      setSelected(new Set());
    } finally {
      setBulkBusy(false);
    }
  };

  if (totalOpen === 0) {
    if (showGrowthPlays && apiTopPlay && apiHealthScore != null) {
      return (
        <GrowthPlaysPanel
          id={id}
          improvements={[apiTopPlay]}
          healthScore={apiHealthScore}
          onOpenActions={onOpenActions}
          onCreateGrowthTask={onCreateGrowthTask}
        />
      );
    }
    return (
      <div id={id} className="animate-fade-up animate-fade-up-delay-2 mb-8">
        <EmptyState
          title="No open issues"
          description="All problems and opportunities are resolved. Run a sync to refresh detections, or generate an AI plan to find new growth experiments."
          action={
            onOpenActions ? (
              <Button variant="soft" onClick={onOpenActions}>
                <ArrowRight size={12} /> Generate AI plan
              </Button>
            ) : undefined
          }
        />
      </div>
    );
  }

  const kindLabel = kindFilter === "problem" ? "must-fix problem" : "growth opportunity";
  const avgScore =
    unresolved.length > 0
      ? unresolved.reduce((s, i) => s + (i.priority_score ?? 0), 0) / unresolved.length
      : 0;
  const highCount = unresolved.filter((i) => i.severity === "high").length;
  const quickWins = unresolved.filter((i) => {
    const book = PLAYBOOKS[i.type];
    const mins = book ? (effortMinutes[book.effort] ?? 120) : 120;
    return mins <= 60 && (i.priority_score ?? 0) >= 40;
  }).length;

  return (
    <div id={id} className="animate-fade-up animate-fade-up-delay-2 mb-8">
      {assignBlocked && (
        <Panel padding="md" className="mb-4 border-kinexis-signal/30 bg-kinexis-signal/5">
          <p className="text-sm font-medium text-ink">
            Assign blocked — data is {staleDays}d stale
          </p>
          <p className="text-muted mt-1 text-xs">
            Sync connectors before creating work so rankings and CTR targets stay trustworthy.
          </p>
        </Panel>
      )}
      {showGrowthPlays && apiTopPlay && apiHealthScore != null && (
        <CollapsibleSection label="Growth plays" defaultOpen={false} className="!mt-0">
          <GrowthPlaysPanel
            improvements={[apiTopPlay]}
            healthScore={apiHealthScore}
            onOpenActions={onOpenActions}
            onCreateGrowthTask={onCreateGrowthTask}
          />
        </CollapsibleSection>
      )}
      <CollapsibleSection label="Queue summary" defaultOpen={false} className="!mt-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
          <span>
            <span className="text-muted">Open </span>
            <span className="font-mono-data font-semibold text-ink">{totalOpen}</span>
          </span>
          <span>
            <span className="text-muted">Avg priority </span>
            <span
              className={`font-mono-data font-semibold ${avgScore >= 60 ? "text-kinexis-risk" : avgScore >= 40 ? "text-kinexis-signal" : "text-ink"}`}
            >
              {avgScore > 0 ? Math.round(avgScore) : "\u2014"}
            </span>
          </span>
          <span>
            <span className="text-muted">High severity </span>
            <span
              className={`font-mono-data font-semibold ${highCount > 0 ? "text-kinexis-risk" : "text-kinexis-proof"}`}
            >
              {highCount}
            </span>
          </span>
          <span>
            <span className="text-muted">Quick wins </span>
            <span
              className={`font-mono-data font-semibold ${quickWins > 0 ? "text-kinexis-proof" : "text-ink"}`}
            >
              {quickWins}
            </span>
          </span>
        </div>
      </CollapsibleSection>

      {/* Single top fix — one CTA, no competing top-3 / top-story heroes */}
      {unresolved[0] && (
        <Panel className="motion-micro mb-4" padding="lg">
          <p className="text-label text-kinexis-focus">Top fix</p>
          <p className="mt-1.5 text-[15px] font-semibold leading-snug text-ink">
            {PLAYBOOKS[unresolved[0].type]?.title ||
              unresolved[0].type.replace(/_/g, " ") ||
              unresolved[0].recommended_action ||
              unresolved[0].message}
          </p>
          <p className="text-muted mt-1.5 line-clamp-2 text-xs leading-relaxed">
            {unresolved[0].recommended_action || unresolved[0].message}
          </p>
          <div className="mt-3">
            <Button
              variant="primary"
              size="sm"
              disabled={assignBlocked}
              title={
                assignBlocked ? `Sync required — data is ${staleDays}d stale` : "Assign this fix"
              }
              onClick={() => {
                const top = unresolved[0];
                if (!top) return;
                if (onQuickAssign) guardedQuickAssign(top);
                else guardedCreateTask(top);
              }}
            >
              Assign <Zap size={11} />
            </Button>
          </div>
        </Panel>
      )}

      {/* Filter bar */}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="section-label">
            {kindFilter === "problem" ? "Problems" : "Opportunities"}
          </h2>
          <p className="mt-1 text-sm font-medium text-ink-secondary">
            {unresolved.length} {kindLabel}
            {unresolved.length === 1 ? "" : "s"}
            {severityFilter !== "all" ? ` (${severityFilter})` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <SegmentedControl
            size="sm"
            ariaLabel="Queue type"
            value={kindFilter}
            onChange={(k) => {
              setKindFilter(k);
            }}
            options={[
              { id: "problem" as const, label: "Problems" },
              { id: "opportunity" as const, label: "Opps" },
            ]}
          />
          <SegmentedControl
            size="sm"
            ariaLabel="Severity filter"
            value={severityFilter}
            onChange={(s) => {
              setSeverityFilter(s);
            }}
            options={(["all", "high", "medium", "low"] as const).map((s) => ({
              id: s,
              label: s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1),
            }))}
          />
          {onOpenActions && (
            <Button variant="soft" size="sm" onClick={onOpenActions}>
              AI plan <ArrowRight size={11} />
            </Button>
          )}
        </div>
      </div>

      {/* Quick filter chips + list */}
      <div className="animate-state-settle">
      {/* Quick filter chips */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {(
          [
            ["all", "All"],
            ["quick_wins", "Quick wins"],
            ["high_impact", "High impact"],
            ["urgent", "Urgent"],
          ] as [QuickFilter, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setQuickFilter(key)}
            className={`chip ${quickFilter === key ? "chip-active" : ""}`}
          >
            {key === "quick_wins" && <Zap size={10} />}
            {key === "high_impact" && <TrendingUp size={10} />}
            {key === "urgent" && <Flag size={10} />}
            {label}
            {key === "all"
              ? ` (${unresolved.length})`
              : key === "quick_wins"
                ? ` (${quickWins})`
                : ""}
          </button>
        ))}
      </div>

      {/* Search + bulk actions */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="w-full max-w-xs">
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
            }}
            placeholder="Search Fix queue\u2026"
            aria-label="Search Fix queue"
          />
        </div>
        {unresolved.length > 0 && (
          <Button variant="ghost" size="sm" onClick={toggleSelectVisible}>
            {visible.every((i) => selected.has(i.id)) ? "Clear selection" : "Select visible"}
          </Button>
        )}
        {selected.size > 0 && (
          <>
            <span className="text-muted font-mono-data text-[11px]">{selected.size} selected</span>
            {onBulkAssign && (
              <Button
                variant="soft"
                size="sm"
                disabled={bulkBusy || assignBlocked}
                title={
                  assignBlocked ? `Sync required — data is ${staleDays}d stale` : "Assign selected"
                }
                onClick={() => void runBulkAssign()}
              >
                Assign selected
              </Button>
            )}
            {onBulkResolve && (
              <Button
                variant="ghost"
                size="sm"
                disabled={bulkBusy}
                onClick={() => void runBulkResolve()}
              >
                Won&apos;t-fix / resolve selected
              </Button>
            )}
          </>
        )}
      </div>

      {unresolved.length === 0 && (
        <EmptyState
          className="mb-3 !py-6"
          title={
            quickFilter !== "all"
              ? "No items match this preset"
              : kindFilter === "problem"
                ? severityFilter === "all"
                  ? "No must-fix problems"
                  : `No ${severityFilter}-severity problems`
                : severityFilter === "all"
                  ? "No growth opportunities"
                  : `No ${severityFilter}-severity opportunities`
          }
          description="Try a different filter or generate an AI plan."
        />
      )}

      <div className="space-y-3">
        {visible.map((insight, idx) => {
          const checklist = PLAYBOOKS[insight.type];
          const steps = concreteSteps(insight) || checklist?.steps || [];
          const impact = impactLabel(insight.priority_score ?? 0);
          const roi = formatRoiBadge(insight.type, checklist?.estimatedROI, effectivenessByType);
          const conf = confidenceMeta(insight);
          const shipped = shippedInsightIds.has(insight.id);

          return (
            <Panel
              key={insight.id}
              padding={false}
              className="motion-micro overflow-hidden hover:border-[color:var(--border-strong)]"
            >
              <div className="p-4">
                <div className="flex items-start gap-4">
                  <label className="mt-2 shrink-0">
                    <input
                      type="checkbox"
                      className="rounded border-[color:var(--border-default)]"
                      checked={selected.has(insight.id)}
                      onChange={() => toggleSelected(insight.id)}
                      aria-label={`Select insight ${insight.id}`}
                    />
                  </label>
                  <div
                    className="text-muted font-mono-data flex h-7 w-7 shrink-0 items-center justify-center border border-[color:var(--border-default)] text-[11px] font-medium"
                    style={{ borderRadius: "var(--radius-sm)" }}
                  >
                    {String(idx + 1).padStart(2, "0")}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                      <Badge tone={severityTone(insight.severity)}>{insight.severity}</Badge>
                      <Badge tone={impact.tone}>{impact.label}</Badge>
                      {conf && (
                        <span title={conf.title}>
                          <Badge tone={conf.tone}>{conf.label}</Badge>
                        </span>
                      )}
                      {checklist && (
                        <span className="font-mono-data text-muted text-xs">
                          <Clock size={10} className="mr-0.5 inline" />
                          {checklist.effort}
                        </span>
                      )}
                      {roi && (
                        <span
                          className={`font-mono-data text-xs ${
                            roi.measured ? "text-kinexis-proof" : "text-muted"
                          }`}
                        >
                          <TrendingUp size={10} className="mr-0.5 inline" />
                          {roi.label}
                        </span>
                      )}
                      <span className="font-mono-data text-muted text-xs">
                        score {Math.round(insight.priority_score ?? 0)}
                      </span>
                    </div>
                    <h3 className="text-[14px] font-medium tracking-tight text-ink">
                      {checklist?.title || insight.type.replace(/_/g, " ")}
                    </h3>
                    <p className="text-muted mt-1.5 whitespace-pre-wrap text-xs leading-relaxed">
                      {insight.message}
                    </p>
                    {insight.recommended_action && !concreteSteps(insight) && (
                      <p className="mt-2.5 flex items-start gap-2 text-xs text-kinexis-focus">
                        <Lightbulb size={12} strokeWidth={1.75} className="mt-0.5 shrink-0" />
                        <span className="whitespace-pre-wrap">{insight.recommended_action}</span>
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    <Button
                      size="sm"
                      disabled={assignBlocked}
                      onClick={() =>
                        onQuickAssign ? guardedQuickAssign(insight) : guardedCreateTask(insight)
                      }
                      title={
                        assignBlocked
                          ? `Sync required — data is ${staleDays}d stale`
                          : `Assign to ${assigneePresets[0] || "Unassigned"}`
                      }
                    >
                      <Plus size={12} /> Assign
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onResolve(insight.id)}
                      className="hover:!bg-kinexis-focus/10 hover:!text-kinexis-focus"
                      title={
                        shipped
                          ? "Resolve as shipped (linked work done)"
                          : "Mark won't-fix (no completed task yet)"
                      }
                    >
                      {shipped ? "Resolve" : "Won't fix"}
                    </Button>
                  </div>
                </div>

                {steps.length > 0 && (
                  <div className="ml-0 mt-4 border-t border-[color:var(--border-subtle)] pt-3 sm:ml-12">
                    <CollapsibleSection
                      label={`Fix checklist (${steps.length})`}
                      defaultOpen={idx < 3}
                      className="!mt-0"
                    >
                      <ol className="space-y-2">
                        {steps.map((step, i) => (
                          <li
                            key={i}
                            className="flex gap-2 text-xs leading-relaxed text-ink-secondary"
                          >
                            <span className="font-mono-data w-4 shrink-0 pt-px text-ink-dim">
                              {i + 1}.
                            </span>
                            <span className="whitespace-pre-wrap">{step}</span>
                          </li>
                        ))}
                      </ol>
                    </CollapsibleSection>
                  </div>
                )}
              </div>
            </Panel>
          );
        })}
      </div>
      </div>
    </div>
  );
}

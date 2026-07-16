"""
Advanced playbooks — success-metric oriented, agent-executable.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Advanced playbooks — success-metric oriented, agent-executable
# ---------------------------------------------------------------------------

PLAYBOOKS: dict[str, dict[str, Any]] = {
    "content_opportunity": {
        "title": "Win the rising query → more clicks & rankings",
        "north_star": "gsc.clicks + gsc.position improvement on the target query",
        "metric": "Impressions → clicks & rankings",
        "effort": "2–4 hrs",
        "success_formula": (
            "Rising impressions mean demand exists. Capture it by matching intent on-page "
            "(title/H1/section), then earn clicks via stronger SERP copy and internal links. "
            "Success = more clicks on this query within 14–28 days, position moving toward top 10."
        ),
        "impact_model": "If impressions stay flat and CTR rises 1–3 pts (or position improves 2–5 spots), clicks scale with demand.",
        "deliverables": [
            "Updated <title>, meta description, H1 aligned to the query intent",
            "New or expanded on-page section (800–1500 words) targeting the query",
            "2–3 internal links with descriptive anchors from related pages",
            "Sitemap/lastmod touch + indexing request for the URL",
        ],
        "technical_spec": [
            "Locate ranking URL (GSC Performance → Queries → Pages, or site search for the query).",
            "Audit intent: informational vs commercial — match page type (guide vs service/landing).",
            "Title formula: `{Primary Query} | {Benefit or Location} | {Brand}` ≤60 chars.",
            "H1 = primary query or close paraphrase; first 100 words answer the intent.",
            "Add H2 section titled with the query or a natural variant; include FAQ if PAA-heavy.",
            "Internal links: from 2–3 topical pages; anchor text ≈ query (not 'click here').",
            "Do not create thin doorway pages; expand the best existing URL when possible.",
        ],
        "copy_templates": [
            "Title: `{Query} — {Outcome in 2026} | {Brand}`",
            "Meta: `Get {benefit}. {Differentiator}. Free estimate / Learn how — {Brand}.`",
            "H2: `What to know about {query}` or `How we handle {query}`",
        ],
        "steps": [
            "Open GSC → Performance → filter to this query; note current page & position.",
            "Audit the ranking URL: does H1/title match the query intent?",
            "Add a dedicated section or landing page targeting the query (800–1500 words).",
            "Rewrite title/meta for click appeal while keeping the keyword early.",
            "Internal-link from 2–3 related pages; resubmit URL in GSC.",
            "Recheck impressions, clicks, and position in 14 days.",
        ],
        "agent_notes": [
            "Primary KPI: increase clicks for this query (not just word count).",
            "Prefer upgrading the existing ranking URL over creating a competing URL.",
            "Ship title + H1 + body section + internal links in one deploy.",
            "After deploy: request indexing; document before/after title and URL.",
        ],
        "acceptance": [
            "Target query (or clear variant) appears in <title> and H1 or a dedicated H2.",
            "New/expanded content is live, unique, and useful (not spun filler).",
            "≥2 internal links point to the page with descriptive anchors.",
            "Page returns 200; no accidental noindex; in sitemap.",
            "Success contract: query clicks up OR position improved within 14–28 days.",
        ],
        "verification": [
            "Day 0: record query clicks, impressions, CTR, position (28d).",
            "Day 3–7: confirm Google has recrawled (URL Inspection).",
            "Day 14: compare query clicks vs Day 0 — target ↑ clicks or ↑ CTR.",
            "Day 28: confirm sustained lift; if flat, iterate title/meta again.",
        ],
        "anti_patterns": [
            "Keyword stuffing titles",
            "Duplicate near-identical landing pages",
            "Changing URL slug without 301",
            "Publishing <300 words of fluff",
        ],
        "metrics_to_watch": ["gsc.impressions", "gsc.clicks", "gsc.ctr", "gsc.position"],
    },
    "ctr_opportunity": {
        "title": "Lift CTR → convert impressions into clicks",
        "north_star": "gsc.ctr and gsc.clicks for the underperforming query/page",
        "metric": "CTR & clicks",
        "effort": "30–60 min",
        "success_formula": (
            "You already have impressions. Every CTR point recovered = free clicks. "
            "Fix SERP title + meta only (fastest win). Success = CTR moves toward expected-for-position "
            "and absolute clicks rise within 7–14 days."
        ),
        "impact_model": "Extra clicks ≈ impressions × (target_CTR − current_CTR). Prioritize high-impression gaps first.",
        "deliverables": [
            "New <title> ≤60 chars with primary keyword + benefit/number/location",
            "New meta description ≤155 chars with CTA + differentiator",
            "No slug change unless required; indexing request after deploy",
        ],
        "technical_spec": [
            "Identify the exact ranking URL for the query (GSC → query → Pages).",
            "Incognito SERP check: note top 3 competitor titles (length, numbers, power words).",
            "Rewrite title: keyword near front; add number, year, or outcome; avoid truncation.",
            "Rewrite meta: problem → benefit → CTA; include a differentiator vs competitors.",
            "Ensure unique title across the site (no duplicates).",
            "Deploy; request indexing; do not change H1 unless it conflicts with new title intent.",
        ],
        "copy_templates": [
            "Title patterns: `{Query}: {Benefit}` · `{N} Tips for {Query}` · `{Query} Near {City} | {Brand}`",
            "Meta pattern: `{Who it's for}. {Proof or differentiator}. {CTA} today.`",
            "Power words: Free, Proven, Local, Same-Day, Guaranteed, 2026, Expert, Custom",
        ],
        "steps": [
            "Search the query in an incognito window; screenshot top 3 titles/metas.",
            "Rewrite title (≤60 chars) with primary keyword + benefit/number.",
            "Rewrite meta (≤155 chars) with a clear CTA and differentiator.",
            "Deploy; request indexing; compare CTR and clicks in 7–14 days.",
        ],
        "agent_notes": [
            "This is a SERP-copy fix — maximize click yield from existing impressions.",
            "Calculate opportunity: impressions × CTR gap = potential monthly clicks.",
            "Ship title+meta together; keep brand voice from agency profile.",
            "If multiple queries share one URL, optimize for the highest-impression query first.",
        ],
        "acceptance": [
            "Live page source shows new title and meta.",
            "Title includes primary keyword; meta has a clear CTA.",
            "No duplicate title tags introduced.",
            "Success contract: CTR ↑ toward expected AND clicks ↑ within 14 days.",
        ],
        "verification": [
            "Day 0: baseline query/page CTR, clicks, impressions.",
            "Day 7: early CTR movement (directionally up).",
            "Day 14: CTR gap to expected reduced by ≥30% OR clicks +10%+.",
            "If no lift: A/B a stronger number/benefit in the title.",
        ],
        "anti_patterns": [
            "Clickbait that mismatches page content (hurts bounce + rankings)",
            "ALL CAPS titles",
            "Identical titles across many pages",
            "Meta stuffed with keywords and no CTA",
        ],
        "metrics_to_watch": ["gsc.ctr", "gsc.clicks", "gsc.impressions"],
    },
    "decline_alert": {
        "title": "Stop the traffic drop → recover clicks",
        "north_star": "Restore gsc.clicks / gsc.impressions WoW to prior baseline",
        "metric": "Clicks / impressions",
        "effort": "1–2 hrs",
        "success_formula": (
            "A WoW click/impression drop compounds into lost leads. Triage indexing, 404s, "
            "canonicals, and content removals on dropped URLs first. Success = stop the bleed "
            "within 7 days, then recover toward prior click levels in 14–28 days."
        ),
        "impact_model": "Preventing further decline protects existing click volume; recovery restores lost sessions/leads.",
        "deliverables": [
            "List of dropped URLs/queries with root cause per URL",
            "Fixes for 404/redirect/robots/canonical/content issues",
            "Updated sitemap + re-crawl requests",
        ],
        "technical_spec": [
            "GSC → Pages/Queries: sort by click/impression change; export top losers.",
            "For each top URL: check HTTP status, canonical, robots, noindex, soft 404.",
            "Fix chains: 404→relevant 301; blocked resources; accidental noindex.",
            "If content was removed/thinned, restore or rewrite to prior quality bar.",
            "Submit sitemap; URL Inspection → Request indexing on money pages.",
            "Check Manual actions & Security issues in GSC.",
        ],
        "copy_templates": [],
        "steps": [
            "Open the worst dropped URL named in this insight (not the whole site).",
            "Confirm HTTP 200, no accidental noindex, canonical not pointing away.",
            "GSC URL Inspection → request indexing if excluded or soft-404.",
            "Fix 404/redirect chains; restore thinned content on that exact page.",
            "Repeat for the next dropped URLs listed; remeasure site clicks in 7 days.",
        ],
        "agent_notes": [
            "Priority is stop-loss on clicks — fix technical blockers before new content.",
            "Document root cause per URL in the PR/handoff.",
            "Do not mass-redirect unrelated pages; preserve relevance.",
        ],
        "acceptance": [
            "Top dropped URLs return 200 or intentional relevant 301.",
            "No accidental noindex/robots block on money pages.",
            "Sitemap includes recovered URLs.",
            "Success contract: WoW click decline halted; recovery trend within 14–28 days.",
        ],
        "verification": [
            "Day 0: snapshot site clicks/impressions + top dropped URLs.",
            "Day 3: confirm fixed URLs are indexable (URL Inspection).",
            "Day 7: WoW decline slowed or reversed.",
            "Day 28: clicks within 10% of pre-drop baseline or improving.",
        ],
        "anti_patterns": [
            "Ignoring indexing exclusions",
            "301 everything to homepage",
            "Deleting pages that still have impressions",
        ],
        "metrics_to_watch": ["gsc.clicks", "gsc.impressions", "gsc.position"],
    },
    "zero_click_alert": {
        "title": "Turn zero-click impressions into clicks",
        "north_star": "gsc.clicks from high-impression / near-zero-click queries",
        "metric": "Clicks from high-impression queries",
        "effort": "1–2 hrs",
        "success_formula": (
            "High impressions + ~0 clicks = wasted visibility. Classify intent first: "
            "local commercial → rewrite title/meta for click appeal; informational → "
            "add a clear on-page answer with CTA. Success = measurable clicks appear "
            "within 14 days on that query."
        ),
        "impact_model": "Even a 1–2% CTR on a high-impression query unlocks material click volume.",
        "deliverables": [
            "Improved title/meta for click appeal",
            "Intent-matched on-page answer block (40–60 words) when informational",
            "CTA linking to relevant service page",
        ],
        "technical_spec": [
            "Classify intent: local/commercial (service+city) vs informational (how-to/cost/guide).",
            "If local commercial: rewrite title (≤60 chars) with primary keyword + location/benefit; "
            "rewrite meta (≤155 chars) with clear CTA.",
            "If informational: put a direct answer under a matching H2 in first screenful; "
            "follow with CTA to service page.",
            "Only consider FAQ/HowTo schema when the page has real FAQ content AND the SERP "
            "shows rich results for that format — never as a default.",
        ],
        "copy_templates": [
            "Local commercial title: `{Service} in {City} | {Benefit} | {Brand}`",
            "Informational answer block: `{Query} is {clear 1–2 sentence answer}.`",
        ],
        "steps": [
            "SERP-check the query: classify intent (local commercial vs informational).",
            "If local commercial: rewrite title/meta on the ranking URL for click appeal.",
            "If informational: add answer block + CTA on the ranking page.",
            "Request indexing; track clicks on that query for 2 weeks.",
        ],
        "agent_notes": [
            "Goal is first clicks from wasted impressions — measure query clicks.",
            "Local commercial queries: winning the click matters more than winning the snippet.",
            "For cost/info queries, a CTA after the answer is better than a zero-click snippet.",
        ],
        "acceptance": [
            "Title/meta updated on ranking URL (commercial) OR answer block live (informational).",
            "Success contract: query gets sustained clicks (CTR > 0.5% or clear ↑) in 14 days.",
        ],
        "verification": [
            "Day 0: impressions high, clicks ~0.",
            "Day 14: clicks > 0 and rising; CTR no longer ~0.",
        ],
        "anti_patterns": [
            "Defaulting to FAQ schema on local commercial queries",
            "Hidden text for snippets",
            "Zero-click snippet as success — clicks are the metric",
        ],
        "metrics_to_watch": ["gsc.clicks", "gsc.ctr", "gsc.impressions"],
    },
    "cro_opportunity": {
        "title": "Convert high-traffic pages → more leads/revenue",
        "north_star": "ga4.key_events / cvr on the landing page (and downstream leads)",
        "metric": "Conversion rate",
        "effort": "2–6 hrs",
        "success_formula": (
            "Traffic without conversions wastes click acquisition. One primary CTA, clearer offer, "
            "shorter forms, trust near CTA. Success = CVR and key_events ↑ within 14 days "
            "without tanking sessions."
        ),
        "impact_model": "Extra conversions ≈ sessions × CVR lift. A +0.5–1.0 pt CVR on a busy page is high leverage.",
        "deliverables": [
            "Single primary CTA above the fold (mobile + desktop)",
            "Shortened form or stronger trust cluster near CTA",
            "Hero copy aligned to traffic intent",
            "Analytics events still firing",
        ],
        "technical_spec": [
            "Identify landing URL from finding; open Clarity recordings (rage clicks, dead ends).",
            "Map fold: one primary CTA; demote secondary links/buttons.",
            "Form: remove non-essential fields; keep attribution fields if CRM needs them.",
            "Add trust: reviews, logos, guarantees, response-time near CTA.",
            "Preserve dataLayer / gtag / HubSpot form events when changing markup.",
            "Optional: A/B headline or CTA label for 14 days.",
        ],
        "copy_templates": [
            "CTA: `Get a free estimate` · `Book a consult` · `Start your project`",
            "Hero: `{Outcome} for {audience} in {location} — without {pain}.`",
        ],
        "steps": [
            "Open the page + Clarity recordings for that URL.",
            "Map the primary CTA above the fold; remove competing CTAs.",
            "Shorten forms (fewer fields) or add trust signals near the CTA.",
            "A/B test headline or CTA copy for 2 weeks.",
            "Watch key_events / CVR on that landing page.",
        ],
        "agent_notes": [
            "Clicks upstream only matter if this page converts — optimize for key_events.",
            "Do not remove tracking when restyling forms.",
            "Mobile fold is the default design target.",
        ],
        "acceptance": [
            "Primary CTA visible without scrolling on mobile and desktop.",
            "Form simplified and/or trust added near CTA.",
            "Conversion events still fire (test submit).",
            "Success contract: landing CVR or key_events ↑ within 14 days.",
        ],
        "verification": [
            "Day 0: sessions, key_events, CVR for URL.",
            "Day 14: CVR ↑ or key_events/session ↑; bounce not worse by >5 pts unless intentional.",
        ],
        "anti_patterns": [
            "Multiple equal CTAs fighting for attention",
            "Broken thank-you / event tracking",
            "Interstitials that block the form on mobile",
        ],
        "metrics_to_watch": ["ga4.key_events", "ga4.cvr", "ga4.sessions", "ga4.bounce_rate"],
    },
    "error_spike_alert": {
        "title": "Clean bad traffic → protect real sessions & conversions",
        "north_star": "Stable ga4.sessions + lower threat/bot noise",
        "metric": "Sessions & threat rate",
        "effort": "45–90 min",
        "success_formula": (
            "Bot/attack traffic distorts analytics and can hurt real users. Tighten WAF/bot rules "
            "without blocking Googlebot or customers. Success = threats down, real sessions stable."
        ),
        "impact_model": "Protects conversion tracking quality and site availability for real clickers.",
        "deliverables": [
            "Cloudflare rule changes documented",
            "Confirmation Googlebot/Bingbot not blocked",
            "Re-check of GA4 sessions post-change",
        ],
        "technical_spec": [
            "Cloudflare → Security Events: note paths, ASNs, countries, bot scores.",
            "Tighten WAF / Bot Fight for abusive patterns; prefer Managed Challenge.",
            "Allowlist known good bots; verify robots and critical APIs still work.",
            "Re-check GA4 sessions and conversion volume next week.",
        ],
        "copy_templates": [],
        "steps": [
            "Cloudflare → Security Events: note attack/bot patterns.",
            "Tighten WAF / bot fight mode for abusive ASNs or paths.",
            "Confirm real users still pass (challenge vs block).",
            "Re-check GA4 sessions next week.",
        ],
        "agent_notes": [
            "Do not hard-block entire countries unless agency approves.",
            "Document rules so they can be rolled back.",
        ],
        "acceptance": [
            "Abusive patterns reduced in Security Events.",
            "Real-user pages load without unexpected blocks.",
            "Success contract: threat rate ↓; GA4 sessions not collapsed.",
        ],
        "verification": [
            "Day 1: security events quieter.",
            "Day 7: GA4 sessions/conversions stable vs pre-change.",
        ],
        "anti_patterns": ["Blocking Googlebot", "Challenge loops on forms"],
        "metrics_to_watch": ["cloudflare.threats", "ga4.sessions", "ga4.key_events"],
    },
    "pagespeed_urgent": {
        "title": "Fix Core Web Vitals (urgent) → rankings + conversion",
        "north_star": "Mobile performance ≥70; protect gsc.clicks and ga4.cvr",
        "metric": "Mobile performance & rankings",
        "effort": "half day+",
        "success_formula": (
            "Slow mobile pages lose rankings and conversions. Fix LCP/TBT/CLS on the cited URL. "
            "Success = mobile score ≥70 and no drop in clicks; ideally CVR stable/up."
        ),
        "impact_model": "CWV fixes support ranking stability and reduce bounce — more of the earned clicks convert.",
        "deliverables": [
            "Optimized LCP image (WebP/AVIF, sized, preloaded)",
            "Deferred non-critical JS; trimmed unused CSS",
            "Caching/CDN headers where controllable",
            "Before/after PageSpeed mobile scores",
        ],
        "technical_spec": [
            "Run PageSpeed Insights mobile on the exact Target URL; save JSON/summary.",
            "LCP: compress/resize hero; width/height attrs; preload LCP image; avoid lazy on LCP.",
            "TBT: defer non-critical JS; split bundles; remove unused third parties.",
            "CLS: reserve space for images/ads/embeds; avoid inserting content above fold.",
            "Enable caching/CDN; retest until score ≥70.",
            "Retest on production URL after deploy (not only localhost).",
        ],
        "copy_templates": [],
        "steps": [
            "Run PageSpeed Insights on the URL (mobile).",
            "Compress/resize hero images; serve WebP/AVIF.",
            "Defer non-critical JS; remove unused CSS.",
            "Enable caching / CDN; retest until score ≥70.",
        ],
        "agent_notes": [
            "Speed is a success-metric unlocker — treat ≥70 mobile as a hard gate.",
            "Prioritize LCP element identified by PSI diagnostics.",
            "Don't break analytics/chat widgets without a plan — defer, don't delete blindly.",
        ],
        "acceptance": [
            "Mobile PageSpeed score ≥70 on the target URL.",
            "LCP image optimized (modern format, dimensions, preload if needed).",
            "No major new console/network errors.",
            "Success contract: score gate met; clicks/CVR not regressing at Day 14.",
        ],
        "verification": [
            "Day 0: PSI mobile score + LCP/TBT/CLS.",
            "Day 0 post-deploy: retest ≥70.",
            "Day 14: GSC clicks and GA4 CVR vs baseline.",
        ],
        "anti_patterns": [
            "Lazy-loading the LCP image",
            "Unsized images causing CLS",
            "Shipping huge hero PNGs/JPEGs",
        ],
        "metrics_to_watch": [
            "pagespeed.performance_score_mobile",
            "gsc.clicks",
            "ga4.bounce_rate",
            "ga4.cvr",
        ],
    },
    "pagespeed_improve": {
        "title": "Improve page speed → better engagement",
        "north_star": "Better LCP/TBT; mobile score trending to 70+",
        "metric": "LCP / TBT",
        "effort": "1–3 hrs",
        "success_formula": "Incremental speed wins reduce bounce and support rankings. Success = measurable PSI improvement.",
        "impact_model": "Supports click retention on-page (lower bounce) and long-term ranking.",
        "deliverables": ["LCP preload/lazy-load fixes", "Reduced blocking scripts", "Retest notes"],
        "technical_spec": [
            "Focus on LCP and Total Blocking Time from PSI.",
            "Lazy-load below-fold media; preload LCP image.",
            "Trim heavy scripts; retest mobile toward 70+.",
        ],
        "copy_templates": [],
        "steps": [
            "Focus on Largest Contentful Paint and Total Blocking Time.",
            "Lazy-load below-fold media; preload the LCP image.",
            "Retest mobile score; aim for 70+.",
        ],
        "agent_notes": ["Ship the highest-impact PSI opportunity first (usually LCP image)."],
        "acceptance": [
            "Mobile score improved vs baseline in the finding.",
            "LCP element identified and optimized.",
        ],
        "verification": ["Day 0 before/after PSI", "Day 14 bounce/clicks check"],
        "anti_patterns": ["Micro-optimizing unused CSS while LCP is 6s+"],
        "metrics_to_watch": ["pagespeed.performance_score_mobile", "ga4.bounce_rate"],
    },
    "mobile_ctr_gap": {
        "title": "Close mobile CTR gap → more mobile clicks",
        "north_star": "Mobile gsc.ctr closing toward desktop CTR",
        "metric": "Mobile CTR",
        "effort": "1–2 hrs",
        "success_formula": (
            "Mobile searchers see you but click less. Fix truncation, tap targets, speed, "
            "and mobile SERP titles. Success = mobile CTR ↑ within 14 days."
        ),
        "impact_model": "Mobile often dominates impressions — closing the CTR gap unlocks large click volume.",
        "deliverables": [
            "Mobile-safe title length",
            "Mobile UX fixes (tap targets, sticky header, font)",
            "Mobile speed fixes if bounce is high",
        ],
        "technical_spec": [
            "Compare mobile vs desktop titles in SERP (truncation?).",
            "Shorten titles that truncate on ~30–35 character mobile display.",
            "Fix tap targets, font size, sticky header covering CTA/content.",
            "Fix mobile speed issues causing bounce before engagement.",
        ],
        "copy_templates": [
            "Mobile title: put keyword + benefit in first 35 characters.",
        ],
        "steps": [
            "Compare mobile vs desktop SERP titles (truncation?).",
            "Test mobile page: tap targets, font size, sticky header covering content.",
            "Fix mobile speed issues that cause bounce before engagement.",
            "Recheck mobile CTR in GSC device report in 14 days.",
        ],
        "agent_notes": ["Optimize for mobile SERP + mobile fold — that's where clicks are lost."],
        "acceptance": [
            "Mobile title not overly truncated in preview tools.",
            "Primary content/CTA usable at 375px width.",
            "Success contract: mobile CTR ↑ within 14 days.",
        ],
        "verification": ["Day 0 mobile vs desktop CTR", "Day 14 mobile CTR gap narrowed"],
        "anti_patterns": ["Desktop-only title testing", "Sticky bars covering the H1/CTA"],
        "metrics_to_watch": ["gsc.ctr", "gsc.clicks", "ga4.bounce_rate"],
    },
    "bing_opportunity": {
        "title": "Open Bing → incremental clicks",
        "north_star": "bing.clicks from a verified, crawled site",
        "metric": "Bing clicks",
        "effort": "30 min",
        "success_formula": "Bing is incremental traffic. Verify, import GSC, submit sitemap. Success = Bing clicks appearing within 14–28 days.",
        "impact_model": "Low effort channel diversification — additive clicks without cannibalizing Google.",
        "deliverables": ["Bing Webmaster verification", "Sitemap submitted", "robots allows Bingbot"],
        "technical_spec": [
            "Add site in Bing Webmaster Tools; import from GSC if available.",
            "Submit absolute sitemap URL; confirm 200.",
            "Ensure robots.txt allows Bingbot.",
        ],
        "copy_templates": [],
        "steps": [
            "Add the site in Bing Webmaster Tools.",
            "Import from Google Search Console (one-click).",
            "Submit sitemap; verify crawl stats in a week.",
        ],
        "agent_notes": ["Treat Bing as bonus click volume after Google CTR/content fixes."],
        "acceptance": [
            "Site verified in Bing Webmaster.",
            "Sitemap accepted.",
            "Success contract: Bing impressions/clicks > 0 within 28 days.",
        ],
        "verification": ["Day 7 crawl stats", "Day 28 Bing clicks"],
        "anti_patterns": ["Blocking Bingbot in robots.txt"],
        "metrics_to_watch": ["bing.clicks", "bing.impressions"],
    },
    "bing_underperform": {
        "title": "Grow Bing share → more non-Google clicks",
        "north_star": "bing.clicks rising vs Google baseline",
        "metric": "Bing vs Google clicks",
        "effort": "1 hr",
        "success_formula": "Fix Bing crawl/index gaps to capture share. Success = Bing clicks ↑ over 28 days.",
        "impact_model": "Incremental clicks from an under-tapped engine.",
        "deliverables": ["Crawl error fixes", "Sitemap resubmit", "robots confirmation"],
        "technical_spec": [
            "Bing Webmaster → Crawl errors; fix blocked resources.",
            "Resubmit sitemap; check Index Explorer coverage.",
            "Ensure robots.txt allows Bingbot.",
        ],
        "copy_templates": [],
        "steps": [
            "Bing Webmaster → Crawl errors; fix blocked resources.",
            "Resubmit sitemap; check Index Explorer coverage.",
            "Ensure robots.txt allows Bingbot.",
        ],
        "agent_notes": ["Clear crawl blockers first; content parity with Google pages second."],
        "acceptance": [
            "Priority Bing crawl errors cleared.",
            "robots.txt allows Bingbot.",
            "Success contract: Bing clicks ↑ within 28 days.",
        ],
        "verification": ["Day 14 crawl health", "Day 28 Bing clicks"],
        "anti_patterns": ["Ignoring Bing-specific blocked resources"],
        "metrics_to_watch": ["bing.clicks"],
    },
    "bounce_cro_alert": {
        "title": "Fix bounce + conversion leak → keep clicks that convert",
        "north_star": "Lower bounce + higher key_events on the landing URL",
        "metric": "Bounce rate & CVR",
        "effort": "2–4 hrs",
        "success_formula": (
            "Clicks that bounce don't become leads. Align message to query/ad, raise CTA, "
            "cut clutter, fix load >3s. Success = bounce ↓ and key_events ↑ in 14 days."
        ),
        "impact_model": "Improves yield of every earned click (SEO or ads).",
        "deliverables": [
            "Intent-aligned hero",
            "CTA above fold",
            "Mobile load fixes if >3s",
            "Clarity-informed UX fixes",
        ],
        "technical_spec": [
            "Watch 5 Clarity recordings (rage clicks, dead ends).",
            "Align hero with the query/ad that sends traffic.",
            "Move primary CTA higher; remove above-fold clutter.",
            "Fix load delays >3s on mobile (images/JS).",
        ],
        "copy_templates": [
            "Hero: mirror the search/ad phrase the user just clicked.",
        ],
        "steps": [
            "Watch 5 Clarity recordings for the page (rage clicks, dead ends).",
            "Align hero message with the ad/search query that sent traffic.",
            "Move primary CTA higher; cut clutter above the fold.",
            "Fix load delays >3s on mobile.",
            "Re-measure bounce + key_events in 14 days.",
        ],
        "agent_notes": [
            "Every bounce wastes a click you already paid for (SEO effort or ad $).",
            "Message match is usually the highest-ROI fix.",
        ],
        "acceptance": [
            "Hero matches likely landing intent.",
            "Primary CTA above the fold on mobile.",
            "Mobile LCP improved if load delay was cited.",
            "Success contract: bounce ↓ and/or key_events ↑ in 14 days.",
        ],
        "verification": [
            "Day 0: bounce, sessions, key_events for URL.",
            "Day 14: bounce improved ≥5 pts OR CVR/key_events ↑.",
        ],
        "anti_patterns": ["Generic hero unrelated to query", "Slow hero video autoplay on mobile"],
        "metrics_to_watch": ["ga4.bounce_rate", "ga4.key_events", "ga4.cvr"],
    },
    "ads_spend_low_leads": {
        "title": "Fix ads → leads leak",
        "north_star": "CRM leads per ad dollar (and valid conversion tracking)",
        "metric": "Ad cost vs CRM leads",
        "effort": "1–3 hrs",
        "success_formula": "Spend must produce tracked leads. Fix tracking and landing message match. Success = test lead in CRM + improved lead volume.",
        "impact_model": "Stops wasted spend; recovers lead yield from existing clicks.",
        "deliverables": ["Verified click→CRM path", "Landing/offer alignment", "Broken form fixes"],
        "technical_spec": [
            "Trace ad click → landing → form → CRM contact.",
            "Fix broken endpoints, missing events, consent blockers.",
            "Align landing offer/CTA with ad copy.",
        ],
        "copy_templates": [],
        "steps": [
            "Open the top landing URL named in this insight.",
            "Submit a test lead — confirm a HubSpot contact with UTMs is created.",
            "Match the primary CTA/form to the ad promise above the fold on that URL.",
            "Pause campaigns still sending traffic here with zero CRM leads.",
            "Remeasure leads vs spend in 7 days.",
        ],
        "agent_notes": ["Engineering owns tracking/landing; media owns pause/rewrite."],
        "acceptance": [
            "Test lead from ad landing appears in CRM.",
            "Primary landing forms work end-to-end.",
            "Success contract: leads/spend improves over next 14 days.",
        ],
        "verification": ["Day 0 test conversion", "Day 14 leads vs cost"],
        "anti_patterns": ["Optimizing ads while forms are broken"],
        "metrics_to_watch": ["ads.cost", "hubspot.leads"],
    },
    "leads_revenue_leak": {
        "title": "Fix leads → revenue handoff",
        "north_star": "Closed revenue from CRM leads",
        "metric": "Leads vs closed revenue",
        "effort": "2–4 hrs",
        "success_formula": "More leads without revenue = handoff/qualification leak. Tighten qualification + CRM stages.",
        "impact_model": "Improves revenue yield of existing lead volume.",
        "deliverables": ["Qualification field updates if needed", "CRM stage/attribution checks"],
        "technical_spec": [
            "Review junk lead patterns; add qualification fields carefully.",
            "Confirm opportunity/revenue stages populate.",
        ],
        "copy_templates": [],
        "steps": [
            "Review lead quality and sales follow-up SLA.",
            "Tighten form qualification fields if junk leads.",
            "Confirm revenue attribution in CRM.",
        ],
        "agent_notes": ["Coordinate with sales before adding friction to forms."],
        "acceptance": [
            "Pipeline fields populate correctly.",
            "Forms still create CRM contacts.",
        ],
        "verification": ["Day 28 revenue vs leads trend"],
        "anti_patterns": ["Adding so much friction that leads collapse"],
        "metrics_to_watch": ["hubspot.leads", "hubspot.revenue"],
    },
    "organic_leads_leak": {
        "title": "Fix organic → leads leak",
        "north_star": "CRM leads from organic sessions/clicks",
        "metric": "Organic traffic vs CRM leads",
        "effort": "1–3 hrs",
        "success_formula": (
            "Organic clicks/sessions up but leads flat = offer/CTA/tracking gap on top pages. "
            "Success = organic-sourced leads ↑ within 14–28 days."
        ),
        "impact_model": "Converts SEO click gains into pipeline.",
        "deliverables": [
            "CTAs on top organic landing pages",
            "Form → CRM + thank-you/key_event verification",
        ],
        "technical_spec": [
            "List top organic landing pages by sessions/clicks.",
            "Add/strengthen mid-funnel CTAs and offers.",
            "Verify form submit → CRM + analytics key event.",
        ],
        "copy_templates": ["CTA on content pages: `Ready to talk? Get a free estimate.`"],
        "steps": [
            "Open the top organic URL by clicks named in this insight.",
            "Submit the contact form — confirm HubSpot contact + thank-you/key_event.",
            "Put one clear CTA above the fold matching search intent on that URL.",
            "Add a mid-page CTA if the page ranks for informational queries.",
            "Remeasure HubSpot leads vs GSC clicks in 14 days.",
        ],
        "agent_notes": ["SEO wins are incomplete until leads move — wire CTAs on winners."],
        "acceptance": [
            "Top organic pages have a clear conversion path.",
            "Test form creates CRM lead / key event.",
            "Success contract: organic-attributed leads ↑ in 28 days.",
        ],
        "verification": ["Day 0 organic leads baseline", "Day 28 lead lift"],
        "anti_patterns": ["Traffic-only reporting with no lead CTA"],
        "metrics_to_watch": ["gsc.clicks", "ga4.sessions", "hubspot.leads"],
    },
    "crawl_broken_pages": {
        "title": "Fix broken crawled pages → restore indexability",
        "north_star": "All cited URLs return 200 or intentional relevant 301",
        "metric": "HTTP status & crawl health",
        "effort": "1–2 hrs",
        "success_formula": (
            "Broken URLs waste crawl budget and drop rankings. Fix or redirect each listed URL. "
            "Success = 200/relevant 301 + indexing request on the final live URL."
        ),
        "impact_model": "Recovers impressions/clicks on previously indexed money pages.",
        "deliverables": ["Fixed or redirected URLs", "Nav/sitemap cleanup", "Indexing requests"],
        "technical_spec": [
            "Open each HTTP-error URL from the insight message.",
            "Restore content or 301 to the closest relevant live URL (not homepage dump).",
            "Remove dead links from nav/sitemap.",
            "Request indexing on the final live URL.",
        ],
        "copy_templates": [],
        "steps": [
            "Open each HTTP-error URL listed in this insight.",
            "Restore content or 301 to the closest relevant live URL (not homepage dump).",
            "Remove dead links from nav/sitemap pointing at those URLs.",
            "Request indexing on the final live URLs; re-crawl in 7 days.",
        ],
        "agent_notes": ["Every step must name the exact broken URL and the final destination."],
        "acceptance": [
            "Cited URLs return 200 or intentional relevant 301.",
            "No nav/sitemap links to dead URLs.",
            "Success contract: re-crawl clean within 7 days.",
        ],
        "verification": ["Day 0 status codes", "Day 7 re-crawl"],
        "anti_patterns": ["301 everything to homepage"],
        "metrics_to_watch": ["gsc.clicks", "gsc.impressions"],
    },
    "crawl_missing_title": {
        "title": "Add missing <title> tags → SERP clickability",
        "north_star": "Every cited URL has a unique ≤60-char title with keyword + brand",
        "metric": "SERP titles",
        "effort": "30–90 min",
        "success_formula": "Missing titles kill CTR. Add unique titles on each listed URL.",
        "impact_model": "Direct SERP CTR recovery on affected pages.",
        "deliverables": ["Unique title per URL", "Indexing request"],
        "technical_spec": [
            "For each URL in the insight: add <title> ≤60 chars with primary keyword + brand.",
            "Deploy; request indexing; verify in live source.",
        ],
        "copy_templates": ['Title: `{Primary Keyword} in {City} | {Brand}`'],
        "steps": [
            "Open each URL listed as missing <title>.",
            "Add a unique title ≤60 chars with primary keyword + brand on that exact page.",
            "Deploy and request indexing for each fixed URL.",
            "Verify titles in live source and SERP.",
        ],
        "agent_notes": ["Document FROM→TO title for each URL."],
        "acceptance": ["Live source shows unique title on each cited URL."],
        "verification": ["Day 0 missing", "Day 7 titles live"],
        "anti_patterns": ["Duplicate sitewide titles"],
        "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
    },
    "crawl_missing_h1": {
        "title": "Add missing H1s → clear on-page intent",
        "north_star": "One clear H1 per cited URL matching search intent",
        "metric": "On-page headings",
        "effort": "30–90 min",
        "success_formula": "Missing H1 confuses relevance. Add one intent-matched H1 per URL.",
        "impact_model": "Supports rankings and message match for the cited pages.",
        "deliverables": ["One H1 per URL"],
        "technical_spec": [
            "For each URL: add one H1 matching primary intent; not logo text; only one H1.",
        ],
        "copy_templates": [],
        "steps": [
            "Open each URL listed as missing H1.",
            "Add one clear H1 matching that page's search intent (not logo text).",
            "Ensure only one H1 per page; deploy.",
            "Remeasure rankings for the affected URLs.",
        ],
        "agent_notes": ["Name each URL and the exact H1 string shipped."],
        "acceptance": ["Each cited URL has exactly one relevant H1."],
        "verification": ["Day 0 → Day 7 live H1 check"],
        "anti_patterns": ["Multiple H1s", "Logo-as-H1"],
        "metrics_to_watch": ["gsc.position", "gsc.clicks"],
    },
    "crawl_thin_content": {
        "title": "Expand thin pages → capture rankings",
        "north_star": "Cited pages meet useful word-count and answer intent",
        "metric": "Content depth",
        "effort": "2–4 hrs",
        "success_formula": "Thin pages under-rank. Expand each listed URL with unique useful content.",
        "impact_model": "Position/CTR lift on thin money pages.",
        "deliverables": ["Expanded sections/FAQ per URL"],
        "technical_spec": [
            "For each URL + word count in the insight: expand unique content; add FAQ/H2; no fluff.",
        ],
        "copy_templates": [],
        "steps": [
            "Open each thin URL with its word count from this insight.",
            "Expand unique content + FAQ/H2 sections that answer the ranking query.",
            "Do not pad with fluff; deploy + request indexing.",
            "Recheck rankings in 14 days.",
        ],
        "agent_notes": ["Ship content on the exact cited URL — do not create a competing thin page."],
        "acceptance": ["Word count above threshold; content is useful and unique."],
        "verification": ["Day 0 word count", "Day 14 rankings"],
        "anti_patterns": ["Spun filler", "Duplicate near-identical pages"],
        "metrics_to_watch": ["gsc.position", "gsc.clicks"],
    },
    "crawl_missing_meta": {
        "title": "Add missing meta descriptions → CTR",
        "north_star": "Unique ≤155-char meta with CTA on each cited URL",
        "metric": "SERP CTR",
        "effort": "30–90 min",
        "success_formula": "Missing metas waste impressions. Write unique metas on each listed URL.",
        "impact_model": "CTR lift on pages that already rank.",
        "deliverables": ["Unique meta per URL"],
        "technical_spec": [
            "For each URL: write meta ≤155 chars with keyword + CTA; deploy; monitor CTR.",
        ],
        "copy_templates": ["Meta: `{Benefit}. {Differentiator}. {CTA} today.`"],
        "steps": [
            "Open each URL listed as missing meta description.",
            "Write a unique meta ≤155 chars with keyword + CTA on that page.",
            "Deploy; monitor CTR for those URLs in GSC.",
        ],
        "agent_notes": ["Document FROM→TO meta for each URL."],
        "acceptance": ["Live source shows unique meta on each cited URL."],
        "verification": ["Day 14 CTR vs baseline"],
        "anti_patterns": ["Identical metas across many pages"],
        "metrics_to_watch": ["gsc.ctr", "gsc.clicks"],
    },
}

# Expected CTR by rounded position (for uplift math when message lacks expected CTR)
_EXPECTED_CTR = {
    1: 0.30,
    2: 0.15,
    3: 0.10,
    4: 0.07,
    5: 0.05,
    6: 0.03,
    7: 0.03,
    8: 0.02,
    9: 0.02,
    10: 0.02,
}

URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.IGNORECASE)
PATH_RE = re.compile(r"(?<![\w])(/[a-zA-Z][a-zA-Z0-9\-/_~.%=?]{1,180})")
QUOTED_RE = re.compile(r'[“"]([^"”]{2,120})[”"]')
NUMERIC_PATH_RE = re.compile(r"^/\d+(?:/\d+)?$")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

CTR_GAP_RE = re.compile(
    r"CTR\s+([\d.]+)\s*%?\s*\([^)]*expected\s*~?([\d.]+)\s*%",
    re.IGNORECASE,
)
IMPR_RE = re.compile(r"([\d,]+)\s*impr", re.IGNORECASE)
POS_RE = re.compile(r"(?:pos(?:ition)?\s*|at pos\s*)([\d.]+)", re.IGNORECASE)
SCORE_RE = re.compile(r"\b(\d{1,3})\s*/\s*100\b")
PCT_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%\s*WoW", re.IGNORECASE)
BOUNCE_RE = re.compile(r"bounce[^\d]*([\d.]+)\s*%", re.IGNORECASE)
CVR_RE = re.compile(r"(?:conversion|cvr)[^\d]*([\d.]+)\s*%", re.IGNORECASE)

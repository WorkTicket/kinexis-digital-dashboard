"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Input";
import { Panel } from "@/components/ui/Panel";

type Profile = {
  goals: string;
  brand_voice: string;
  do_not_touch: string;
  competitors: string;
  target_audience: string;
  notes: string;
  domains: string;
  brand_terms: string;
  primary_location: string;
  service_areas: string;
  exclude_areas: string;
  success_contract: {
    primary_metric: string;
    secondary_metrics: string;
    target_delta_pct: string;
    window_days: string;
    notes: string;
  };
  thresholds: {
    wow_impression_growth: string;
    ctr_gap_pct: string;
    ctr_gap_pct_opp: string;
    pagespeed_urgent: string;
    pagespeed_improve: string;
    decline_wow: string;
    min_impressions_30d: string;
    min_impressions_30d_opp: string;
  };
};

type Props = {
  profileJson?: string;
  owner?: string;
  priority?: number;
  onSave: (data: { profile: Record<string, unknown>; owner: string; priority: number }) => void;
};

const PRIMARY_OPTIONS = [
  { value: "hubspot.leads", label: "HubSpot leads" },
  { value: "hubspot.revenue", label: "HubSpot revenue" },
  { value: "hubspot.opportunities", label: "HubSpot opportunities" },
  { value: "hubspot.closed_won", label: "HubSpot deals won" },
  { value: "paid.conversions", label: "Paid conversions (all channels)" },
  { value: "paid.cost", label: "Paid spend (all channels)" },
  { value: "paid.conversion_value", label: "Paid conversion value" },
  { value: "paid.clicks", label: "Paid clicks (all channels)" },
  { value: "ga4.key_events", label: "GA4 conversions" },
  { value: "ga4.sessions", label: "GA4 sessions" },
  { value: "gsc.clicks", label: "GSC organic clicks" },
  { value: "gsc.impressions", label: "GSC impressions" },
];

function parseProfile(raw?: string): Profile {
  const emptyThr = {
    wow_impression_growth: "0.20",
    ctr_gap_pct: "0.40",
    ctr_gap_pct_opp: "0.30",
    pagespeed_urgent: "50",
    pagespeed_improve: "70",
    decline_wow: "-0.20",
    min_impressions_30d: "1000",
    min_impressions_30d_opp: "250",
  };
  const emptyContract = {
    primary_metric: "hubspot.leads",
    secondary_metrics: "hubspot.revenue, gsc.clicks, ga4.key_events",
    target_delta_pct: "20",
    window_days: "90",
    notes: "",
  };
  try {
    const p = JSON.parse(raw || "{}");
    const domainsRaw = p.domains ?? p.aliases ?? "";
    const domains = Array.isArray(domainsRaw)
      ? domainsRaw.filter((d: unknown) => typeof d === "string").join(", ")
      : String(domainsRaw || "");
    const brandRaw = p.brand_terms ?? "";
    const brand_terms = Array.isArray(brandRaw)
      ? brandRaw.filter((d: unknown) => typeof d === "string").join(", ")
      : String(brandRaw || "");
    const nestedSa = p.service_area && typeof p.service_area === "object" ? p.service_area : {};
    const areasRaw = p.service_areas ?? nestedSa.service_areas ?? nestedSa.areas ?? "";
    const service_areas = Array.isArray(areasRaw)
      ? areasRaw.filter((d: unknown) => typeof d === "string").join(", ")
      : String(areasRaw || "");
    const exclRaw = p.exclude_areas ?? nestedSa.exclude_areas ?? nestedSa.exclude ?? "";
    const exclude_areas = Array.isArray(exclRaw)
      ? exclRaw.filter((d: unknown) => typeof d === "string").join(", ")
      : String(exclRaw || "");
    const primary_location = String(
      p.primary_location || nestedSa.primary_location || nestedSa.primary || p.location || ""
    );
    const t = p.thresholds || {};
    const sc = p.success_contract || {};
    const secondary = Array.isArray(sc.secondary_metrics)
      ? sc.secondary_metrics.join(", ")
      : String(sc.secondary_metrics || emptyContract.secondary_metrics);
    return {
      goals: String(p.goals || ""),
      brand_voice: String(p.brand_voice || ""),
      do_not_touch: String(p.do_not_touch || ""),
      competitors: String(p.competitors || ""),
      target_audience: String(p.target_audience || ""),
      notes: String(p.notes || ""),
      domains,
      brand_terms,
      primary_location,
      service_areas,
      exclude_areas,
      success_contract: {
        primary_metric: String(sc.primary_metric || emptyContract.primary_metric),
        secondary_metrics: secondary,
        target_delta_pct: String(sc.target_delta_pct ?? emptyContract.target_delta_pct),
        window_days: String(sc.window_days ?? emptyContract.window_days),
        notes: String(sc.notes || ""),
      },
      thresholds: {
        wow_impression_growth: String(t.wow_impression_growth ?? emptyThr.wow_impression_growth),
        ctr_gap_pct: String(t.ctr_gap_pct ?? emptyThr.ctr_gap_pct),
        ctr_gap_pct_opp: String(t.ctr_gap_pct_opp ?? emptyThr.ctr_gap_pct_opp),
        pagespeed_urgent: String(t.pagespeed_urgent ?? emptyThr.pagespeed_urgent),
        pagespeed_improve: String(t.pagespeed_improve ?? emptyThr.pagespeed_improve),
        decline_wow: String(t.decline_wow ?? emptyThr.decline_wow),
        min_impressions_30d: String(t.min_impressions_30d ?? emptyThr.min_impressions_30d),
        min_impressions_30d_opp: String(
          t.min_impressions_30d_opp ?? emptyThr.min_impressions_30d_opp
        ),
      },
    };
  } catch {
    return {
      goals: "",
      brand_voice: "",
      do_not_touch: "",
      competitors: "",
      target_audience: "",
      notes: "",
      domains: "",
      brand_terms: "",
      primary_location: "",
      service_areas: "",
      exclude_areas: "",
      success_contract: emptyContract,
      thresholds: emptyThr,
    };
  }
}

export default function ClientProfileEditor({
  profileJson,
  owner: ownerProp = "",
  priority: priorityProp = 1,
  onSave,
}: Props) {
  const [form, setForm] = useState<Profile>(() => parseProfile(profileJson));
  const [owner, setOwner] = useState(ownerProp);
  const [priority, setPriority] = useState(priorityProp || 1);
  const [section, setSection] = useState<"context" | "contract" | "thresholds">("context");
  const [contractEnabled, setContractEnabled] = useState(() => {
    try {
      const p = JSON.parse(profileJson || "{}");
      return Boolean(p?.success_contract?.primary_metric);
    } catch {
      return false;
    }
  });

  useEffect(() => {
    setForm(parseProfile(profileJson));
    try {
      const p = JSON.parse(profileJson || "{}");
      setContractEnabled(Boolean(p?.success_contract?.primary_metric));
    } catch {
      setContractEnabled(false);
    }
  }, [profileJson]);

  useEffect(() => {
    setOwner(ownerProp || "");
    setPriority(priorityProp || 1);
  }, [ownerProp, priorityProp]);

  return (
    <Panel className="space-y-3">
      <p className="section-label">Agency memory</p>
      <div className="flex flex-wrap gap-1">
        {(
          [
            ["context", "Business context"],
            ["contract", "Success contract"],
            ["thresholds", "Insight thresholds"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSection(id)}
            className={`chip ${section === id ? "chip-active" : ""}`}
          >
            {label}
          </button>
        ))}
      </div>

      {section === "context" && (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <Input
              label="Owner"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              placeholder="Account lead"
              className="!py-2 !text-xs"
            />
            <Select
              label="Priority"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="!py-2 !text-xs"
            >
              <option value={1}>Normal</option>
              <option value={2}>High</option>
              <option value={3}>VIP</option>
            </Select>
          </div>
          {(
            [
              ["domains", "Domain aliases"],
              ["brand_terms", "Brand search terms"],
              ["primary_location", "Primary location"],
              ["service_areas", "Service areas (cities served)"],
              ["exclude_areas", "Out of area (never target)"],
              ["goals", "Goals"],
              ["brand_voice", "Brand voice"],
              ["target_audience", "Target audience"],
              ["competitors", "Competitors"],
              ["do_not_touch", "Do not touch"],
              ["notes", "Notes"],
            ] as [Exclude<keyof Profile, "thresholds" | "success_contract">, string][]
          ).map(([key, label]) => (
            <Textarea
              key={key}
              label={label}
              value={form[key]}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
              rows={
                key === "notes" ||
                key === "competitors" ||
                key === "domains" ||
                key === "brand_terms" ||
                key === "service_areas" ||
                key === "exclude_areas"
                  ? 2
                  : 1
              }
              className="!min-h-[2rem] !text-xs"
              placeholder={
                key === "domains"
                  ? "e.g. preferredplumbingsolution.com (GSC/GA4 match)"
                  : key === "brand_terms"
                    ? "e.g. Acme, Acme Plumbing (comma-separated)"
                    : key === "primary_location"
                      ? "e.g. Cedar Falls, Iowa"
                      : key === "service_areas"
                        ? "e.g. Cedar Falls, Waterloo, Evansdale (comma-separated)"
                        : key === "exclude_areas"
                          ? "e.g. Cedar Lake (nearby cities Google may show — do not grow)"
                          : key === "goals"
                            ? "e.g. +20% organic leads this quarter"
                            : key === "brand_voice"
                              ? "e.g. confident, plain-spoken, no hype"
                              : key === "target_audience"
                                ? "e.g. mid-market B2B ops leaders"
                                : key === "competitors"
                                  ? "e.g. rival.com, otherbrand.com"
                                  : key === "do_not_touch"
                                    ? "e.g. homepage hero, pricing page"
                                    : "Anything else the AI should know"
              }
            />
          ))}
        </>
      )}

      {section === "contract" && (
        <div className="space-y-2.5">
          <p className="text-xs leading-relaxed text-ink-dim">
            Binding KPI for this engagement. Portfolio risk, Prove, Report, and agent briefs
            optimize against this target.
          </p>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-secondary">
            <input
              type="checkbox"
              checked={contractEnabled}
              onChange={(e) => setContractEnabled(e.target.checked)}
              className="rounded border-surface-border"
            />
            Enable Success Contract
          </label>
          {contractEnabled && (
            <>
              <Select
                label="Primary success metric"
                value={form.success_contract.primary_metric}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    success_contract: { ...f.success_contract, primary_metric: e.target.value },
                  }))
                }
                className="!py-2 !text-xs"
              >
                {PRIMARY_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </Select>
              <Input
                label="Secondary metrics (comma-separated)"
                value={form.success_contract.secondary_metrics}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    success_contract: { ...f.success_contract, secondary_metrics: e.target.value },
                  }))
                }
                className="!py-2 !text-xs"
                hint="e.g. paid.conversions, hubspot.leads, ga4.key_events"
              />
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Input
                  label="Target lift %"
                  value={form.success_contract.target_delta_pct}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      success_contract: { ...f.success_contract, target_delta_pct: e.target.value },
                    }))
                  }
                  className="!py-2 !text-xs"
                />
                <Input
                  label="Window (days)"
                  value={form.success_contract.window_days}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      success_contract: { ...f.success_contract, window_days: e.target.value },
                    }))
                  }
                  className="!py-2 !text-xs"
                />
              </div>
              <Textarea
                label="Contract notes"
                value={form.success_contract.notes}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    success_contract: { ...f.success_contract, notes: e.target.value },
                  }))
                }
                rows={2}
                className="!min-h-[2rem] !text-xs"
                placeholder="e.g. Exclude brand campaigns; count only marketing-qualified leads"
              />
            </>
          )}
        </div>
      )}

      {section === "thresholds" && (
        <div className="space-y-2.5">
          <p className="text-xs leading-relaxed text-ink-dim">
            Advanced — tune Detect rules for this vertical. Leave defaults if unsure.
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {(
              [
                [
                  "wow_impression_growth",
                  "Week-over-week impression growth",
                  "How fast impressions must rise to flag a surge",
                ],
                [
                  "ctr_gap_pct",
                  "Click rate gap vs typical (problems)",
                  "Gap that creates a must-fix issue",
                ],
                [
                  "ctr_gap_pct_opp",
                  "Click rate gap vs typical (opportunities)",
                  "Softer gap treated as a growth play",
                ],
                [
                  "min_impressions_30d",
                  "Min impressions / 30 days (problems)",
                  "Ignore thin traffic for problem flags",
                ],
                [
                  "min_impressions_30d_opp",
                  "Min impressions / 30 days (opps)",
                  "Ignore thin traffic for opportunities",
                ],
                [
                  "decline_wow",
                  "Week-over-week decline threshold",
                  "Negative change that triggers a decline alert",
                ],
                ["pagespeed_urgent", "PageSpeed urgent below", "Score under this is urgent"],
                [
                  "pagespeed_improve",
                  "PageSpeed improve below",
                  "Score under this should be improved",
                ],
              ] as [keyof Profile["thresholds"], string, string][]
            ).map(([key, label, hint]) => (
              <Input
                key={key}
                label={label}
                value={form.thresholds[key]}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    thresholds: { ...f.thresholds, [key]: e.target.value },
                  }))
                }
                className="!py-2 !text-xs"
                hint={hint}
              />
            ))}
          </div>
        </div>
      )}

      <Button
        type="button"
        variant="soft"
        onClick={() => {
          const thr: Record<string, number> = {};
          for (const [k, v] of Object.entries(form.thresholds)) {
            const n = Number(v);
            if (!Number.isNaN(n)) thr[k] = n;
          }
          const profile: Record<string, unknown> = {
            goals: form.goals,
            brand_voice: form.brand_voice,
            do_not_touch: form.do_not_touch,
            competitors: form.competitors,
            target_audience: form.target_audience,
            notes: form.notes,
            domains: form.domains,
            brand_terms: form.brand_terms,
            primary_location: form.primary_location,
            service_areas: form.service_areas,
            exclude_areas: form.exclude_areas,
            thresholds: thr,
          };
          if (contractEnabled) {
            const secondary = form.success_contract.secondary_metrics
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
            profile.success_contract = {
              primary_metric: form.success_contract.primary_metric,
              secondary_metrics: secondary,
              target_delta_pct: Number(form.success_contract.target_delta_pct) || 20,
              window_days: Number(form.success_contract.window_days) || 90,
              notes: form.success_contract.notes,
            };
          }
          onSave({
            profile,
            owner,
            priority,
          });
        }}
      >
        Save profile
      </Button>
    </Panel>
  );
}

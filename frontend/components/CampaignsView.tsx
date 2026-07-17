"use client";

import { useEffect, useMemo, useState } from "react";
import { api, Metric } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Stat } from "@/components/ui/Stat";
import { Megaphone, PauseCircle, TrendingDown } from "lucide-react";

type CampaignRow = {
  source: string;
  campaign: string;
  cost: number;
  clicks: number;
  impressions: number;
  conversions: number;
  conversion_value: number;
};

type Props = {
  clientId: number;
  onPrescribe?: () => void;
};

type WasteRow = {
  source: string;
  label: string;
  dimType: string;
  cost: number;
  clicks: number;
  conversions: number;
};

function rollupCampaigns(metrics: Metric[]): CampaignRow[] {
  const map = new Map<string, CampaignRow>();
  for (const m of metrics) {
    if (!["ads_csv", "google_ads", "meta_ads"].includes(m.source)) continue;
    if (m.dimension_type !== "campaign" || !m.dimension_value) continue;
    const key = `${m.source}::${m.dimension_value}`;
    const row =
      map.get(key) ||
      ({
        source: m.source,
        campaign: m.dimension_value,
        cost: 0,
        clicks: 0,
        impressions: 0,
        conversions: 0,
        conversion_value: 0,
      } satisfies CampaignRow);
    if (m.metric_name === "cost") row.cost += m.value;
    else if (m.metric_name === "clicks") row.clicks += m.value;
    else if (m.metric_name === "impressions") row.impressions += m.value;
    else if (m.metric_name === "conversions") row.conversions += m.value;
    else if (m.metric_name === "conversion_value") row.conversion_value += m.value;
    map.set(key, row);
  }
  return [...map.values()].sort((a, b) => b.cost - a.cost);
}

function rollupWaste(metrics: Metric[], dimType: string, minSpend: number): WasteRow[] {
  const map = new Map<string, WasteRow>();
  for (const m of metrics) {
    if (!["google_ads", "meta_ads"].includes(m.source)) continue;
    if (m.dimension_type !== dimType || !m.dimension_value) continue;
    const key = `${m.source}::${m.dimension_value}`;
    const row =
      map.get(key) ||
      ({
        source: m.source,
        label: m.dimension_value,
        dimType,
        cost: 0,
        clicks: 0,
        conversions: 0,
      } satisfies WasteRow);
    if (m.metric_name === "cost") row.cost += m.value;
    else if (m.metric_name === "clicks") row.clicks += m.value;
    else if (m.metric_name === "conversions") row.conversions += m.value;
    map.set(key, row);
  }
  return [...map.values()]
    .filter((r) => r.cost >= minSpend && r.conversions <= 0)
    .sort((a, b) => b.cost - a.cost)
    .slice(0, 8);
}

export default function CampaignsView({ clientId, onPrescribe }: Props) {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void api.metrics
      .list({ client_id: clientId, days: 14 })
      .then((rows) => {
        if (!cancelled) setMetrics(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load campaigns");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const campaigns = useMemo(() => rollupCampaigns(metrics), [metrics]);
  const searchTermWaste = useMemo(() => rollupWaste(metrics, "search_term", 25), [metrics]);
  const placementWaste = useMemo(() => rollupWaste(metrics, "placement", 40), [metrics]);
  const weak = campaigns.filter((c) => c.cost >= 50 && c.conversions <= 0);
  const totalSpend = campaigns.reduce((s, c) => s + c.cost, 0);
  const totalConv = campaigns.reduce((s, c) => s + c.conversions, 0);

  if (loading) {
    return (
      <Panel padding="lg">
        <p className="text-muted text-sm">Loading campaign performance…</p>
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel padding="lg">
        <p className="text-sm text-kinexis-risk">{error}</p>
      </Panel>
    );
  }
  if (campaigns.length === 0) {
    return (
      <EmptyState
        title="No paid campaign data"
        description="Connect Google Ads, Meta Ads, or paste an Ads CSV on this client, then sync."
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="metric-grid grid-cols-2 sm:grid-cols-4">
        <Stat label="Campaigns (14d)" value={campaigns.length} />
        <Stat
          label="Spend"
          value={`$${totalSpend.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
        />
        <Stat
          label="Conversions"
          value={totalConv.toLocaleString(undefined, { maximumFractionDigits: 1 })}
        />
        <Stat
          label="Weak (spend, 0 conv)"
          value={weak.length}
          tone={weak.length ? "danger" : "success"}
        />
      </div>

      {weak.length > 0 && (
        <Panel padding="md" className="border-kinexis-risk/25 bg-kinexis-risk/5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                <PauseCircle size={14} className="text-kinexis-risk" />
                Pause candidates
              </p>
              <p className="text-muted mt-1 text-xs leading-relaxed">
                {weak.length} campaign{weak.length === 1 ? "" : "s"} spent ≥$50 with zero
                conversions in 14 days. Prescribe opens the Fix queue with pause playbooks.
              </p>
            </div>
            {onPrescribe && (
              <Button variant="soft" size="sm" onClick={onPrescribe}>
                Open Fix queue
              </Button>
            )}
          </div>
        </Panel>
      )}

      {(searchTermWaste.length > 0 || placementWaste.length > 0) && (
        <Panel padding="md" className="border-kinexis-risk/20 bg-kinexis-risk/5">
          <p className="flex items-center gap-2 text-sm font-medium text-ink">
            <TrendingDown size={14} className="text-kinexis-risk" />
            Waste surfaces
          </p>
          <p className="text-muted mb-3 mt-1 text-xs leading-relaxed">
            Search terms and Meta placements burning spend with zero conversions (14d).
          </p>
          <ul className="space-y-2">
            {[...searchTermWaste, ...placementWaste].map((w) => (
              <li
                key={`${w.dimType}-${w.source}-${w.label}`}
                className="flex flex-wrap items-center justify-between gap-2 text-[12px]"
              >
                <span className="min-w-0 flex-1 truncate text-ink">
                  <span className="text-muted uppercase">{w.dimType.replace(/_/g, " ")}</span>
                  {" · "}
                  {w.label}
                </span>
                <span className="font-mono-data text-kinexis-risk">
                  ${w.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
              </li>
            ))}
          </ul>
          {onPrescribe && (
            <div className="mt-3">
              <Button variant="soft" size="sm" onClick={onPrescribe}>
                Open Fix queue
              </Button>
            </div>
          )}
        </Panel>
      )}

      <Panel padding={false}>
        <div className="border-b border-[color:var(--border-subtle)] px-4 py-3">
          <p className="section-label flex items-center gap-2">
            <Megaphone size={12} /> Campaign performance
          </p>
        </div>
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {campaigns.map((c) => {
            const cpa = c.conversions > 0 ? c.cost / c.conversions : null;
            const isWeak = c.cost >= 50 && c.conversions <= 0;
            return (
              <li
                key={`${c.source}-${c.campaign}`}
                className="flex flex-wrap items-center gap-3 px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{c.campaign}</p>
                  <p className="text-muted mt-0.5 text-[11px] uppercase">
                    {c.source.replace(/_/g, " ")}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="font-mono-data text-ink">
                    ${c.cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                  <span className="text-muted">{c.clicks.toLocaleString()} clicks</span>
                  <span className="text-muted">
                    {c.conversions.toLocaleString(undefined, { maximumFractionDigits: 1 })} conv
                  </span>
                  {cpa != null && <span className="text-muted">CPA ${cpa.toFixed(0)}</span>}
                  {isWeak ? (
                    <Badge tone="risk">
                      <TrendingDown size={10} className="mr-0.5 inline" />
                      Pause
                    </Badge>
                  ) : c.conversions > 0 ? (
                    <Badge tone="proof">Converting</Badge>
                  ) : (
                    <Badge tone="default">Low spend</Badge>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}

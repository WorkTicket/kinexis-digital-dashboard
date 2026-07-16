"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { buildKpiSummaries, formatKpiValue, type KpiSummary } from "@/lib/metrics";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { LoadingState } from "@/components/ui/LoadingState";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { X, GitCompare } from "lucide-react";

type Props = {
  clients: { id: number; name: string }[];
  onClose: () => void;
};

type ClientKPIs = {
  client: { id: number; name: string };
  kpis: KpiSummary[];
};

function KpiRow({
  label,
  a,
  b,
}: {
  label: string;
  a: KpiSummary | undefined;
  b: KpiSummary | undefined;
}) {
  const diff = a && b ? a.value - b.value : null;
  const aUp = (a?.changePct ?? 0) > 0;
  const bUp = (b?.changePct ?? 0) > 0;
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[color:var(--border-subtle)] py-2.5 text-[13px]">
      <span className="text-muted w-32 shrink-0 text-[11px] font-medium">{label}</span>
      <div className="flex flex-1 items-center gap-3">
        <span className="font-mono-data flex-1 text-right font-semibold text-ink">
          {a ? formatKpiValue(a.value, a.format) : "\u2014"}
        </span>
        {a && (
          <span
            className={`font-mono-data w-14 text-xs ${aUp ? "text-kinexis-proof" : "text-kinexis-risk"}`}
          >
            {aUp ? "+" : ""}
            {a.changePct?.toFixed(1)}%
          </span>
        )}
        {diff !== null && (
          <span
            className={`font-mono-data w-16 text-center text-xs font-semibold ${diff > 0 ? "text-kinexis-proof" : diff < 0 ? "text-kinexis-risk" : "text-muted"}`}
          >
            {diff > 0
              ? `A +${formatKpiValue(diff, a?.format ?? "number")}`
              : diff < 0
                ? `B +${formatKpiValue(Math.abs(diff), a?.format ?? "number")}`
                : "\u2014"}
          </span>
        )}
        {b && (
          <span
            className={`font-mono-data w-14 text-xs ${bUp ? "text-kinexis-proof" : "text-kinexis-risk"}`}
          >
            {bUp ? "+" : ""}
            {b.changePct?.toFixed(1)}%
          </span>
        )}
        <span className="font-mono-data flex-1 font-semibold text-ink">
          {b ? formatKpiValue(b.value, b.format) : "\u2014"}
        </span>
      </div>
    </div>
  );
}

export default function ClientComparisonView({ clients, onClose }: Props) {
  const [clientA, setClientA] = useState<number | null>(null);
  const [clientB, setClientB] = useState<number | null>(null);
  const [dataA, setDataA] = useState<ClientKPIs | null>(null);
  const [dataB, setDataB] = useState<ClientKPIs | null>(null);
  const [loading, setLoading] = useState(false);

  const loadClient = useCallback(async (id: number, setter: (c: ClientKPIs) => void) => {
    try {
      const [client, metrics] = await Promise.all([
        api.clients.get(id),
        api.metrics.list({ client_id: id, days: 30, site_totals_only: true }),
      ]);
      const kpis = buildKpiSummaries(metrics, "30d");
      setter({ client: { id: client.id, name: client.name }, kpis });
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!clientA || !clientB) return;
    setLoading(true);
    Promise.all([loadClient(clientA, setDataA), loadClient(clientB, setDataB)]).finally(() =>
      setLoading(false)
    );
  }, [clientA, clientB, loadClient]);

  if (clients.length < 2) {
    return (
      <div className="workspace-content animate-fade-up">
        <EmptyState
          title="Need at least 2 clients to compare"
          description="Add more clients from the sidebar to use this feature."
        />
      </div>
    );
  }

  const priorityKeys = [
    "clicks",
    "impressions",
    "ctr",
    "sessions",
    "conversions",
    "cvr",
    "leads",
    "revenue",
    "ad_cost",
  ];
  const allKpis = [
    ...new Set([
      ...(dataA?.kpis.map((k) => k.key) ?? []),
      ...(dataB?.kpis.map((k) => k.key) ?? []),
    ]),
  ].filter((k) => priorityKeys.includes(k));

  return (
    <div className="workspace-content animate-fade-up">
      <div className="mb-6 flex items-center justify-between">
        <PageHeader
          eyebrow="Compare"
          title="Client comparison"
          description="Side-by-side metrics across two clients"
        />
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X size={14} />
        </Button>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <div>
          <label className="text-label mb-2 block">Client A</label>
          <select
            value={clientA ?? ""}
            onChange={(e) => setClientA(e.target.value ? Number(e.target.value) : null)}
            className="input-field"
          >
            <option value="">Select client...</option>
            {clients
              .filter((c) => c.id !== clientB)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label className="text-label mb-2 block">Client B</label>
          <select
            value={clientB ?? ""}
            onChange={(e) => setClientB(e.target.value ? Number(e.target.value) : null)}
            className="input-field"
          >
            <option value="">Select client...</option>
            {clients
              .filter((c) => c.id !== clientA)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </div>
      </div>

      {loading && <LoadingState label="Loading comparison..." variant="spinner" />}

      {!loading && dataA && dataB && (
        <Panel padding={false} className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-[color:var(--border-subtle)] bg-surface px-5 py-3">
            <span className="text-[13px] font-medium text-ink">{dataA.client.name}</span>
            <GitCompare size={14} className="text-muted" />
            <span className="text-[13px] font-medium text-ink">{dataB.client.name}</span>
          </div>
          <div className="p-5">
            {allKpis.map((key) => (
              <KpiRow
                key={key}
                label={dataA.kpis.find((k) => k.key === key)?.label ?? key}
                a={dataA.kpis.find((k) => k.key === key)}
                b={dataB.kpis.find((k) => k.key === key)}
              />
            ))}
          </div>
        </Panel>
      )}

      {!loading && (!dataA || !dataB) && (clientA || clientB) && (
        <Panel padding="lg" className="text-center">
          <p className="text-muted text-sm">Select two clients to compare their 30-day metrics.</p>
        </Panel>
      )}
    </div>
  );
}

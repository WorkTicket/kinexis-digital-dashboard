"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type {
  Recommendation,
  RecommendationEffectiveness,
} from "@/lib/api/endpoints/recommendations";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { Brain, Trophy } from "lucide-react";

type Props = {
  clientId?: number | null;
};

function outcomeTone(outcome?: string | null): "proof" | "risk" | "signal" | "default" {
  if (outcome === "win") return "proof";
  if (outcome === "loss") return "risk";
  if (outcome === "flat") return "signal";
  return "default";
}

export default function LearningLoopView({ clientId }: Props) {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [fixes, setFixes] = useState<RecommendationEffectiveness[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.recommendations.list(clientId ? { client_id: clientId, limit: 40 } : { limit: 40 }),
      api.recommendations.effectiveness(),
    ])
      .then(([list, eff]) => {
        if (cancelled) return;
        setRecs(list);
        setFixes(eff.fixes || []);
      })
      .catch(() => {
        if (!cancelled) {
          setRecs([]);
          setFixes([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  if (loading) {
    return (
      <Panel padding="lg">
        <p className="text-muted text-sm">Loading recommendation outcomes…</p>
      </Panel>
    );
  }

  if (recs.length === 0 && fixes.length === 0) {
    return (
      <EmptyState
        title="No verified recommendations yet"
        description="Assign fixes from Prescribe, ship them on Execute, then mark Prove outcomes. Win/loss rates accumulate here across your book."
      />
    );
  }

  return (
    <div className="space-y-4">
      {fixes.length > 0 && (
        <Panel padding="md">
          <p className="section-label mb-3 flex items-center gap-2">
            <Trophy size={12} /> What worked across clients
          </p>
          <ul className="space-y-2">
            {fixes.slice(0, 12).map((f) => (
              <li
                key={f.fix_type}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] pb-2 last:border-0"
              >
                <span className="text-sm text-ink">{f.fix_type.replace(/_/g, " ")}</span>
                <div className="flex items-center gap-2 text-[11px]">
                  <Badge tone={f.win_rate != null && f.win_rate >= 0.5 ? "proof" : "default"}>
                    {f.win_rate != null ? `${Math.round(f.win_rate * 100)}% win` : "n/a"}
                  </Badge>
                  <span className="text-muted font-mono-data">{f.total} fixes</span>
                  {f.median_lift_pct != null && (
                    <span className="text-muted font-mono-data">
                      median {f.median_lift_pct > 0 ? "+" : ""}
                      {f.median_lift_pct}%
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel padding={false}>
        <div className="border-b border-[color:var(--border-subtle)] px-4 py-3">
          <p className="section-label flex items-center gap-2">
            <Brain size={12} /> Recommendation lifecycle
            {clientId ? " (this client)" : " (all clients)"}
          </p>
        </div>
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {recs.map((r) => (
            <li key={r.id} className="px-4 py-3">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge tone="brand">{r.status}</Badge>
                {r.outcome && <Badge tone={outcomeTone(r.outcome)}>{r.outcome}</Badge>}
                {r.fix_type && (
                  <span className="text-muted text-[11px]">{r.fix_type.replace(/_/g, " ")}</span>
                )}
              </div>
              <p className="line-clamp-2 text-sm font-medium leading-snug text-ink">{r.title}</p>
              <p className="text-muted font-mono-data mt-1 text-[11px]">
                {r.actual_lift_pct != null
                  ? `Lift ${r.actual_lift_pct > 0 ? "+" : ""}${r.actual_lift_pct}%`
                  : r.expected_lift_pct != null
                    ? `Expected ~${r.expected_lift_pct}%`
                    : "Awaiting Prove"}
                {r.verified_at ? ` · verified ${r.verified_at.slice(0, 10)}` : ""}
              </p>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

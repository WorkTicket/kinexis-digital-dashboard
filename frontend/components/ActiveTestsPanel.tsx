"use client";

import { useEffect, useState } from "react";
import { api, type Experiment } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

type Rec = {
  id: number;
  title: string;
  status: string;
  fix_type?: string | null;
  expected_metric?: string | null;
  expected_lift_pct?: number | null;
  outcome?: string | null;
  actual_lift_pct?: number | null;
};

type Props = {
  clientId: number;
};

const ACTIVE_REC = new Set(["proposed", "accepted", "scheduled", "in_progress", "completed"]);
const ACTIVE_EXP = new Set(["draft", "running"]);

export default function ActiveTestsPanel({ clientId }: Props) {
  const [rows, setRows] = useState<Rec[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [hypothesis, setHypothesis] = useState("");
  const [metric, setMetric] = useState("");
  const [saving, setSaving] = useState(false);

  const reload = () => {
    api.recommendations
      .list({ client_id: clientId, limit: 40 })
      .then((list) => {
        const active = (list || []).filter((r) => ACTIVE_REC.has(r.status));
        setRows(active.slice(0, 12));
      })
      .catch(() => setRows([]));
    api.experiments
      .list({ client_id: clientId, limit: 40 })
      .then((list) => {
        const active = (list || []).filter((e) => ACTIVE_EXP.has(e.status));
        setExperiments(active.slice(0, 12));
      })
      .catch(() => setExperiments([]));
  };

  useEffect(() => {
    let cancelled = false;
    api.recommendations
      .list({ client_id: clientId, limit: 40 })
      .then((list) => {
        if (cancelled) return;
        const active = (list || []).filter((r) => ACTIVE_REC.has(r.status));
        setRows(active.slice(0, 12));
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      });
    api.experiments
      .list({ client_id: clientId, limit: 40 })
      .then((list) => {
        if (cancelled) return;
        const active = (list || []).filter((e) => ACTIVE_EXP.has(e.status));
        setExperiments(active.slice(0, 12));
      })
      .catch(() => {
        if (!cancelled) setExperiments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const onCreate = async () => {
    const h = hypothesis.trim();
    if (!h || saving) return;
    setSaving(true);
    try {
      await api.experiments.create({
        client_id: clientId,
        hypothesis: h,
        success_metric: metric.trim() || undefined,
        status: "running",
      });
      setHypothesis("");
      setMetric("");
      reload();
    } catch {
      /* ignore — empty panel still usable */
    } finally {
      setSaving(false);
    }
  };

  const onStatus = async (id: number, status: string) => {
    try {
      await api.experiments.update(id, { status });
      reload();
    } catch {
      /* ignore */
    }
  };

  return (
    <Panel className="mb-4 p-4">
      <p className="section-label text-muted mb-1 text-[11px] font-semibold tracking-wide">
        Active tests
      </p>
      <p className="text-muted mb-3 text-[12px]">
        Experiment registry + recommendations — hypothesis → ship → Prove against contract KPI
      </p>

      <div className="mb-4 space-y-2 rounded-[var(--radius-md)] border border-[color:var(--border-subtle)] p-3">
        <p className="text-[12px] font-medium text-ink">Log experiment</p>
        <input
          className="w-full rounded border border-[color:var(--border-subtle)] bg-transparent px-2 py-1.5 text-[13px] text-ink"
          placeholder="Hypothesis (e.g. New hero CTA lifts form CVR)"
          value={hypothesis}
          onChange={(e) => setHypothesis(e.target.value)}
        />
        <input
          className="w-full rounded border border-[color:var(--border-subtle)] bg-transparent px-2 py-1.5 text-[13px] text-ink"
          placeholder="Success metric (optional, e.g. key_events)"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        />
        <Button variant="soft" size="sm" disabled={!hypothesis.trim() || saving} onClick={onCreate}>
          Start experiment
        </Button>
      </div>

      {experiments.length > 0 && (
        <ul className="mb-3 space-y-2">
          {experiments.map((e) => (
            <li key={`exp-${e.id}`} className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">{e.hypothesis}</p>
                <p className="text-muted text-[11px]">
                  experiment
                  {e.success_metric ? ` · prove ${e.success_metric}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <Badge tone={e.status === "running" ? "proof" : "default"}>{e.status}</Badge>
                {e.status === "running" && (
                  <>
                    <Button variant="ghost" size="sm" onClick={() => onStatus(e.id, "won")}>
                      Won
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => onStatus(e.id, "lost")}>
                      Lost
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onStatus(e.id, "inconclusive")}
                    >
                      Flat
                    </Button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li key={r.id} className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-ink">{r.title}</p>
                <p className="text-muted text-[11px]">
                  {r.fix_type || "fix"}
                  {r.expected_metric ? ` · prove ${r.expected_metric}` : ""}
                  {r.expected_lift_pct != null ? ` · target +${r.expected_lift_pct}%` : ""}
                </p>
              </div>
              <Badge
                tone={
                  r.status === "completed"
                    ? "warning"
                    : r.status === "in_progress"
                      ? "proof"
                      : "default"
                }
              >
                {r.status.replace(/_/g, " ")}
              </Badge>
            </li>
          ))}
        </ul>
      )}

      {rows.length === 0 && experiments.length === 0 && (
        <p className="text-muted text-[12px]">No active recommendations or experiments yet.</p>
      )}
    </Panel>
  );
}

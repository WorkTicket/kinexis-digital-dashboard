"use client";

import { useMemo } from "react";
import { DataSource } from "@/lib/api";
import { RefreshCw, AlertCircle, CheckCircle2, CircleDashed } from "lucide-react";

type Props = {
  datasources: DataSource[];
  syncing?: boolean;
  onSync?: () => void;
  lastSyncResults?: Record<string, string> | null;
  compact?: boolean;
  showSources?: boolean;
};

function relativeTime(iso: string | null): string {
  if (!iso) return "Never synced";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Never synced";
  const diff = Date.now() - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function isDataStale(datasources: DataSource[]): boolean {
  if (datasources.length === 0) return true;
  const times = datasources
    .map((d) => d.last_synced_at)
    .filter(Boolean)
    .map((t) => new Date(t!).getTime());
  if (times.length === 0) return true;
  const newest = Math.max(...times);
  return Date.now() - newest > 24 * 60 * 60 * 1000;
}

export function latestSyncAt(datasources: DataSource[]): string | null {
  const times = datasources.map((d) => d.last_synced_at).filter(Boolean) as string[];
  if (times.length === 0) return null;
  const sorted = times.sort((a, b) => new Date(b).getTime() - new Date(a).getTime());
  return sorted[0] ?? null;
}

function failedSources(
  datasources: DataSource[],
  lastSyncResults?: Record<string, string> | null
): string[] {
  const fromResults = lastSyncResults
    ? Object.entries(lastSyncResults)
        .filter(([, v]) => v !== "ok" && !String(v).startsWith("skipped"))
        .map(([k]) => k.toUpperCase())
    : [];
  if (fromResults.length > 0) return fromResults;
  return [
    ...new Set(
      datasources
        .filter((d) => {
          const s = (d.status || "").toLowerCase();
          return s === "error" || s === "failed" || s === "partial" || s === "reauth_required";
        })
        .map((d) => d.type.toUpperCase())
    ),
  ];
}

function sourceTone(ds: DataSource, lastSyncResults?: Record<string, string> | null) {
  const result = lastSyncResults?.[ds.type];
  if (result && result !== "ok" && !String(result).startsWith("skipped")) return "error";
  const s = (ds.status || "").toLowerCase();
  if (s === "error" || s === "failed" || s === "reauth_required") return "error";
  if (s === "partial") return "partial";
  if (s === "active" || ds.last_synced_at) return "ok";
  return "pending";
}

/** One chip per type — duplicate DB rows (same type) used to render twice. */
function uniqueByType(datasources: DataSource[]): DataSource[] {
  const byType = new Map<string, DataSource>();
  for (const ds of datasources) {
    const key = (ds.type || "").toLowerCase();
    const prev = byType.get(key);
    if (!prev) {
      byType.set(key, ds);
      continue;
    }
    const prevTone = sourceTone(prev);
    const nextTone = sourceTone(ds);
    // Prefer error, then most recently synced, then higher id
    if (nextTone === "error" && prevTone !== "error") {
      byType.set(key, ds);
      continue;
    }
    if (prevTone === "error" && nextTone !== "error") continue;
    const prevTs = prev.last_synced_at ? new Date(prev.last_synced_at).getTime() : 0;
    const nextTs = ds.last_synced_at ? new Date(ds.last_synced_at).getTime() : 0;
    if (nextTs > prevTs || (nextTs === prevTs && ds.id > prev.id)) {
      byType.set(key, ds);
    }
  }
  return [...byType.values()];
}

export default function SyncStatusStrip({
  datasources,
  syncing,
  onSync,
  lastSyncResults,
  compact = true,
  showSources = true,
}: Props) {
  const uniqueSources = useMemo(() => uniqueByType(datasources), [datasources]);
  const latest = useMemo(() => latestSyncAt(datasources), [datasources]);
  const stale = useMemo(() => isDataStale(datasources), [datasources]);
  const failed = useMemo(
    () => failedSources(uniqueSources, lastSyncResults),
    [uniqueSources, lastSyncResults]
  );
  const hasError = failed.length > 0;
  const errorDetails = useMemo(
    () =>
      uniqueSources
        .filter((d) => {
          const t = sourceTone(d, lastSyncResults);
          return t === "error" || t === "partial";
        })
        .map((d) => {
          const t = sourceTone(d, lastSyncResults);
          const label = t === "partial" ? "partial" : "sync failed";
          return `${d.type.toUpperCase()}: ${d.last_error || label}`;
        })
        .join(" · "),
    [uniqueSources, lastSyncResults]
  );

  const syncBtn = onSync ? (
    <button
      type="button"
      onClick={onSync}
      disabled={syncing}
      className={
        stale || hasError
          ? "btn-primary inline-flex items-center gap-2 !px-3 !py-1 px-3 py-1 !text-[11px] disabled:opacity-40"
          : "btn-ghost !px-2 !py-1"
      }
    >
      <RefreshCw size={11} className={syncing ? "animate-spin" : ""} />
      {syncing ? "Syncing…" : "Sync"}
    </button>
  ) : null;

  return (
    <div className="space-y-1.5">
      <div className="text-muted inline-flex flex-wrap items-center gap-2 text-xs">
        {hasError && <AlertCircle size={12} className="shrink-0 text-kinexis-risk" />}
        <span className={stale ? "text-kinexis-signal/90" : ""} title={errorDetails || undefined}>
          Synced {relativeTime(latest)}
        </span>
        {hasError && (
          <span className="text-kinexis-risk" title={errorDetails || failed.join(", ")}>
            {failed.join(", ")} need attention
          </span>
        )}
        {syncBtn}
      </div>
      {showSources && uniqueSources.length > 0 && !compact && (
        <div className="flex flex-wrap gap-2">
          {uniqueSources.map((ds) => {
            const tone = sourceTone(ds, lastSyncResults);
            const cls =
              tone === "error"
                ? "border-kinexis-risk/30 text-kinexis-risk"
                : tone === "partial"
                  ? "border-kinexis-signal/40 text-kinexis-signal"
                  : tone === "ok"
                    ? "border-kinexis-proof/30 text-kinexis-proof"
                    : "border-[color:var(--border-default)] text-muted";
            const Icon =
              tone === "error" || tone === "partial"
                ? AlertCircle
                : tone === "ok"
                  ? CheckCircle2
                  : CircleDashed;
            return (
              <span
                key={ds.type}
                className={`inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-medium ${cls}`}
                style={{ borderRadius: "var(--radius-sm)" }}
                title={
                  tone === "error" || tone === "partial"
                    ? ds.last_error || (tone === "partial" ? "Sync incomplete" : "Sync failed")
                    : `Last sync: ${relativeTime(ds.last_synced_at)}`
                }
              >
                <Icon size={10} />
                {ds.type.toUpperCase()}
                {tone === "partial" ? " · partial" : ""}
                {tone === "error" && ds.status === "reauth_required" ? " · reconnect" : ""}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

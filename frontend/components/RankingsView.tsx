"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowDown, ArrowUp, Minus, Pin, PinOff, Search, X } from "lucide-react";
import { api, KeywordHistory, RankingRow, RankingsReport } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Stat } from "@/components/ui/Stat";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { CHART, chartAxisTick, chartGridProps } from "@/lib/chartTheme";
import { useToast } from "@/components/Toast";

const HIDDEN_STORAGE_KEY = "kinexis-hidden-rankings";

function loadHidden(clientId: number): string[] {
  try {
    const raw = localStorage.getItem(HIDDEN_STORAGE_KEY);
    if (!raw) return [];
    const all: Record<string, string[]> = JSON.parse(raw);
    return Array.isArray(all[String(clientId)]) ? (all[String(clientId)] as string[]) : [];
  } catch {
    return [];
  }
}

function saveHidden(clientId: number, queries: string[]) {
  try {
    const raw = localStorage.getItem(HIDDEN_STORAGE_KEY);
    const all: Record<string, string[]> = raw ? JSON.parse(raw) : {};
    all[String(clientId)] = queries;
    localStorage.setItem(HIDDEN_STORAGE_KEY, JSON.stringify(all));
  } catch {
    // storage full or unavailable
  }
}

type Props = {
  clientId: number;
  days: number;
  onDaysChange: (days: number) => void;
  onSync?: () => void;
};

type BucketFilter = "all" | "top3" | "top10" | "page2" | "deeper";
type BrandFilter = "all" | "brand" | "non_brand";

export default function RankingsView({ clientId, days, onDaysChange, onSync }: Props) {
  const { error: toastError } = useToast();
  const [data, setData] = useState<RankingsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bucket, setBucket] = useState<BucketFilter>("all");
  const [brand, setBrand] = useState<BrandFilter>("all");
  const [trackedOnly, setTrackedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [newKeyword, setNewKeyword] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [history, setHistory] = useState<KeywordHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [serpEnabled, setSerpEnabled] = useState(false);
  const [serpResults, setSerpResults] = useState<
    { position?: number; url?: string; title?: string; snippet?: string }[] | null
  >(null);
  const [serpBusy, setSerpBusy] = useState(false);

  type SortKey = "position" | "change" | "impressions" | "clicks" | "ctr" | null;
  const [sortKey, setSortKey] = useState<SortKey>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [hiddenQueries, setHiddenQueries] = useState<string[]>(() => loadHidden(clientId));

  const handleSort = (key: NonNullable<SortKey>) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir("desc");
    } else if (sortDir === "desc") {
      setSortDir("asc");
    } else {
      setSortKey(null);
    }
  };

  const sortedRankings = useMemo(() => {
    if (!data?.rankings) return [];
    if (!sortKey) return data.rankings;
    return [...data.rankings].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      const va = aVal != null ? aVal : sortKey === "position" ? Infinity : 0;
      const vb = bVal != null ? bVal : sortKey === "position" ? Infinity : 0;
      const cmp = va < vb ? -1 : va > vb ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data?.rankings, sortKey, sortDir]);

  const visibleRankings = useMemo(
    () => sortedRankings.filter((r) => !hiddenQueries.includes(r.query)),
    [sortedRankings, hiddenQueries]
  );

  const hideQuery = (query: string) => {
    setHiddenQueries((prev) => {
      const next = [...prev, query];
      saveHidden(clientId, next);
      return next;
    });
  };

  const showAll = () => {
    setHiddenQueries([]);
    saveHidden(clientId, []);
  };

  useEffect(() => {
    const t = setTimeout(() => setSearchDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const report = await api.rankings.get(clientId, {
        days,
        bucket,
        q: searchDebounced || undefined,
        tracked_only: trackedOnly,
        brand,
      });
      setData(report);
    } catch (e) {
      console.warn(e);
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load rankings");
    } finally {
      setLoading(false);
    }
  }, [clientId, days, bucket, searchDebounced, trackedOnly, brand]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) {
      setHistory(null);
      setSerpResults(null);
      return;
    }
    let cancelled = false;
    setHistoryLoading(true);
    api.rankings
      .history(clientId, selected, Math.max(days, 90))
      .then((h) => {
        if (!cancelled) setHistory(h);
      })
      .catch((e) => {
        console.warn("Keyword history load failed", e);
        if (!cancelled) {
          setHistory(null);
          toastError(e instanceof Error ? e.message : "Failed to load keyword history");
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });

    setSerpBusy(true);
    api.rankings
      .serp(clientId, { query: selected, limit: 5 })
      .then((res) => {
        if (cancelled) return;
        setSerpEnabled(res.enabled);
        const snap = res.snapshots?.[0];
        setSerpResults(snap?.results?.length ? snap.results : null);
      })
      .catch((e) => {
        if (!cancelled) {
          setSerpResults(null);
          console.warn("SERP load failed", e);
          toastError(e instanceof Error ? e.message : "Failed to load SERP results");
        }
      })
      .finally(() => {
        if (!cancelled) setSerpBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [clientId, selected, days, toastError]);

  const refreshSerp = async () => {
    if (!selected) return;
    setSerpBusy(true);
    try {
      const res = await api.rankings.refreshSerp(clientId, selected);
      const snap = (res as { snapshot?: { results?: typeof serpResults } }).snapshot;
      if (snap?.results) setSerpResults(snap.results);
      setSerpEnabled(true);
    } catch (e) {
      console.warn("SERP refresh failed", e);
      toastError(e instanceof Error ? e.message : "Failed to refresh SERP");
    } finally {
      setSerpBusy(false);
    }
  };
  const handleTrack = async (keyword: string) => {
    setBusy(true);
    try {
      await api.rankings.track(clientId, { keyword });
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to pin keyword";
      setError(msg);
      setTimeout(() => setError((prev) => (prev === msg ? null : prev)), 4000);
    } finally {
      setBusy(false);
    }
  };

  const handleUntrack = async (trackedId: number) => {
    setBusy(true);
    try {
      await api.rankings.untrack(clientId, trackedId);
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to unpin keyword";
      setError(msg);
      setTimeout(() => setError((prev) => (prev === msg ? null : prev)), 4000);
    } finally {
      setBusy(false);
    }
  };

  const handleAddKeyword = async (e: React.FormEvent) => {
    e.preventDefault();
    const kw = newKeyword.trim();
    if (!kw) return;
    await handleTrack(kw);
    setNewKeyword("");
    setSelected(kw);
  };

  const summary = data?.summary;
  const hasData = (summary?.queries_ranked ?? 0) > 0 || (summary?.tracked_count ?? 0) > 0;

  return (
    <div className="animate-fade-up space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="section-label">Google rankings</h2>
          <p className="section-title">Where this client ranks in Google Search.</p>
        </div>
        <div className="flex gap-1.5">
          {[14, 28, 56].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => onDaysChange(d)}
              className={`chip ${days === d ? "chip-active" : ""}`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {loading && !data ? (
        <LoadingState variant="table" rows={8} />
      ) : error && !data ? (
        <ErrorState
          title="Couldn’t load rankings"
          description={error}
          onRetry={() => void load()}
        />
      ) : !hasData ? (
        <EmptyState
          title="No ranking data yet"
          description="Connect Google Search Console and sync to see query positions, or pin keywords to track."
          action={
            onSync ? (
              <Button variant="soft" size="sm" onClick={onSync}>
                Sync GSC now
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat
              label="Avg position"
              value={summary?.avg_position != null ? summary.avg_position.toFixed(1) : "—"}
              hint="Impression-weighted"
            />
            <Stat label="In top 10" value={String(summary?.top10 ?? 0)} hint="Queries ≤ #10" />
            <Stat
              label="Striking distance"
              value={String(summary?.striking_distance ?? 0)}
              hint="Positions 11–20"
            />
            <Stat
              label="Improved"
              value={String(summary?.improved ?? 0)}
              hint="Moved up vs prior"
              tone="success"
            />
            <Stat
              label="Declined"
              value={String(summary?.declined ?? 0)}
              hint="Moved down vs prior"
              tone="danger"
            />
            <Stat label="Tracked" value={String(summary?.tracked_count ?? 0)} hint="Watchlist" />
          </div>

          <form onSubmit={handleAddKeyword} className="panel flex flex-wrap items-end gap-3 p-4">
            <div className="min-w-[200px] flex-1">
              <Input
                label="Track a keyword"
                placeholder="e.g. emergency plumber dallas"
                value={newKeyword}
                onChange={(e) => setNewKeyword(e.target.value)}
              />
            </div>
            <Button type="submit" size="sm" disabled={busy || !newKeyword.trim()}>
              <Pin size={14} className="mr-1.5 inline" />
              Pin keyword
            </Button>
          </form>

          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                { id: "all" as const, label: "All" },
                { id: "top3" as const, label: `Top 3 (${summary?.buckets.top3 ?? 0})` },
                { id: "top10" as const, label: `#4–10 (${summary?.buckets.top10 ?? 0})` },
                { id: "page2" as const, label: `11–20 (${summary?.buckets.page2 ?? 0})` },
                { id: "deeper" as const, label: `21+ (${summary?.buckets.deeper ?? 0})` },
              ] as const
            ).map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setBucket(b.id)}
                className={`chip ${bucket === b.id ? "chip-active" : ""}`}
              >
                {b.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setTrackedOnly((v) => !v)}
              className={`chip ${trackedOnly ? "chip-active" : ""}`}
            >
              Tracked only
            </button>
            {(
              [
                { id: "all" as const, label: "All queries" },
                { id: "non_brand" as const, label: "Non-brand" },
                { id: "brand" as const, label: "Brand" },
              ] as const
            ).map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setBrand(b.id)}
                className={`chip ${brand === b.id ? "chip-active" : ""}`}
              >
                {b.label}
              </button>
            ))}
            <div className="relative ml-auto min-w-[180px] max-w-xs flex-1">
              <Search
                size={14}
                className="text-muted pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
              />
              <input
                className="input-field !py-1.5 !pl-8 !text-xs"
                placeholder="Filter queries…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {hiddenQueries.length > 0 && (
              <button type="button" onClick={showAll} className="chip text-kinexis-risk">
                Show hidden ({hiddenQueries.length})
              </button>
            )}
          </div>

          {selected && (
            <section className="panel overflow-hidden">
              <div className="flex items-center justify-between gap-3 border-b border-surface-border/80 px-5 py-3.5">
                <div>
                  <p className="truncate text-sm font-semibold text-ink" title={selected}>
                    Position history · {selected}
                  </p>
                  <p className="text-muted mt-0.5 text-xs">
                    Daily average from Google Search Console
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
                  Close
                </Button>
              </div>
              {historyLoading ? (
                <LoadingState label="Loading history…" variant="spinner" compact />
              ) : !history?.history?.length ? (
                <p className="text-muted px-5 py-8 text-sm">
                  No daily position history for this query yet. Sync GSC or wait for impressions.
                </p>
              ) : (
                <div className="h-[220px] px-2 pb-2 pt-4 sm:h-[260px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart
                      data={history.history}
                      margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
                    >
                      <defs>
                        <linearGradient id="posFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={CHART.focus} stopOpacity={0.35} />
                          <stop offset="100%" stopColor={CHART.focus} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid {...chartGridProps} />
                      <XAxis
                        dataKey="date"
                        tick={chartAxisTick}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v: string) => v.slice(5)}
                        minTickGap={28}
                      />
                      <YAxis
                        reversed
                        domain={["dataMin - 1", "dataMax + 1"]}
                        tick={chartAxisTick}
                        axisLine={false}
                        tickLine={false}
                        width={36}
                        allowDecimals={false}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const p = payload[0]?.payload as KeywordHistory["history"][0] | undefined;
                          if (!p) return null;
                          return (
                            <div
                              className="rounded-lg border border-[color:var(--border-default)] bg-surface-elevated px-3 py-2 text-xs shadow-dropdown"
                              style={{ fontFamily: CHART.monoFamily }}
                            >
                              <p className="mb-1 font-ui font-medium text-ink">{p.date}</p>
                              <p className="text-muted font-mono-data">
                                Pos {p.position ?? "—"} · {p.impressions.toLocaleString()} impr ·{" "}
                                {p.clicks.toLocaleString()} clicks
                              </p>
                            </div>
                          );
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="position"
                        stroke={CHART.focus}
                        fill="url(#posFill)"
                        strokeWidth={2}
                        connectNulls
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
              {(serpEnabled || serpResults) && (
                <div className="border-t border-surface-border/80 px-5 py-4">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-ink">Live SERP</p>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={serpBusy || !selected}
                      onClick={() => void refreshSerp()}
                    >
                      {serpBusy ? "Fetching…" : "Refresh SERP"}
                    </Button>
                  </div>
                  {!serpEnabled && !serpResults ? (
                    <p className="text-muted text-xs">
                      Set SERP_PROVIDER and SERP_API_KEY in .env to pull competitor SERP context for
                      declining and tracked queries.
                    </p>
                  ) : serpBusy && !serpResults ? (
                    <p className="text-muted text-xs">Loading SERP…</p>
                  ) : !serpResults?.length ? (
                    <p className="text-muted text-xs">
                      No cached SERP for this query yet. Click Refresh SERP after enabling a
                      provider.
                    </p>
                  ) : (
                    <ol className="space-y-1.5 text-xs">
                      {serpResults.slice(0, 8).map((r, i) => (
                        <li key={`${r.position ?? i}-${r.url}`} className="text-ink-secondary">
                          <span className="text-muted mr-1.5 font-mono">
                            #{r.position ?? i + 1}
                          </span>
                          <span className="text-ink">{r.title || "—"}</span>
                          {r.url ? (
                            <span className="text-muted block truncate pl-6">{r.url}</span>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
            </section>
          )}

          <section className="panel overflow-hidden">
            <div className="border-b border-surface-border/80 px-5 py-3.5">
              <p className="text-sm font-semibold text-ink">Keyword rankings</p>
              <p className="text-muted mt-0.5 text-xs">
                Lower position is better. Change compares to the prior {days}-day window.
              </p>
            </div>
            {!data?.rankings?.length ? (
              <p className="text-muted px-5 py-6 text-sm">No queries match these filters.</p>
            ) : visibleRankings.length === 0 ? (
              <p className="text-muted px-5 py-6 text-sm">
                All queries hidden.{" "}
                <button type="button" onClick={showAll} className="underline hover:text-ink">
                  Show all
                </button>
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-muted border-b border-surface-border/60 text-left text-[12px] font-medium">
                      <th className="w-10 px-4 py-2.5 font-semibold" />
                      <th className="px-4 py-2.5 font-semibold">Query</th>
                      {(
                        [
                          { key: "position" as const, label: "Pos" },
                          { key: "change" as const, label: "Change" },
                          { key: "impressions" as const, label: "Impr." },
                          { key: "clicks" as const, label: "Clicks" },
                          { key: "ctr" as const, label: "CTR" },
                        ] as const
                      ).map((col) => {
                        const active = sortKey === col.key;
                        return (
                          <th
                            key={col.key}
                            className="cursor-pointer select-none whitespace-nowrap px-4 py-2.5 font-semibold hover:text-ink"
                            onClick={() => handleSort(col.key)}
                          >
                            <span className="inline-flex items-center gap-1">
                              {col.label}
                              {active && sortDir === "desc" && <ArrowDown size={10} />}
                              {active && sortDir === "asc" && <ArrowUp size={10} />}
                            </span>
                          </th>
                        );
                      })}
                      <th className="w-8 px-2 py-2.5 font-semibold" />
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRankings.map((row) => (
                      <RankingTableRow
                        key={row.query}
                        row={row}
                        selected={selected === row.query}
                        busy={busy}
                        onSelect={() => setSelected(row.query)}
                        onTrack={() => void handleTrack(row.query)}
                        onUntrack={() => row.tracked_id && void handleUntrack(row.tracked_id)}
                        onHide={() => {
                          hideQuery(row.query);
                          if (selected === row.query) setSelected(null);
                        }}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function RankingTableRow({
  row,
  selected,
  busy,
  onSelect,
  onTrack,
  onUntrack,
  onHide,
}: {
  row: RankingRow;
  selected: boolean;
  busy: boolean;
  onSelect: () => void;
  onTrack: () => void;
  onUntrack: () => void;
  onHide: () => void;
}) {
  const ctrPct = row.ctr > 1 || row.ctr < 0 ? row.ctr : row.ctr * 100;
  return (
    <tr
      className={`row-hover group cursor-pointer border-b border-[color:var(--border-subtle)] last:border-0 ${
        selected ? "bg-kinexis-focus/5" : ""
      }`}
      onClick={onSelect}
    >
      <td className="px-3 py-2.5">
        <button
          type="button"
          disabled={busy}
          title={row.tracked ? "Unpin keyword" : "Pin keyword"}
          className={`rounded-md p-1.5 ${
            row.tracked ? "bg-kinexis-focus/10 text-kinexis-focus" : "text-muted hover:text-ink"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            if (row.tracked) onUntrack();
            else onTrack();
          }}
        >
          {row.tracked ? <Pin size={14} /> : <PinOff size={14} />}
        </button>
      </td>
      <td className="max-w-[280px] truncate px-4 py-2.5 text-ink" title={row.query}>
        {row.query}
      </td>
      <td className="font-mono-data text-muted whitespace-nowrap px-4 py-2.5">
        {row.position != null ? row.position.toFixed(1) : "—"}
      </td>
      <td className="font-mono-data whitespace-nowrap px-4 py-2.5">
        <ChangeCell change={row.change} />
      </td>
      <td className="font-mono-data text-muted whitespace-nowrap px-4 py-2.5">
        {row.impressions.toLocaleString()}
      </td>
      <td className="font-mono-data text-muted whitespace-nowrap px-4 py-2.5">
        {row.clicks.toLocaleString()}
      </td>
      <td className="font-mono-data text-muted whitespace-nowrap px-4 py-2.5">
        {ctrPct.toFixed(1)}%
      </td>
      <td className="px-2 py-2.5">
        <button
          type="button"
          title="Hide from list"
          className="text-muted hover:bg-surface-hover rounded-md p-1 opacity-0 transition-opacity hover:text-ink group-hover:opacity-100"
          onClick={(e) => {
            e.stopPropagation();
            onHide();
          }}
        >
          <X size={14} />
        </button>
      </td>
    </tr>
  );
}

function ChangeCell({ change }: { change: number | null }) {
  if (change == null) {
    return <span className="text-muted">—</span>;
  }
  // Negative = improved (lower position number)
  if (Math.abs(change) < 0.15) {
    return (
      <span className="text-muted inline-flex items-center gap-0.5">
        <Minus size={12} />0
      </span>
    );
  }
  if (change < 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-kinexis-proof">
        <ArrowUp size={12} />
        {Math.abs(change).toFixed(1)}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 text-kinexis-risk">
      <ArrowDown size={12} />
      {change.toFixed(1)}
    </span>
  );
}

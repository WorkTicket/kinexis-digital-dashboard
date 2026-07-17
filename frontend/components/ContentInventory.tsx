"use client";

import { useMemo, useState } from "react";
import { Metric } from "@/lib/api";
import { buildPageMetrics, formatKpiValue } from "@/lib/metrics";
import { Panel } from "@/components/ui/Panel";
import { FileText, ArrowUpDown } from "lucide-react";

type Props = {
  metrics: Metric[];
};

type SortKey = "clicks" | "impressions" | "ctr" | "sessions" | "conversions" | "cvr";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string; format: "number" | "percent" }[] = [
  { key: "clicks", label: "Clicks", format: "number" },
  { key: "impressions", label: "Impr.", format: "number" },
  { key: "ctr", label: "CTR", format: "percent" },
  { key: "sessions", label: "Sessions", format: "number" },
  { key: "conversions", label: "Conv.", format: "number" },
  { key: "cvr", label: "CVR", format: "percent" },
];

export default function ContentInventory({ metrics }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("clicks");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [periodDays, setPeriodDays] = useState(30);
  const [filter, setFilter] = useState("");

  const pages = useMemo(() => {
    let list = buildPageMetrics(metrics, periodDays);
    if (filter) {
      const q = filter.toLowerCase();
      list = list.filter((p) => p.url.toLowerCase().includes(q));
    }
    list.sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      return sortDir === "desc" ? vb - va : va - vb;
    });
    return list;
  }, [metrics, periodDays, sortKey, sortDir, filter]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (pages.length === 0) {
    return (
      <Panel padding="md">
        <div className="flex items-center gap-3">
          <FileText size={15} className="text-muted shrink-0" />
          <div>
            <p className="text-[13px] font-medium text-ink">Content inventory</p>
            <p className="text-muted text-[11px]">
              No page-level data available. Sync GSC + GA4 to populate.
            </p>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <Panel padding="md">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileText size={14} className="shrink-0 text-kinexis-focus" />
          <h3 className="text-[13px] font-semibold text-ink">
            Content inventory · {pages.length} page{pages.length === 1 ? "" : "s"}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-surface-border/30 p-0.5">
            {([7, 30, 90] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setPeriodDays(d)}
                className={`rounded-md px-3 py-1 text-[11px] font-medium transition-all duration-micro ${
                  periodDays === d
                    ? "bg-surface-elevated text-ink shadow-panel"
                    : "text-muted hover:text-ink-secondary"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter pages…"
            className="placeholder:text-muted-dim w-40 rounded-lg border border-[color:var(--border-subtle)] bg-surface-lighter px-3 py-2 text-[12px] text-ink outline-none transition-colors focus:border-kinexis-focus/30"
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-[12px]">
          <thead>
            <tr className="border-b border-[color:var(--border-subtle)]">
              <th className="text-muted-dim pb-2.5 pr-4 text-[11px] font-medium uppercase tracking-wider">
                Page
              </th>
              {COLUMNS.map((col) => (
                <th key={col.key} className="pb-2.5 pr-3 text-right">
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className="text-muted-dim inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider transition-colors hover:text-ink-secondary"
                  >
                    {col.label}
                    {sortKey === col.key ? (
                      <ArrowUpDown size={10} className="text-kinexis-focus" />
                    ) : (
                      <ArrowUpDown size={10} className="opacity-30" />
                    )}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pages.slice(0, 100).map((page) => (
              <tr
                key={page.url}
                className="border-b border-[color:var(--border-subtle)] transition-colors last:border-0 hover:bg-surface-lighter/40"
              >
                <td className="max-w-[200px] truncate py-3 pr-4">
                  <span className="block truncate text-[12px] text-ink-secondary" title={page.url}>
                    {page.url.replace(/^https?:\/\/[^/]+/, "")}
                  </span>
                </td>
                {COLUMNS.map((col) => (
                  <td key={col.key} className="py-3 pr-3 text-right font-mono text-[12px]">
                    <span className="text-ink-secondary">
                      {formatKpiValue(page[col.key], col.format)}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pages.length > 100 && (
        <p className="text-muted mt-3 text-center text-[11px]">
          Showing top 100 of {pages.length} pages. Use the filter to narrow results.
        </p>
      )}
    </Panel>
  );
}

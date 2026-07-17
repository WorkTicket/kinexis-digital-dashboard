"use client";

import { ArrowDownRight, ArrowUpRight, SearchX } from "lucide-react";
import { PortfolioClient } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import type { SortKey } from "@/hooks/usePortfolioData";

function contractStatusTone(status?: string): "danger" | "warning" | "proof" | "default" {
  switch (status) {
    case "behind":
      return "danger";
    case "on_track":
      return "warning";
    case "ahead":
      return "proof";
    default:
      return "default";
  }
}

function riskBadgeTone(risk: PortfolioClient["risk"]): "danger" | "warning" | "proof" | "default" {
  switch (risk) {
    case "critical":
      return "danger";
    case "stabilizing":
    case "watch":
      return "warning";
    case "healthy":
      return "proof";
    default:
      return "default";
  }
}

function effortTone(effort?: string) {
  if (effort === "low") return "text-kinexis-focus border-kinexis-focus/30";
  if (effort === "high") return "text-kinexis-risk border-kinexis-risk/30";
  return "text-kinexis-signal border-kinexis-signal/30";
}

function formatSync(iso: string | null) {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "\u2014";
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "1d ago";
  if (days > 30) return `${Math.floor(days / 7)}w ago`;
  return `${days}d ago`;
}

function getSyncTone(iso: string | null): "proof" | "warning" | "danger" | "default" {
  if (!iso) return "danger";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 1) return "proof";
  if (days <= 3) return "warning";
  return "danger";
}

function HealthMiniBar({ score }: { score: number }) {
  const color =
    score >= 75 ? "bg-kinexis-proof" : score >= 50 ? "bg-kinexis-signal" : "bg-kinexis-risk";
  const label = score === 0 ? "No data" : `Health: ${score}`;
  return (
    <div className="progress-track w-16" title={label}>
      <div className={`progress-fill ${color} motion-bar`} style={{ width: `${score || 0}%` }} />
    </div>
  );
}

function WowCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="font-mono-data text-xs text-ink-dim">\u2014</span>;
  }
  const up = value >= 0;
  const label = up ? `Up ${value.toFixed(0)}%` : `Down ${Math.abs(value).toFixed(0)}%`;
  return (
    <span
      className={`font-mono-data inline-flex items-center gap-0.5 text-xs ${
        up ? "text-kinexis-proof" : "text-kinexis-risk"
      }`}
      role="text"
      aria-label={label}
    >
      {up ? <ArrowUpRight size={12} aria-hidden /> : <ArrowDownRight size={12} aria-hidden />}
      {up ? "+" : ""}
      {value.toFixed(0)}%
    </span>
  );
}

export type ClientOpenHint = {
  open_insights?: number;
  open_tasks?: number;
  risk?: string;
  tab?: string;
  insight_id?: number;
  task_id?: number;
};

type Props = {
  rows: PortfolioClient[];
  sorted: PortfolioClient[];
  sortKey: SortKey;
  setSortKey: (key: SortKey) => void;
  ownerFilter: string;
  setOwnerFilter: (value: string) => void;
  ownerOptions: string[];
  myBookName: string;
  setMyBook: (name: string) => void;
  assigneePresets: string[];
  priorityOnly: boolean;
  setPriorityOnly: (value: boolean | ((v: boolean) => boolean)) => void;
  reportReadyOnly: boolean;
  setReportReadyOnly: (value: boolean | ((v: boolean) => boolean)) => void;
  tableSearch: string;
  setTableSearch: (value: string) => void;
  hasActiveFilters: boolean;
  clearFilters: () => void;
  bulkMode: boolean;
  bulkSelected: Set<number>;
  toggleBulkSelect: (clientId: number) => void;
  toggleAllVisible: () => void;
  onOpenClient: (clientId: number, hint?: ClientOpenHint) => void;
  onStartTopAction?: (clientId: number) => void;
  startingClientId?: number | null;
};

function primaryCta(row: PortfolioClient) {
  if (row.success_contract?.status === "behind") {
    return { label: "Review contract", tab: "detect" as const };
  }
  if (row.report_ready) {
    return { label: "Generate report", tab: "report" as const };
  }
  if (row.open_tasks > 0) {
    return { label: "Open Execute", tab: "execute" as const };
  }
  if (row.open_insights > 0) {
    return { label: "Open Fix queue", tab: "prescribe" as const };
  }
  if (row.risk === "critical" || row.risk === "watch") {
    return { label: "Open Detect", tab: "detect" as const };
  }
  return { label: "Open", tab: (row.top_action?.cta_tab || "detect") as string };
}

export function PortfolioClientTable({
  rows,
  sorted,
  sortKey,
  setSortKey,
  ownerFilter,
  setOwnerFilter,
  ownerOptions,
  myBookName,
  setMyBook,
  assigneePresets,
  priorityOnly,
  setPriorityOnly,
  reportReadyOnly,
  setReportReadyOnly,
  tableSearch,
  setTableSearch,
  hasActiveFilters,
  clearFilters,
  bulkMode,
  bulkSelected,
  toggleBulkSelect,
  toggleAllVisible,
  onOpenClient,
  onStartTopAction,
  startingClientId = null,
}: Props) {
  const openRow = (row: PortfolioClient) =>
    onOpenClient(row.client_id, {
      open_insights: row.open_insights,
      open_tasks: row.open_tasks,
      risk: row.risk,
      insight_id: row.top_action?.insight_id ?? undefined,
      task_id: row.top_action?.task_id ?? undefined,
      tab: row.top_action?.cta_tab,
    });

  return (
    <>
      <CollapsibleSection label="Filters & sort" className="mb-4">
        <div className="panel flex flex-wrap items-center gap-2 p-3">
          <span className="text-muted mr-1 text-[11px]">Sort</span>
          {(
            [
              ["contract", "Contract"],
              ["risk", "Risk"],
              ["slipping", "Slipping"],
              ["health_score", "Health"],
              ["open_insights", "Problems"],
              ["open_tasks", "Work"],
              ["clicks", "Clicks"],
              ["name", "Name"],
            ] as [SortKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSortKey(key)}
              className={`chip ${sortKey === key ? "chip-active" : ""}`}
            >
              {label}
            </button>
          ))}
          <span className="text-muted ml-2 mr-1 text-[11px]">Owner</span>
          <select
            value={ownerFilter}
            onChange={(e) => setOwnerFilter(e.target.value)}
            className="border border-[color:var(--border-subtle)] bg-surface px-2 py-2 text-xs text-ink"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            <option value="all">All owners</option>
            <option value="unassigned">Unassigned</option>
            {ownerOptions.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <select
            value={myBookName}
            onChange={(e) => setMyBook(e.target.value)}
            className="border border-[color:var(--border-subtle)] bg-surface px-2 py-2 text-xs text-ink"
            style={{ borderRadius: "var(--radius-sm)" }}
            title="My book \u2014 filter to your owner name"
          >
            <option value="">My book: off</option>
            {assigneePresets.map((p) => (
              <option key={p} value={p}>
                My book: {p}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setPriorityOnly((v) => !v)}
            className={`chip ${priorityOnly ? "chip-active" : ""}`}
          >
            Priority 2+
          </button>
          <button
            type="button"
            onClick={() => setReportReadyOnly((v) => !v)}
            className={`chip ${reportReadyOnly ? "chip-active" : ""}`}
          >
            Report ready
          </button>
          <div className="ml-auto flex items-center gap-2">
            <input
              type="search"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              placeholder="Search clients\u2026"
              className="input-field !w-40 !py-2 !text-xs"
            />
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="text-muted motion-micro text-xs hover:text-ink-secondary"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </CollapsibleSection>

      {sorted.length === 0 && rows.length > 0 ? (
        <div className="animate-fade-up py-16">
          <EmptyState
            className="mx-auto w-full max-w-md !border-0 !bg-transparent"
            icon={<SearchX size={20} strokeWidth={1.5} />}
            title="No clients match"
            description="Try adjusting your filters or clearing them to see all clients."
            action={
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Clear all filters
              </Button>
            }
          />
        </div>
      ) : (
        <>
          <div className="mb-6 space-y-3 md:hidden">
            {sorted.map((row) => (
              <div
                key={row.client_id}
                role="button"
                tabIndex={0}
                onClick={() => openRow(row)}
                onKeyDown={(e: React.KeyboardEvent) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    openRow(row);
                  }
                }}
                className="panel motion-micro cursor-pointer px-4 py-4 hover:border-[color:var(--border-strong)]"
              >
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <p className="truncate text-[13px] font-medium text-ink">{row.name}</p>
                    <Badge tone={riskBadgeTone(row.risk)}>{row.risk.replace("_", " ")}</Badge>
                    {row.success_contract?.status && row.success_contract.status !== "unset" && (
                      <Badge tone={contractStatusTone(row.success_contract.status)}>
                        {row.success_contract.status.replace("_", " ")}
                      </Badge>
                    )}
                    {row.slipping && (
                      <span className="text-label mb-0 text-kinexis-momentum">slipping</span>
                    )}
                  </div>
                  <div className="mb-1.5 flex items-center gap-3">
                    <HealthMiniBar score={row.health_score} />
                    <span className="font-mono-data text-xs text-ink-secondary">
                      {row.health_score > 0 ? row.health_score : "—"}
                    </span>
                    <span className="text-muted font-mono-data text-[11px]">
                      {formatSync(row.last_synced_at)}
                    </span>
                    <span className="text-muted font-mono-data text-[11px]">
                      {row.metrics?.gsc_clicks?.toLocaleString() || 0} clicks
                    </span>
                  </div>
                  {row.top_action ? (
                    <p className="truncate text-xs text-ink">{row.top_action.title}</p>
                  ) : (
                    <p className="text-xs text-ink-dim">Ready for review</p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {onStartTopAction && row.top_action && (
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={startingClientId === row.client_id}
                        onClick={(e) => {
                          e.stopPropagation();
                          onStartTopAction(row.client_id);
                        }}
                      >
                        {startingClientId === row.client_id ? "Starting…" : "Start"}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="soft"
                      onClick={(e) => {
                        e.stopPropagation();
                        const cta = primaryCta(row);
                        onOpenClient(row.client_id, { tab: cta.tab });
                      }}
                    >
                      {primaryCta(row).label}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="panel hidden overflow-hidden md:block">
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-[color:var(--border-subtle)] bg-surface text-left">
                    {(
                      [
                        ...(bulkMode ? [["Sel", undefined] as [string, string | undefined]] : []),
                        ["Client", undefined],
                        ["Contract", undefined],
                        ["Risk", undefined],
                        ["Health", undefined],
                        ["Top action", undefined],
                        ["Sync \u00b7 Open", "Sync status, open issues + tasks"],
                        ["Next", undefined],
                        ["WoW Clicks", "Week-over-week"],
                      ] as [string, string | undefined][]
                    ).map(([label, title]) => (
                      <th
                        key={label}
                        title={title}
                        className="text-muted whitespace-nowrap px-4 py-3 text-[12px] font-semibold"
                      >
                        {label === "Sel" ? (
                          <input
                            type="checkbox"
                            checked={
                              sorted.length > 0 &&
                              sorted.every((r) => bulkSelected.has(r.client_id))
                            }
                            onChange={toggleAllVisible}
                            aria-label="Select all visible"
                          />
                        ) : (
                          label
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((row) => (
                    <tr
                      key={row.client_id}
                      className="row-hover cursor-pointer border-b border-[color:var(--border-subtle)] last:border-0"
                      onClick={() => (bulkMode ? toggleBulkSelect(row.client_id) : openRow(row))}
                    >
                      {bulkMode && (
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={bulkSelected.has(row.client_id)}
                            onChange={() => toggleBulkSelect(row.client_id)}
                            aria-label={`Select ${row.name}`}
                          />
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <div className="min-w-0 max-w-[220px]">
                          <p className="flex items-center gap-2 truncate font-medium text-ink">
                            {row.name}
                            {(row.priority || 1) >= 2 && (
                              <span className="text-label mb-0 text-kinexis-focus">
                                P{row.priority}
                              </span>
                            )}
                            {row.slipping && (
                              <span className="text-label mb-0 text-kinexis-momentum">
                                slipping
                              </span>
                            )}
                          </p>
                          <p className="text-muted mt-0.5 truncate text-[11px]">
                            {row.industry || "\u2014"}
                            {row.owner ? ` \u00b7 ${row.owner}` : " \u00b7 Unassigned"}
                            {" \u00b7 "}
                            <span className="font-mono-data">
                              {(row.metrics?.gsc_clicks ?? 0).toLocaleString()}
                            </span>{" "}
                            clicks / 7d
                            {(row.metrics?.leads || 0) > 0 &&
                              ` \u00b7 ${row.metrics!.leads!.toLocaleString()} leads`}
                          </p>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {row.success_contract?.configured ? (
                          <div className="min-w-0">
                            <Badge tone={contractStatusTone(row.success_contract.status)}>
                              {(row.success_contract.status || "unset").replace("_", " ")}
                            </Badge>
                            {row.success_contract.progress?.change_pct != null && (
                              <p className="text-muted font-mono-data mt-1 text-xs">
                                {row.success_contract.progress.change_pct >= 0 ? "+" : ""}
                                {row.success_contract.progress.change_pct}%
                                {row.success_contract.progress.target_delta_pct != null &&
                                  ` / +${row.success_contract.progress.target_delta_pct}%`}
                              </p>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-ink-dim">Unset</span>
                        )}
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="group/risk relative inline-block">
                          <button
                            type="button"
                            className="focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-kinexis-focus/50"
                            style={{ borderRadius: "var(--radius-sm)" }}
                            title={row.risk_reasons?.join(" \u00b7 ") || undefined}
                            aria-label={`${row.risk.replace("_", " ")} risk${
                              row.risk_reasons?.length ? `: ${row.risk_reasons.join(", ")}` : ""
                            }`}
                            aria-describedby={
                              (row.risk_reasons?.length || 0) > 0
                                ? `risk-tooltip-${row.client_id}`
                                : undefined
                            }
                          >
                            <Badge tone={riskBadgeTone(row.risk)}>
                              {row.risk.replace("_", " ")}
                            </Badge>
                          </button>
                          {(row.risk_reasons?.length || 0) > 0 && (
                            <div
                              id={`risk-tooltip-${row.client_id}`}
                              role="tooltip"
                              className="pointer-events-none absolute left-0 top-full z-20 mt-1.5 hidden w-56 border border-[color:var(--border-default)] bg-surface-elevated p-3 text-[11px] text-ink-secondary shadow-dropdown group-focus-within/risk:block group-hover/risk:block"
                              style={{ borderRadius: "var(--radius-md)" }}
                            >
                              <p className="mb-1 font-medium text-ink">Why</p>
                              <ul className="list-disc space-y-0.5 pl-3">
                                {row.risk_reasons!.map((reason) => (
                                  <li key={reason}>{reason}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <HealthMiniBar score={row.health_score} />
                          <span className="text-metric text-base leading-none">
                            {row.health_score > 0 ? row.health_score : "—"}
                          </span>
                        </div>
                      </td>
                      <td className="max-w-[200px] px-4 py-3">
                        {row.top_action ? (
                          <div className="min-w-0">
                            <p className="truncate text-xs text-ink">{row.top_action.title}</p>
                            {row.top_action.effort && (
                              <span
                                className={`badge mt-1 border ${effortTone(row.top_action.effort)}`}
                              >
                                {row.top_action.effort}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-ink-dim">\u2014</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              !row.last_synced_at
                                ? "bg-kinexis-risk"
                                : getSyncTone(row.last_synced_at) === "proof"
                                  ? "bg-kinexis-proof"
                                  : getSyncTone(row.last_synced_at) === "warning"
                                    ? "bg-kinexis-signal"
                                    : "bg-kinexis-risk"
                            }`}
                          />
                          <span className="font-mono-data text-xs text-ink-secondary">
                            {formatSync(row.last_synced_at)}
                          </span>
                        </div>
                        <div className="text-muted mt-0.5 text-[11px]">
                          {row.open_insights} issue{row.open_insights === 1 ? "" : "s"} ·{" "}
                          {row.open_tasks} task{row.open_tasks === 1 ? "" : "s"}
                        </div>
                      </td>
                      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                        <div className="flex flex-wrap items-center gap-2">
                          {onStartTopAction && row.top_action ? (
                            <Button
                              size="sm"
                              variant="primary"
                              disabled={startingClientId === row.client_id}
                              onClick={() => onStartTopAction(row.client_id)}
                            >
                              {startingClientId === row.client_id ? "Starting…" : "Start"}
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="soft"
                              onClick={() => {
                                const cta = primaryCta(row);
                                onOpenClient(row.client_id, { tab: cta.tab });
                              }}
                            >
                              {primaryCta(row).label}
                            </Button>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <WowCell value={row.wow?.clicks} />
                          {(row.wow?.sessions ?? null) !== null && (
                            <WowCell value={row.wow?.sessions} />
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </>
  );
}

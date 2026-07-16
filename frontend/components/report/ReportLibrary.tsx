"use client";

import {
  RefreshCw,
  Sparkles,
  CheckCircle2,
  Circle,
  AlertTriangle,
  Trash2,
  ArrowUpDown,
} from "lucide-react";
import { useState, useMemo } from "react";
import type { ReportLibrary, ReportLibraryItem, ReportReadinessChecklist } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { LoadingState } from "@/components/ui/LoadingState";
import { ErrorState } from "@/components/ui/ErrorState";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import ConfirmDialog from "@/components/ConfirmDialog";
import { MONTH_NAMES } from "@/components/report/reportUtils";
import { motion } from "@/lib/motion";
import type { RefObject } from "react";

type Props = {
  clientName?: string;
  library: ReportLibrary | null;
  libraryLoading: boolean;
  libraryError: string | null;
  score: number;
  statusLabel: string;
  checklist: ReportReadinessChecklist | undefined;
  year: number;
  month: number;
  days: number;
  generating: boolean;
  deleting: boolean;
  highlightGenerate: boolean;
  generatePanelRef: RefObject<HTMLDivElement | null>;
  onRetryLibrary: () => void;
  onYearChange: (year: number) => void;
  onMonthChange: (month: number) => void;
  onDaysChange: (days: number) => void;
  onGenerateMonth: (year?: number, month?: number) => void;
  onGenerateRolling: () => void;
  onOpenSaved: (item: ReportLibraryItem) => void;
  onDeleteReport: (reportId: number) => void;
};

export function ReportLibraryPanel({
  clientName,
  library,
  libraryLoading,
  libraryError,
  score,
  statusLabel,
  checklist,
  year,
  month,
  days,
  generating,
  deleting,
  highlightGenerate,
  generatePanelRef,
  onRetryLibrary,
  onYearChange,
  onMonthChange,
  onDaysChange,
  onGenerateMonth,
  onGenerateRolling,
  onOpenSaved,
  onDeleteReport,
}: Props) {
  const [deleteTarget, setDeleteTarget] = useState<ReportLibraryItem | null>(null);
  const [sortNewest, setSortNewest] = useState(true);

  const sortedReports = useMemo(() => {
    const items = library?.reports ?? [];
    return [...items].sort((a, b) => {
      const dateA = new Date(`${a.year}-${String(a.month).padStart(2, "0")}-01`);
      const dateB = new Date(`${b.year}-${String(b.month).padStart(2, "0")}-01`);
      return sortNewest ? dateB.getTime() - dateA.getTime() : dateA.getTime() - dateB.getTime();
    });
  }, [library?.reports, sortNewest]);
  return (
    <div className="animate-fade-up space-y-6">
      <div className="mission-hero !mb-6">
        <p className="section-label text-muted mb-1.5 text-[11px] font-semibold tracking-wide">
          Report studio
        </p>
        <h2 className="text-display text-[24px] leading-tight sm:text-[28px]">Report library</h2>
        <p className="text-muted mt-2 max-w-xl text-[13px] leading-relaxed">
          Client-facing success packs for {clientName || library?.client_name || "this client"}.
          Open a saved month or generate a new one — nothing builds until you ask.
        </p>
      </div>

      {libraryLoading ? (
        <LoadingState label="Loading library…" variant="spinner" />
      ) : libraryError ? (
        <ErrorState
          title="Library unavailable"
          description={libraryError}
          onRetry={onRetryLibrary}
        />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Panel padding="lg" className="space-y-4 lg:col-span-1">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-muted text-[12px] font-semibold">Readiness</p>
                  <p className="mt-1 font-display text-3xl text-ink">{score}%</p>
                </div>
                <Badge
                  tone={
                    library?.status === "ready"
                      ? "success"
                      : library?.status === "stale"
                        ? "warning"
                        : "default"
                  }
                >
                  {statusLabel}
                </Badge>
              </div>
              <ul className="space-y-2.5">
                {(
                  [
                    ["data_synced", "Data synced recently"],
                    ["work_or_proof", "Completed work or proven levers"],
                    ["has_saved_report", "At least one saved month"],
                    ["narrative_ready", "Narrative ready on a saved month"],
                  ] as const
                ).map(([key, label]) => {
                  const ok = checklist?.[key];
                  return (
                    <li key={key} className="flex items-center gap-2 text-sm">
                      {ok ? (
                        <CheckCircle2 size={14} className="shrink-0 text-kinexis-proof" />
                      ) : (
                        <Circle size={14} className="text-muted shrink-0" />
                      )}
                      <span className={ok ? "text-ink-secondary" : "text-muted"}>{label}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="text-muted text-[11px] leading-relaxed">
                {library?.proven_lever_count || 0} proven levers · {library?.tasks_completed || 0}{" "}
                tasks done · {library?.insights_open || 0} issues open
                {library?.data_freshness ? ` · synced ${library.data_freshness.slice(0, 10)}` : ""}
              </p>
            </Panel>

            <div
              ref={generatePanelRef}
              className={`lg:col-span-2 ${highlightGenerate ? "ring-1 ring-kinexis-focus/40" : ""}`}
              style={highlightGenerate ? { borderRadius: "var(--radius-lg)" } : undefined}
            >
              <Panel padding="lg" className="space-y-4">
                <div>
                  <p className="text-label">Generate</p>
                  <p className="mt-1 text-sm text-ink-secondary">
                    Builds the month, writes the narrative, and saves it to the library.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    value={month}
                    onChange={(e) => onMonthChange(Number(e.target.value))}
                    className="input-field w-auto px-2 py-1.5 text-xs"
                    aria-label="Month"
                  >
                    {MONTH_NAMES.map((name, i) => (
                      <option key={name} value={i + 1}>
                        {name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={year}
                    onChange={(e) => onYearChange(Number(e.target.value))}
                    className="input-field w-auto px-2 py-1.5 text-xs"
                    aria-label="Year"
                  >
                    {Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - i).map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                  <Button
                    onClick={() => onGenerateMonth()}
                    disabled={generating}
                    className={generating ? motion.busy : undefined}
                  >
                    <Sparkles size={13} />
                    {generating ? "Generating…" : "Generate month"}
                  </Button>
                </div>
                <div className="border-t border-[color:var(--border-subtle)] pt-3">
                  <p className="text-label mb-2">Rolling preview</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {[30, 60, 90].map((d) => (
                      <button
                        key={d}
                        type="button"
                        onClick={() => onDaysChange(d)}
                        className={`chip ${days === d ? "chip-active" : ""}`}
                      >
                        {d}d
                      </button>
                    ))}
                    <Button
                      variant="soft"
                      size="sm"
                      onClick={onGenerateRolling}
                      disabled={generating}
                    >
                      Generate preview
                    </Button>
                  </div>
                  <p className="text-muted mt-2 text-[11px]">
                    Rolling previews are not saved. Use monthly generate for client deliverables.
                  </p>
                </div>
              </Panel>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="section-label">Saved months</h3>
              {(library?.reports?.length || 0) > 1 && (
                <button
                  type="button"
                  onClick={() => setSortNewest((v) => !v)}
                  className="btn-ghost gap-1 text-[11px]"
                  title={sortNewest ? "Newest first" : "Oldest first"}
                >
                  <ArrowUpDown size={11} />
                  {sortNewest ? "Newest" : "Oldest"}
                </button>
              )}
            </div>
            {(library?.reports?.length || 0) === 0 ? (
              <EmptyState
                title="No saved reports yet"
                description="Generate a calendar month to create your first client success pack."
                action={
                  <Button size="sm" onClick={() => onGenerateMonth()} disabled={generating}>
                    <Sparkles size={12} />
                    Generate {MONTH_NAMES[month - 1]} {year}
                  </Button>
                }
              />
            ) : (
              <div className="space-y-2">
                {sortedReports.map((item) => (
                  <Panel
                    key={item.id}
                    padding="md"
                    className="flex flex-wrap items-center justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-ink">
                        {item.month_name || MONTH_NAMES[item.month - 1]} {item.year}
                      </p>
                      <p className="text-muted text-xs">
                        Saved {item.generated_at?.slice(0, 10) || "—"}
                        {item.stale ? " · data synced since save" : ""}
                        {!item.narrative_ready ? " · narrative weak" : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {item.stale && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-kinexis-signal">
                          <AlertTriangle size={11} /> Stale
                        </span>
                      )}
                      <Button variant="soft" size="sm" onClick={() => onOpenSaved(item)}>
                        Open
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onGenerateMonth(item.year, item.month)}
                        disabled={generating}
                      >
                        <RefreshCw size={12} /> Refresh
                      </Button>
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(item)}
                        className="icon-btn text-muted hover:!text-kinexis-risk"
                        title={`Delete ${item.month_name || MONTH_NAMES[item.month - 1]} ${item.year}`}
                        aria-label={`Delete ${item.month_name || MONTH_NAMES[item.month - 1]} ${item.year}`}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </Panel>
                ))}
              </div>
            )}
          </div>

          <ConfirmDialog
            open={deleteTarget !== null}
            title="Delete report"
            description={
              deleteTarget
                ? `Permanently delete ${deleteTarget.month_name || MONTH_NAMES[deleteTarget.month - 1]} ${deleteTarget.year}? This cannot be undone.`
                : ""
            }
            confirmLabel={deleting ? "Deleting…" : "Delete"}
            danger
            busy={deleting}
            onConfirm={async () => {
              if (deleteTarget) {
                try {
                  await onDeleteReport(deleteTarget.id);
                } finally {
                  setDeleteTarget(null);
                }
              }
            }}
            onCancel={() => setDeleteTarget(null)}
          />
        </>
      )}
    </div>
  );
}

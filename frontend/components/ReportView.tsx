"use client";

import { Printer, FileDown, ArrowLeft, RefreshCw, Copy } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { LoadingState } from "@/components/ui/LoadingState";
import { ErrorState } from "@/components/ui/ErrorState";
import { ReportLibraryPanel } from "@/components/report/ReportLibrary";
import { ReportDocument } from "@/components/report/ReportDocument";
import { useReportView } from "@/hooks/useReportView";
import { useToast } from "@/components/Toast";
import { motion } from "@/lib/motion";

type Props = {
  clientId: number;
  clientName?: string;
  /** Bump to jump to library and highlight Generate */
  focusGenerateKey?: number;
  onStatusChange?: (status: string) => void;
};

export default function ReportView({
  clientId,
  clientName,
  focusGenerateKey = 0,
  onStatusChange,
}: Props) {
  const rv = useReportView({ clientId, focusGenerateKey, onStatusChange });
  const { success: toastSuccess, error: toastError } = useToast();

  const copyClientReportLink = async () => {
    if (typeof window === "undefined" || !rv.report) return;
    try {
      const { api } = await import("@/lib/api");
      const savedId = rv.report.monthly_report_id;
      const res = await api.actions.createReportShare(clientId, {
        reportId: typeof savedId === "number" ? savedId : undefined,
        expiresDays: 90,
      });
      const url = res.html_url || res.url;
      if (!url) throw new Error("No share URL returned");
      await navigator.clipboard?.writeText(url);
      const reachable = !/127\.0\.0\.1|localhost/i.test(url);
      toastSuccess(
        reachable
          ? "Client report link copied — share with your client"
          : "Report link copied (localhost). Set Public base URL in Settings → Client portal."
      );
    } catch {
      toastError("Could not create client report link — is the backend running?");
    }
  };

  const copyPulseLink = async () => {
    if (typeof window === "undefined") return;
    try {
      const { api } = await import("@/lib/api");
      const res = await api.actions.createPulseShare(clientId, 90);
      const url =
        res.html_url ||
        res.url ||
        `${window.location.port === "3000" ? "http://127.0.0.1:8000" : window.location.origin}${res.api_path}/html`;
      await navigator.clipboard?.writeText(url);
      const reachable = !/127\.0\.0\.1|localhost/i.test(url);
      toastSuccess(
        reachable
          ? "Success Pulse link copied — share with your client"
          : "Pulse link copied (localhost). Set Public base URL in Settings → Client portal."
      );
    } catch {
      toastError("Could not create pulse link — is the backend running?");
    }
  };

  if (rv.screen === "library") {
    return (
      <ReportLibraryPanel
        clientName={clientName}
        library={rv.library}
        libraryLoading={rv.libraryLoading}
        libraryError={rv.libraryError}
        score={rv.score}
        statusLabel={rv.statusLabel}
        checklist={rv.checklist}
        year={rv.year}
        month={rv.month}
        days={rv.days}
        generating={rv.generating}
        highlightGenerate={rv.highlightGenerate}
        generatePanelRef={rv.generatePanelRef}
        onRetryLibrary={() => void rv.loadLibrary()}
        onYearChange={rv.setYear}
        onMonthChange={rv.setMonth}
        onDaysChange={rv.setDays}
        onGenerateMonth={(y, m) => void rv.generateMonth(y, m)}
        onGenerateRolling={() => void rv.generateRollingPreview()}
        onOpenSaved={(item) => void rv.openSaved(item)}
        onDeleteReport={(id) => void rv.deleteReport(id)}
        deleting={rv.deleting}
      />
    );
  }

  return (
    <div className="animate-fade-up space-y-6">
      <div className="report-no-print flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <Button variant="ghost" size="sm" onClick={() => rv.setScreen("library")}>
            <ArrowLeft size={12} /> Library
          </Button>
          <div>
            <p className="section-label text-muted mb-1 text-[11px] font-semibold tracking-wide">
              Client pack
            </p>
            <h2 className="text-display text-[24px] leading-tight sm:text-[28px]">
              Client success report
            </h2>
            <p className="text-muted mt-1.5 text-[13px]">
              Proof of work for {clientName || rv.report?.client.name || "client"} ·{" "}
              {rv.periodLabel}
              {rv.report?.from_cache ? " · saved" : rv.report ? " · just generated" : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-col items-stretch gap-3 sm:items-end">
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              onClick={() => void rv.downloadPdf()}
              disabled={rv.downloading || rv.viewerLoading || !rv.report}
              className={rv.downloading ? motion.busy : undefined}
            >
              <FileDown size={13} />
              {rv.downloading ? "Building PDF…" : "Download PDF"}
            </Button>
            <Button variant="soft" onClick={rv.openPrintable} disabled={!rv.report}>
              <Printer size={13} /> Open HTML / Print
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <Button variant="ghost" size="sm" onClick={() => void copyClientReportLink()} disabled={!rv.report}>
              <Copy size={12} /> Share with client
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void copyPulseLink()}>
              <Copy size={12} /> Share pulse
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void rv.refreshCurrent()}
              disabled={rv.generating}
            >
              <RefreshCw size={12} />
              {rv.generating ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
          {rv.checklist && rv.exportBlocked && !rv.report?.from_cache && (
            <p className="max-w-xs text-right text-xs leading-relaxed text-muted">
              PDF is ready to share; a stronger checklist will raise confidence for QBRs.
            </p>
          )}
        </div>
      </div>

      {rv.viewerLoading || rv.generating ? (
        <LoadingState
          label={rv.generating ? "Generating report…" : "Opening report…"}
          variant={rv.generating ? "cards" : "spinner"}
        />
      ) : rv.viewerError || !rv.report ? (
        <ErrorState
          title="Report unavailable"
          description={
            rv.viewerError || "No data yet for this period. Sync connectors, then generate."
          }
          onRetry={() => void rv.refreshCurrent()}
        />
      ) : (
        <ReportDocument
          report={rv.report}
          provenLevers={rv.provenLevers}
          agency={rv.agency}
          periodLabel={rv.periodLabel}
          stale={rv.currentStale}
        />
      )}
    </div>
  );
}

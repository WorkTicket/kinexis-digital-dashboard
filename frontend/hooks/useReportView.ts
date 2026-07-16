"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, SuccessReport, GrowthLever, ReportLibrary, ReportLibraryItem } from "@/lib/api";
import { getApiHeaders } from "@/lib/api/client";
import { useToast } from "@/components/Toast";
import {
  MONTH_NAMES,
  prevMonth,
  resolveAgency,
  readinessScore,
  exportBlocked,
} from "@/components/report/reportUtils";

type Options = {
  clientId: number;
  focusGenerateKey?: number;
  onStatusChange?: (status: string) => void;
};

export function useReportView({ clientId, focusGenerateKey = 0, onStatusChange }: Options) {
  const { success, error: toastError, info: toastInfo } = useToast();
  const initial = useMemo(() => prevMonth(), []);
  const [screen, setScreen] = useState<"library" | "viewer">("library");
  const [library, setLibrary] = useState<ReportLibrary | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  const [mode, setMode] = useState<"monthly" | "rolling">("monthly");
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [days, setDays] = useState(30);
  const [report, setReport] = useState<SuccessReport | null>(null);
  const [provenLevers, setProvenLevers] = useState<GrowthLever[]>([]);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const generatePanelRef = useRef<HTMLDivElement>(null);
  const [highlightGenerate, setHighlightGenerate] = useState(false);

  const loadLibrary = useCallback(async () => {
    setLibraryLoading(true);
    setLibraryError(null);
    try {
      const data = await api.actions.getReportLibrary(clientId);
      setLibrary(data);
      onStatusChange?.(data.status);
    } catch (e) {
      setLibrary(null);
      setLibraryError(e instanceof Error ? e.message : "Failed to load report library");
      onStatusChange?.("draft");
    } finally {
      setLibraryLoading(false);
    }
  }, [clientId, onStatusChange]);

  useEffect(() => {
    loadLibrary();
  }, [loadLibrary]);

  useEffect(() => {
    if (focusGenerateKey > 0) {
      setScreen("library");
      setHighlightGenerate(true);
      setTimeout(() => {
        generatePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 50);
      const t = setTimeout(() => setHighlightGenerate(false), 2400);
      return () => clearTimeout(t);
    }
    return;
  }, [focusGenerateKey]);

  const openSaved = useCallback(
    async (item: ReportLibraryItem) => {
      setScreen("viewer");
      setMode("monthly");
      setYear(item.year);
      setMonth(item.month);
      setViewerLoading(true);
      setViewerError(null);
      try {
        const [data, leversRes] = await Promise.all([
          api.actions.getReport(clientId, { year: item.year, month: item.month }),
          api.levers.reportLevers(clientId).catch((e) => {
            console.warn("Failed to load report levers", e);
            toastInfo("Report loaded, but proven levers unavailable");
            return { levers: [] as GrowthLever[] };
          }),
        ]);
        setReport(data);
        setProvenLevers(leversRes.levers || []);
      } catch (e) {
        setReport(null);
        setViewerError(e instanceof Error ? e.message : "Failed to open report");
      } finally {
        setViewerLoading(false);
      }
    },
    [clientId, toastInfo]
  );

  const generateMonth = useCallback(
    async (y = year, m = month) => {
      setGenerating(true);
      setViewerError(null);
      try {
        const [data, leversRes] = await Promise.all([
          api.actions.generateMonthlyReport(clientId, y, m),
          api.levers.reportLevers(clientId).catch((e) => {
            console.warn("Failed to load report levers", e);
            toastInfo("Report generated, but proven levers unavailable");
            return { levers: [] as GrowthLever[] };
          }),
        ]);
        setYear(y);
        setMonth(m);
        setMode("monthly");
        setReport(data);
        setProvenLevers(leversRes.levers || []);
        setScreen("viewer");
        success(`${MONTH_NAMES[m - 1]} ${y} report generated and saved`);
        await loadLibrary();
      } catch (e) {
        toastError(e instanceof Error ? e.message : "Failed to generate report");
      } finally {
        setGenerating(false);
      }
    },
    [clientId, loadLibrary, month, year, success, toastError, toastInfo]
  );

  const generateRollingPreview = useCallback(async () => {
    setGenerating(true);
    setViewerError(null);
    setMode("rolling");
    setScreen("viewer");
    setViewerLoading(true);
    try {
      const [data, leversRes] = await Promise.all([
        api.actions.getReport(clientId, { days, refresh: true }),
        api.levers.reportLevers(clientId).catch((e) => {
          console.warn("Failed to load report levers", e);
          toastInfo("Preview ready, but proven levers unavailable");
          return { levers: [] as GrowthLever[] };
        }),
      ]);
      setReport(data);
      setProvenLevers(leversRes.levers || []);
      success(`Rolling ${days}d preview ready (not saved)`);
    } catch (e) {
      setReport(null);
      setViewerError(e instanceof Error ? e.message : "Failed to build preview");
    } finally {
      setViewerLoading(false);
      setGenerating(false);
    }
  }, [clientId, days, success, toastInfo]);

  const refreshCurrent = useCallback(async () => {
    if (mode !== "monthly") {
      await generateRollingPreview();
      return;
    }
    await generateMonth(year, month);
  }, [mode, year, month, generateMonth, generateRollingPreview]);

  const reportOpts = useMemo(
    () => (mode === "monthly" ? { year, month } : { days }),
    [mode, year, month, days]
  );

  const openPrintable = useCallback(async () => {
    try {
      const url = api.actions.reportHtmlUrl(clientId, reportOpts);
      const res = await fetch(url, { headers: await getApiHeaders() });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status}: ${err}`);
      }
      const html = await res.text();
      const blob = new Blob([html], { type: "text/html" });
      const blobUrl = URL.createObjectURL(blob);
      const win = window.open(blobUrl, "_blank");
      if (!win) {
        toastError("Pop-up blocked — allow pop-ups to open the printable report");
      }
      // Keep blob alive long enough for the new tab to load
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Failed to open printable report");
    }
  }, [clientId, reportOpts, toastError]);

  const downloadPdf = useCallback(async () => {
    const checklist = library?.checklist;
    if (exportBlocked(checklist) && !report?.from_cache) {
      toastError("Report not ready to export — complete the checklist first.");
      setScreen("library");
      return;
    }
    setDownloading(true);
    try {
      await api.actions.downloadReportPdf(clientId, reportOpts);
      success("PDF downloaded — ready to email");
    } catch (e) {
      toastError(
        e instanceof Error ? e.message : "PDF unavailable. Open HTML and use Print → Save as PDF."
      );
      openPrintable();
    } finally {
      setDownloading(false);
    }
  }, [clientId, reportOpts, library, report, openPrintable, success, toastError]);

  const deleteReport = useCallback(
    async (reportId: number) => {
      setDeleting(true);
      try {
        await api.actions.deleteReport(clientId, reportId);
        success("Report deleted");
        await loadLibrary();
      } catch (e) {
        toastError(e instanceof Error ? e.message : "Failed to delete report");
      } finally {
        setDeleting(false);
      }
    },
    [clientId, loadLibrary, success, toastError]
  );

  const periodLabel = report
    ? report.period.mode === "monthly"
      ? `${report.period.month_name || MONTH_NAMES[(report.period.month || 1) - 1]} ${report.period.year}`
      : `${report.period.start} → ${report.period.end}`
    : mode === "monthly"
      ? `${MONTH_NAMES[month - 1]} ${year}`
      : `Last ${days} days`;

  const agency = resolveAgency(report);
  const checklist = library?.checklist;
  const score = readinessScore(checklist);
  const statusLabel =
    library?.status === "ready"
      ? "Ready"
      : library?.status === "stale"
        ? "Stale"
        : library?.status === "unsaved"
          ? "Unsaved"
          : "Draft";

  const currentStale = library?.reports.find((r) => r.year === year && r.month === month)?.stale;

  return {
    screen,
    setScreen,
    library,
    libraryLoading,
    libraryError,
    loadLibrary,
    year,
    setYear,
    month,
    setMonth,
    days,
    setDays,
    report,
    provenLevers,
    viewerLoading,
    viewerError,
    generating,
    downloading,
    deleting,
    generatePanelRef,
    highlightGenerate,
    openSaved,
    generateMonth,
    generateRollingPreview,
    refreshCurrent,
    openPrintable,
    downloadPdf,
    deleteReport,
    periodLabel,
    agency,
    checklist,
    score,
    statusLabel,
    currentStale,
    exportBlocked: exportBlocked(checklist),
  };
}

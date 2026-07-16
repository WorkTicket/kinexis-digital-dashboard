import { API_BASE, getApiHeaders, request } from "../client";
import type {
  ContentBrief,
  FunnelReport,
  GrowthLever,
  PortfolioBenchmark,
  ReportLibrary,
  ReportLibraryItem,
  SuccessContractPayload,
  SuccessReport,
  TodayItem,
} from "../types";

export const actions = {
  getLatestPlan: (clientId: number, init?: RequestInit) =>
    request<{
      id: number;
      title: string;
      content: unknown[];
      created_at: string;
      status?: string;
    }>(`/actions/plans/${clientId}/latest`, init),
  listPlans: (clientId: number, status?: string) => {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    return request<
      { id: number; title: string; content: unknown[]; created_at: string; status?: string }[]
    >(`/actions/plans/${clientId}${qs}`);
  },
  generatePlan: (clientId: number) =>
    request<{ status: string; plan_id?: number; message?: string }>(
      `/actions/plans/generate/${clientId}`,
      { method: "POST" },
      300000
    ),
  getKnownEvents: (clientId: number, init?: RequestInit) =>
    request<{
      client_id: number;
      events: { name: string; start: string; end: string; type: string }[];
    }>(`/actions/known-events/${clientId}`, init),
  getFunnel: (clientId: number, init?: RequestInit) =>
    request<FunnelReport>(`/actions/funnel/${clientId}`, init),
  getContract: (clientId: number, init?: RequestInit) =>
    request<SuccessContractPayload>(`/actions/contract/${clientId}`, init),
  getImpact: (taskId: number, init?: RequestInit) =>
    request<{
      status: string;
      message?: string;
      outcome?: string;
      auto_outcome?: string;
      outcome_manual?: boolean;
      confidence?: string;
      evidence_label?: string;
      confidence_note?: string;
      caution_notes?: string[];
      checked_at?: string;
      metrics_improved?: number;
      metrics_declined?: number;
      avg_primary_metric_change?: number;
      primary_metric?: string;
      proof_copy?: string;
      funnel_proof?: {
        metric: string;
        label: string;
        before: number;
        after: number;
        change_pct: number | null;
      }[];
      revenue_story?: string | null;
      window_days?: number;
      causal_verdict?: {
        verdict?: string;
        causal_evidence_label?: string;
        matched_control?: Record<string, unknown> | null;
        bootstrap_ci?: {
          ci_lower?: number | null;
          ci_upper?: number | null;
          median_effect?: number | null;
          ci_excludes_zero?: boolean;
          ci_level?: number;
        };
      } | null;
      details?: {
        metric: string;
        before: number;
        after: number;
        change_pct: number | null;
        is_primary?: boolean;
      }[];
    }>(`/actions/impact/${taskId}`, init),
  getImpactBatch: (taskIds: number[], init?: RequestInit) => {
    const ids = taskIds.slice(0, 50).join(",");
    return request<
      Record<
        string,
        {
          status: string;
          message?: string;
          outcome?: string;
          auto_outcome?: string;
          outcome_manual?: boolean;
          confidence?: string;
          evidence_label?: string;
          confidence_note?: string;
          caution_notes?: string[];
          checked_at?: string;
          metrics_improved?: number;
          metrics_declined?: number;
          avg_primary_metric_change?: number;
          primary_metric?: string;
          proof_copy?: string;
          window_days?: number;
          causal_verdict?: {
            verdict?: string;
            causal_evidence_label?: string;
            matched_control?: Record<string, unknown> | null;
            bootstrap_ci?: {
              ci_lower?: number | null;
              ci_upper?: number | null;
              median_effect?: number | null;
              ci_excludes_zero?: boolean;
              ci_level?: number;
            };
          } | null;
          details?: {
            metric: string;
            before: number;
            after: number;
            change_pct: number | null;
            is_primary?: boolean;
          }[];
        }
      >
    >(`/actions/impact/batch?task_ids=${encodeURIComponent(ids)}`, init);
  },
  recheckImpact: (taskId: number) =>
    request<{ status: string }>(`/actions/impact/recheck/${taskId}`, { method: "POST" }),
  setImpactOutcome: (taskId: number, outcome: "win" | "loss" | "flat" | "auto") =>
    request<{
      status: string;
      outcome?: string;
      auto_outcome?: string;
      message?: string;
    }>(`/actions/impact/outcome/${taskId}`, {
      method: "POST",
      body: JSON.stringify({ outcome }),
    }),
  portfolioWins: (days = 30) =>
    request<{
      days: number;
      wins: { task_id: number; client_id: number; avg_primary_change: number; label: string }[];
    }>(`/actions/impact/wins/portfolio?days=${days}`),
  aiValue: () =>
    request<{
      clients: {
        client_id: number;
        client_name: string;
        plans_adopted: number;
        attributed_lift_avg: number;
        ai_value_score: number;
      }[];
    }>("/actions/ai-value"),
  benchmark: () => request<PortfolioBenchmark>("/actions/benchmark"),
  fixEffectiveness: () =>
    request<{
      fixes: {
        fix_type: string;
        wins: number;
        total: number;
        win_rate: number | null;
        median_lift_pct: number | null;
        client_count: number;
        measured: boolean;
      }[];
    }>("/actions/fix-effectiveness"),
  startTopAction: (clientId: number) =>
    request<{
      ok: boolean;
      task_id: number;
      client_id: number;
      insight_id?: number | null;
      assigned_to?: string;
      status: string;
      due_date?: string | null;
      cta_tab: string;
      title: string;
      detail?: string;
      open_cursor: boolean;
      result_notes?: string | null;
      target_query?: string | null;
      target_url?: string | null;
      playbook_pattern?: string | null;
    }>(`/actions/start-top-action/${clientId}`, { method: "POST" }),
  createPulseShare: (clientId: number, expiresDays = 90) =>
    request<{
      token: string;
      client_id: number;
      expires_at?: string | null;
      path: string;
      api_path: string;
      html_path?: string;
      html_url?: string;
      url?: string;
    }>("/pulse/share", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, expires_days: expiresDays }),
    }),
  createReportShare: (clientId: number, opts?: { reportId?: number; expiresDays?: number }) =>
    request<{
      token: string;
      client_id: number;
      report_id?: number | null;
      expires_at?: string | null;
      path: string;
      api_path: string;
      html_url?: string;
      url?: string;
    }>("/portal/report/share", {
      method: "POST",
      body: JSON.stringify({
        client_id: clientId,
        report_id: opts?.reportId ?? null,
        expires_days: opts?.expiresDays ?? 90,
      }),
    }),
  today: (opts?: { owner?: string; assignee?: string }) => {
    const params = new URLSearchParams();
    if (opts?.owner) params.set("owner", opts.owner);
    if (opts?.assignee) params.set("assignee", opts.assignee);
    const qs = params.toString();
    return request<{ generated_at: string; items: TodayItem[] }>(
      `/actions/today${qs ? `?${qs}` : ""}`
    );
  },
  listBriefs: (clientId: number) => request<ContentBrief[]>(`/actions/briefs/${clientId}`),
  generateBrief: (clientId: number, insightId: number) =>
    request<{ status: string; brief_id?: number; message?: string }>(
      `/actions/briefs/generate/${clientId}/${insightId}`,
      { method: "POST" },
      300000
    ),
  updateBriefStatus: (briefId: number, status: string) =>
    request<{ ok: boolean }>(`/actions/briefs/${briefId}/status`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    }),
  getReport: (
    clientId: number,
    opts?: { days?: number; year?: number; month?: number; refresh?: boolean }
  ) => {
    const qs = new URLSearchParams();
    if (opts?.year != null && opts?.month != null) {
      qs.set("year", String(opts.year));
      qs.set("month", String(opts.month));
    } else {
      qs.set("days", String(opts?.days ?? 30));
    }
    if (opts?.refresh) qs.set("refresh", "true");
    return request<SuccessReport>(`/actions/report/${clientId}?${qs.toString()}`);
  },
  getReportLibrary: (clientId: number) =>
    request<ReportLibrary>(`/actions/report/${clientId}/library`),
  reportHtmlUrl: (
    clientId: number,
    opts?: { days?: number; year?: number; month?: number; refresh?: boolean }
  ) => {
    const qs = new URLSearchParams();
    if (opts?.year != null && opts?.month != null) {
      qs.set("year", String(opts.year));
      qs.set("month", String(opts.month));
    } else {
      qs.set("days", String(opts?.days ?? 30));
    }
    if (opts?.refresh) qs.set("refresh", "true");
    return `${API_BASE}/actions/report/${clientId}/html?${qs.toString()}`;
  },
  downloadReportPdf: async (
    clientId: number,
    opts?: { days?: number; year?: number; month?: number; refresh?: boolean }
  ) => {
    const qs = new URLSearchParams();
    if (opts?.year != null && opts?.month != null) {
      qs.set("year", String(opts.year));
      qs.set("month", String(opts.month));
    } else {
      qs.set("days", String(opts?.days ?? 30));
    }
    if (opts?.refresh) qs.set("refresh", "true");
    const res = await fetch(`${API_BASE}/actions/report/${clientId}/pdf?${qs.toString()}`, {
      headers: await getApiHeaders(),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(
        res.status === 503
          ? "PDF engine unavailable. Opening HTML — use Print → Save as PDF."
          : `${res.status}: ${err}`
      );
    }
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") || "";
    const match = /filename="?([^"]+)"?/.exec(cd);
    const filename = match?.[1] || `success-report-${clientId}.pdf`;
    const url = URL.createObjectURL(blob);
    if (typeof document !== "undefined") {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
  generateMonthlyReport: (clientId: number, year: number, month: number) =>
    request<SuccessReport>(
      `/actions/report/${clientId}/monthly?year=${year}&month=${month}`,
      { method: "POST" },
      120000
    ),
  listMonthlyReports: (clientId: number) =>
    request<ReportLibraryItem[]>(`/actions/report/${clientId}/monthly/list`),
  deleteReport: (clientId: number, reportId: number) =>
    request<{ ok: boolean }>(`/actions/report/${clientId}/monthly/${reportId}`, {
      method: "DELETE",
    }),
};

export const levers = {
  list: (clientId: number, synthesize = true) =>
    request<GrowthLever[]>(
      `/levers/client/${clientId}?synthesize=${synthesize ? "true" : "false"}`
    ),
  synthesize: (clientId: number) =>
    request<GrowthLever[]>(`/levers/client/${clientId}/synthesize`, { method: "POST" }),
  get: (leverId: number) => request<GrowthLever>(`/levers/${leverId}`),
  setStatus: (
    leverId: number,
    body: {
      status: string;
      task_id?: number;
      brief_id?: number;
      impact_summary?: string;
      confidence_label?: string;
      include_in_report?: boolean;
    }
  ) =>
    request<GrowthLever>(`/levers/${leverId}/status`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  linkTask: (leverId: number, taskId: number) =>
    request<GrowthLever>(`/levers/${leverId}/link-task`, {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
    }),
  linkBrief: (leverId: number, briefId: number) =>
    request<GrowthLever>(`/levers/${leverId}/link-brief`, {
      method: "POST",
      body: JSON.stringify({ brief_id: briefId }),
    }),
  reportLevers: (clientId: number) =>
    request<{ levers: GrowthLever[] }>(`/levers/report/${clientId}`),
  portfolioReportReady: () =>
    request<{ by_client: Record<string, number> }>("/levers/portfolio/report-ready"),
};

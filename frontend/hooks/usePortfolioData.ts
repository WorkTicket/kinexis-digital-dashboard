"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, PortfolioClient, SuccessBoard, TodayItem } from "@/lib/api";
import { downloadCSV } from "@/lib/utils";
import { useToast } from "@/components/Toast";

const MY_BOOK_KEY = "kinexis-my-book-owner";

export type SortKey =
  | "risk"
  | "health_score"
  | "open_insights"
  | "open_tasks"
  | "clicks"
  | "name"
  | "slipping"
  | "contract";

export type AttentionFilter =
  "all" | "critical" | "watch" | "slipping" | "overdue" | "stale" | "off_contract";

export type PortfolioWin = {
  task_id: number;
  avg_primary_change: number;
  label: string;
  client_id: number;
  client_name?: string;
};

export type AiValueRow = {
  client_id: number;
  client_name: string;
  plans_adopted: number;
  attributed_lift_avg: number;
  ai_value_score: number;
};

export type CapacityOwner = {
  name: string;
  open: number;
  overdue: number;
};

const EMPTY_METRICS: PortfolioClient["metrics"] = {
  gsc_clicks: 0,
  gsc_impressions: 0,
  ga4_sessions: 0,
  ga4_conversions: 0,
  ctr: 0,
  conversion_rate: 0,
  leads: 0,
  revenue: 0,
  ad_cost: 0,
};

const EMPTY_WOW: PortfolioClient["wow"] = {
  clicks: null,
  sessions: null,
  conversions: null,
  leads: null,
  revenue: null,
  ad_cost: null,
};

function normalizePortfolioClient(row: PortfolioClient): PortfolioClient {
  return {
    ...row,
    metrics: { ...EMPTY_METRICS, ...(row.metrics || {}) },
    wow: { ...EMPTY_WOW, ...(row.wow || {}) },
    rankings: row.rankings || {},
    risk: row.risk || "no_data",
    // Never coerce missing scores to 0 (0 = no_data special case). Prefer nullish → 0 only when truly absent.
    health_score:
      row.health_score == null || !Number.isFinite(Number(row.health_score))
        ? 0
        : Math.max(0, Math.round(Number(row.health_score))),
    open_insights: row.open_insights ?? 0,
    open_insights_high: row.open_insights_high ?? 0,
    open_tasks: row.open_tasks ?? 0,
  };
}

function contractRank(status?: string): number {
  switch (status) {
    case "behind":
      return 0;
    case "on_track":
      return 1;
    case "no_data":
      return 2;
    case "unset":
      return 3;
    case "ahead":
      return 4;
    default:
      return 5;
  }
}

export function usePortfolioData() {
  const { info: toastInfo, success: toastSuccess } = useToast();
  const [rows, setRows] = useState<PortfolioClient[]>([]);
  const [wins, setWins] = useState<PortfolioWin[]>([]);
  const [todayItems, setTodayItems] = useState<TodayItem[]>([]);
  const [aiValue, setAiValue] = useState<AiValueRow[]>([]);
  const [successBoard, setSuccessBoard] = useState<SuccessBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("contract");
  const [filter, setFilter] = useState<AttentionFilter>("all");
  const [ownerFilter, setOwnerFilter] = useState<string>("all");
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [reportReadyOnly, setReportReadyOnly] = useState(false);
  const [myBookName, setMyBookName] = useState<string>("");
  const [assigneePresets, setAssigneePresets] = useState<string[]>(["Unassigned"]);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [tableSearch, setTableSearch] = useState("");
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelected, setBulkSelected] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    try {
      setMyBookName(localStorage.getItem(MY_BOOK_KEY) || "");
    } catch {
      /* ignore */
    }
    api.settings
      .get()
      .then((s) => {
        const raw = s.assignee_presets || "Unassigned";
        const list = raw
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean);
        if (list.length) setAssigneePresets(list);
        const agent = (s.my_agent_name || "").trim();
        if (agent) {
          try {
            const existing = localStorage.getItem(MY_BOOK_KEY) || "";
            if (!existing) {
              localStorage.setItem(MY_BOOK_KEY, agent);
              setMyBookName(agent);
            }
          } catch {
            /* ignore */
          }
        }
      })
      .catch((e) => {
        console.warn("Failed to load assignee presets", e);
      });
  }, []);

  const setMyBook = useCallback((name: string) => {
    setMyBookName(name);
    try {
      if (name) localStorage.setItem(MY_BOOK_KEY, name);
      else localStorage.removeItem(MY_BOOK_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const fetchPortfolio = useCallback(async () => {
    const todayOpts =
      ownerFilter !== "all"
        ? { owner: ownerFilter === "unassigned" ? "unassigned" : ownerFilter }
        : myBookName
          ? { owner: myBookName }
          : undefined;
    const warnSecondary = (label: string) => (e: unknown) => {
      console.warn(`Portfolio secondary load failed: ${label}`, e);
      toastInfo(`Couldn\u2019t load ${label}`);
    };
    const [bench, winData, today, aiVal] = await Promise.all([
      api.actions.benchmark(),
      api.actions.portfolioWins(30).catch((e) => {
        warnSecondary("30-day wins")(e);
        return { wins: [] };
      }),
      api.actions.today(todayOpts).catch((e) => {
        warnSecondary("today\u2019s work")(e);
        return { items: [] as TodayItem[] };
      }),
      api.actions.aiValue().catch((e) => {
        warnSecondary("AI value")(e);
        return { clients: [] };
      }),
    ]);
    const clients = Array.isArray(bench) ? bench : bench.clients || [];
    setRows(clients.map(normalizePortfolioClient));
    setSuccessBoard(Array.isArray(bench) ? null : bench.success_board || null);
    setWins(winData.wins || []);
    setTodayItems(today.items || []);
    setAiValue(aiVal.clients || []);
  }, [ownerFilter, myBookName, toastInfo]);

  const loadPortfolio = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      await fetchPortfolio();
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, [fetchPortfolio]);

  useEffect(() => {
    void loadPortfolio();
  }, [loadPortfolio]);

  const handleSyncAll = async () => {
    setSyncingAll(true);
    setSyncNote(null);
    try {
      const result = await api.metrics.syncAll();
      if (result.queued) {
        const n = result.client_count ?? result.client_ids?.length ?? 0;
        setSyncNote(result.message || `Queued sync for ${n} client${n === 1 ? "" : "s"}`);
      } else {
        const ok = (result.clients || []).filter((c) => !c.error).length;
        const failed = (result.clients || []).filter((c) => c.error).length;
        setSyncNote(
          failed
            ? `Synced ${ok} client${ok === 1 ? "" : "s"} (${failed} skipped / failed)`
            : `Synced ${ok} client${ok === 1 ? "" : "s"}`
        );
      }
      await fetchPortfolio();
    } catch (e) {
      setSyncNote(e instanceof Error ? e.message : "Sync all failed");
    } finally {
      setSyncingAll(false);
    }
  };

  const portfolioStats = useMemo(() => {
    const critical = rows.filter((r) => r.risk === "critical").length;
    const watch = rows.filter((r) => r.risk === "watch").length;
    const slipping = rows.filter((r) => r.slipping).length;
    const overdue = rows.filter((r) => (r.overdue_tasks || 0) > 0).length;
    const stale = rows.filter((r) => (r.stale_days ?? 0) >= 3 || !r.last_synced_at).length;
    const offContract = rows.filter((r) => r.success_contract?.status === "behind").length;
    const reportReady =
      rows.filter((r) => r.report_ready).length ||
      rows.filter((r) => (r.open_tasks || 0) === 0 && wins.some((w) => w.client_id === r.client_id))
        .length;
    // no_data is not healthy — empty/unsynced books must not inflate the green count
    const healthy = rows.filter((r) => r.risk === "healthy").length;
    const noData = rows.filter((r) => r.risk === "no_data").length;
    const attributedLift = wins.reduce((s, w) => s + (w.avg_primary_change || 0), 0);
    const totalClicks = rows.reduce((s, r) => s + (r.metrics?.gsc_clicks || 0), 0);
    const totalRevenue = rows.reduce((s, r) => s + (r.metrics?.revenue || 0), 0);
    return {
      critical,
      watch,
      healthy,
      noData,
      slipping,
      overdue,
      stale,
      offContract,
      atRisk: critical + watch,
      reportReady,
      attributedLift,
      avgAttributedLift: wins.length ? attributedLift / wins.length : 0,
      revenue30: rows.reduce((s, r) => s + (r.metrics?.revenue || 0), 0),
      leads30: rows.reduce((s, r) => s + (r.metrics?.leads || 0), 0),
      totalClicks,
      totalRevenue,
    };
  }, [rows, wins]);

  const capacity = useMemo(() => {
    const openWork = rows.reduce((s, r) => s + (r.open_tasks || 0), 0);
    const overdueWork = rows.reduce((s, r) => s + (r.overdue_tasks || 0), 0);
    const byOwner = new Map<string, { open: number; overdue: number }>();
    for (const r of rows) {
      const owner = (r.owner || "Unassigned").trim() || "Unassigned";
      const cur = byOwner.get(owner) || { open: 0, overdue: 0 };
      cur.open += r.open_tasks || 0;
      cur.overdue += r.overdue_tasks || 0;
      byOwner.set(owner, cur);
    }
    const owners: CapacityOwner[] = [...byOwner.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .filter((o) => o.open > 0 || o.overdue > 0)
      .sort((a, b) => b.open - a.open || b.overdue - a.overdue)
      .slice(0, 6);
    return { openWork, overdueWork, owners };
  }, [rows]);

  const ownerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of rows) {
      if (r.owner?.trim()) set.add(r.owner.trim());
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [rows]);

  const searchFiltered = useMemo(() => {
    const q = tableSearch.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.industry || "").toLowerCase().includes(q) ||
        (r.owner || "").toLowerCase().includes(q)
    );
  }, [rows, tableSearch]);

  const filtered = useMemo(() => {
    return searchFiltered.filter((r) => {
      if (filter === "critical" && r.risk !== "critical") return false;
      if (filter === "watch" && r.risk !== "watch") return false;
      if (filter === "slipping" && !r.slipping) return false;
      if (filter === "overdue" && (r.overdue_tasks || 0) <= 0) return false;
      if (filter === "stale" && !((r.stale_days ?? 0) >= 3 || !r.last_synced_at)) return false;
      if (filter === "off_contract" && r.success_contract?.status !== "behind") return false;
      if (ownerFilter === "unassigned" && (r.owner || "").trim()) return false;
      if (ownerFilter !== "all" && ownerFilter !== "unassigned") {
        if ((r.owner || "").trim() !== ownerFilter) return false;
      }
      if (myBookName && ownerFilter === "all") {
        if ((r.owner || "").trim() !== myBookName) return false;
      }
      if (priorityOnly && (r.priority || 1) < 2) return false;
      if (reportReadyOnly && !r.report_ready) return false;
      return true;
    });
  }, [searchFiltered, filter, ownerFilter, myBookName, priorityOnly, reportReadyOnly]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    const order: Record<string, number> = {
      critical: 0,
      stabilizing: 1,
      watch: 1,
      healthy: 2,
      no_data: 3,
    };
    copy.sort((a, b) => {
      if (sortKey === "name") return a.name.localeCompare(b.name);
      if (sortKey === "clicks") return (b.metrics?.gsc_clicks || 0) - (a.metrics?.gsc_clicks || 0);
      if (sortKey === "health_score") return a.health_score - b.health_score;
      if (sortKey === "open_insights") return b.open_insights - a.open_insights;
      if (sortKey === "open_tasks") return b.open_tasks - a.open_tasks;
      if (sortKey === "slipping") {
        return Number(!!b.slipping) - Number(!!a.slipping) || a.health_score - b.health_score;
      }
      if (sortKey === "contract") {
        const ca = contractRank(a.success_contract?.status);
        const cb = contractRank(b.success_contract?.status);
        if (ca !== cb) return ca - cb;
        const pa = a.priority || 1;
        const pb = b.priority || 1;
        if (pb !== pa) return pb - pa;
        if (a.risk_rank != null && b.risk_rank != null) return a.risk_rank - b.risk_rank;
        return a.health_score - b.health_score;
      }
      if (a.risk_rank != null && b.risk_rank != null) return a.risk_rank - b.risk_rank;
      return (order[a.risk] ?? 0) - (order[b.risk] ?? 0) || a.health_score - b.health_score;
    });
    return copy;
  }, [filtered, sortKey]);

  const clearFilters = () => {
    setFilter("all");
    setOwnerFilter("all");
    setPriorityOnly(false);
    setReportReadyOnly(false);
    setMyBook("");
    setTableSearch("");
    setBulkMode(false);
    setBulkSelected(new Set());
  };

  const toggleBulkSelect = (clientId: number) => {
    setBulkSelected((prev) => {
      const next = new Set(prev);
      if (next.has(clientId)) next.delete(clientId);
      else next.add(clientId);
      return next;
    });
  };

  const toggleAllVisible = () => {
    const ids = sorted.map((r) => r.client_id);
    const allOn = ids.every((id) => bulkSelected.has(id));
    if (allOn) setBulkSelected(new Set());
    else setBulkSelected(new Set(ids));
  };

  const bulkSync = async () => {
    if (bulkSelected.size === 0) return;
    setBulkBusy(true);
    setSyncNote(null);
    let ok = 0;
    let failed = 0;
    for (const id of bulkSelected) {
      try {
        await api.metrics.sync(id);
        ok++;
      } catch {
        failed++;
      }
    }
    setSyncNote(
      `Synced ${ok} client${ok === 1 ? "" : "s"}${failed > 0 ? `, ${failed} failed` : ""}`
    );
    setBulkBusy(false);
    await fetchPortfolio();
    setBulkMode(false);
    setBulkSelected(new Set());
  };

  const bulkArchive = async () => {
    if (bulkSelected.size === 0) return;
    setBulkBusy(true);
    let ok = 0;
    for (const id of bulkSelected) {
      try {
        await api.clients.archive(id);
        ok++;
      } catch {
        /* skip */
      }
    }
    toastSuccess(`Archived ${ok} client${ok === 1 ? "" : "s"}`);
    setBulkBusy(false);
    await loadPortfolio();
    setBulkMode(false);
    setBulkSelected(new Set());
  };

  const bulkUnarchive = async () => {
    if (bulkSelected.size === 0) return;
    setBulkBusy(true);
    let ok = 0;
    for (const id of bulkSelected) {
      try {
        await api.clients.unarchive(id);
        ok++;
      } catch {
        /* skip */
      }
    }
    toastSuccess(`Restored ${ok} client${ok === 1 ? "" : "s"}`);
    setBulkBusy(false);
    await loadPortfolio();
    setBulkMode(false);
    setBulkSelected(new Set());
  };

  const hasActiveFilters =
    filter !== "all" ||
    ownerFilter !== "all" ||
    priorityOnly ||
    reportReadyOnly ||
    !!myBookName ||
    !!tableSearch;

  const exportCSV = () => {
    const headers = [
      "Client",
      "Industry",
      "Owner",
      "Risk",
      "Health",
      "Contract",
      "Open Issues",
      "Open Tasks",
      "Overdue",
      "Clicks 7d",
      "Sessions 7d",
      "Conversions 7d",
      "Leads 7d",
      "Revenue 7d",
      "Last Sync",
    ];
    const csvRows = sorted.map((r) =>
      [
        `"${r.name}"`,
        `"${r.industry || ""}"`,
        `"${r.owner || ""}"`,
        r.risk,
        r.health_score,
        r.success_contract?.status || "unset",
        r.open_insights,
        r.open_tasks,
        r.overdue_tasks || 0,
        r.metrics?.gsc_clicks || 0,
        r.metrics?.ga4_sessions || 0,
        r.metrics?.ga4_conversions || 0,
        r.metrics?.leads || 0,
        r.metrics?.revenue || 0,
        r.last_synced_at || "",
      ].join(",")
    );
    downloadCSV("kinexis-portfolio", headers, csvRows);
    toastSuccess("CSV exported");
  };

  const toggleBulkMode = () => {
    setBulkMode((v) => !v);
    setBulkSelected(new Set());
  };

  return {
    rows,
    wins,
    todayItems,
    aiValue,
    successBoard,
    loading,
    loadError,
    sortKey,
    setSortKey,
    filter,
    setFilter,
    ownerFilter,
    setOwnerFilter,
    priorityOnly,
    setPriorityOnly,
    reportReadyOnly,
    setReportReadyOnly,
    myBookName,
    setMyBook,
    assigneePresets,
    syncingAll,
    syncNote,
    tableSearch,
    setTableSearch,
    bulkMode,
    bulkSelected,
    bulkBusy,
    loadPortfolio,
    handleSyncAll,
    portfolioStats,
    capacity,
    ownerOptions,
    sorted,
    clearFilters,
    toggleBulkSelect,
    toggleAllVisible,
    bulkSync,
    bulkArchive,
    bulkUnarchive,
    hasActiveFilters,
    exportCSV,
    toggleBulkMode,
  };
}

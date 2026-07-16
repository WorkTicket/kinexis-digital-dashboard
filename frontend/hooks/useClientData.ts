"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, Client, Insight, Metric, Task, DataSource } from "@/lib/api";

const DEFAULT_ASSIGNEE = "Unassigned";
export const DEFAULT_METRIC_DAYS = 90;
export const DEFAULT_LIST_LIMIT = 200;

export const clientDataKeys = {
  bundle: (id: number) => ["clientData", id, "bundle"] as const,
  assignees: ["settings", "assignees"] as const,
};

type ClientBundle = {
  client: Client | null;
  metrics: Metric[];
  insights: Insight[];
  tasks: Task[];
  datasources: DataSource[];
};

async function fetchClientBundle(
  id: number,
  opts?: { syncFirst?: boolean; syncedRef?: Set<number> }
): Promise<ClientBundle> {
  if (opts?.syncFirst) {
    await api.metrics.sync(id).catch((e) => {
      console.warn("Initial sync failed", e);
    });
  }

  const results = await Promise.allSettled([
    api.clients.get(id),
    api.metrics.list({ client_id: id, days: DEFAULT_METRIC_DAYS, site_totals_only: true }),
    api.insights.list({ client_id: id, limit: DEFAULT_LIST_LIMIT, offset: 0 }),
    api.tasks.list({ client_id: id, limit: DEFAULT_LIST_LIMIT, offset: 0 }),
    api.clients.datasources.list(id),
  ]);

  let client: Client | null = results[0].status === "fulfilled" ? results[0].value : null;
  let metrics: Metric[] = results[1].status === "fulfilled" ? results[1].value : [];
  let insights: Insight[] = results[2].status === "fulfilled" ? results[2].value : [];
  let tasks: Task[] = results[3].status === "fulfilled" ? results[3].value : [];
  let datasources: DataSource[] = results[4].status === "fulfilled" ? results[4].value : [];

  if (metrics.length === 0 && !opts?.syncFirst && opts?.syncedRef && !opts.syncedRef.has(id)) {
    opts.syncedRef.add(id);
    await api.metrics.sync(id).catch((e) => {
      console.warn("Auto sync failed", e);
    });
    const [refreshed, refreshedInsights] = await Promise.all([
      api.metrics.list({
        client_id: id,
        days: DEFAULT_METRIC_DAYS,
        site_totals_only: true,
      }),
      api.insights.list({ client_id: id, limit: DEFAULT_LIST_LIMIT, offset: 0 }),
    ]);
    metrics = refreshed;
    insights = refreshedInsights;
  }

  const fails = results.filter((r) => r.status === "rejected");
  if (fails.length > 0) {
    console.error(
      "Some data failed to load:",
      fails.map((f: PromiseRejectedResult) => f.reason?.message || f.reason)
    );
  }

  return { client, metrics, insights, tasks, datasources };
}

export interface UseClientDataReturn {
  selectedClientId: number | null;
  client: Client | null;
  metrics: Metric[];
  insights: Insight[];
  tasks: Task[];
  datasources: DataSource[];
  loading: boolean;
  hasLoadedOnce: boolean;
  error: string | null;
  syncing: boolean;
  syncedRef: React.MutableRefObject<Set<number>>;
  lastSyncResults: Record<string, string> | null;
  assigneePresets: string[];
  loadClient: (id: number, options?: { syncFirst?: boolean }) => Promise<void>;
  syncClient: (id: number) => Promise<{
    results: Record<string, string>;
    sources: DataSource[];
    insightsCreated: number;
  }>;
  setSelectedClientId: Dispatch<SetStateAction<number | null>>;
  setClient: Dispatch<SetStateAction<Client | null>>;
  setMetrics: Dispatch<SetStateAction<Metric[]>>;
  setInsights: Dispatch<SetStateAction<Insight[]>>;
  setTasks: Dispatch<SetStateAction<Task[]>>;
  setDatasources: Dispatch<SetStateAction<DataSource[]>>;
  setHasLoadedOnce: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setLastSyncResults: Dispatch<SetStateAction<Record<string, string> | null>>;
  clearError: () => void;
}

function emptyBundle(): ClientBundle {
  return { client: null, metrics: [], insights: [], tasks: [], datasources: [] };
}

function patchBundle(prev: ClientBundle | undefined, patch: Partial<ClientBundle>): ClientBundle {
  return { ...(prev ?? emptyBundle()), ...patch };
}

export function useClientData(): UseClientDataReturn {
  const queryClient = useQueryClient();
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncResults, setLastSyncResults] = useState<Record<string, string> | null>(null);
  const [assigneePresets, setAssigneePresets] = useState<string[]>([DEFAULT_ASSIGNEE]);
  const syncedRef = useRef<Set<number>>(new Set());
  const syncFirstRef = useRef(false);
  const loadGenRef = useRef(0);

  const bundleQuery = useQuery({
    queryKey:
      selectedClientId != null ? clientDataKeys.bundle(selectedClientId) : ["clientData", "idle"],
    queryFn: async () => {
      const id = selectedClientId!;
      const syncFirst = syncFirstRef.current;
      syncFirstRef.current = false;
      try {
        return await fetchClientBundle(id, {
          syncFirst,
          syncedRef: syncedRef.current,
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load client");
        throw e;
      }
    },
    enabled: selectedClientId != null,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (bundleQuery.isSuccess) setHasLoadedOnce(true);
  }, [bundleQuery.isSuccess, bundleQuery.dataUpdatedAt]);

  useEffect(() => {
    if (bundleQuery.isError && bundleQuery.error) {
      setError(
        bundleQuery.error instanceof Error ? bundleQuery.error.message : "Failed to load client"
      );
    }
  }, [bundleQuery.isError, bundleQuery.error]);

  const bundle = bundleQuery.data ?? emptyBundle();

  const updateBundle = useCallback(
    (updater: (prev: ClientBundle) => ClientBundle) => {
      if (selectedClientId == null) return;
      queryClient.setQueryData<ClientBundle>(clientDataKeys.bundle(selectedClientId), (prev) =>
        updater(prev ?? emptyBundle())
      );
    },
    [queryClient, selectedClientId]
  );

  const setClient: Dispatch<SetStateAction<Client | null>> = useCallback(
    (action) => {
      updateBundle((prev) =>
        patchBundle(prev, {
          client: typeof action === "function" ? action(prev.client) : action,
        })
      );
    },
    [updateBundle]
  );

  const setMetrics: Dispatch<SetStateAction<Metric[]>> = useCallback(
    (action) => {
      updateBundle((prev) =>
        patchBundle(prev, {
          metrics: typeof action === "function" ? action(prev.metrics) : action,
        })
      );
    },
    [updateBundle]
  );

  const setInsights: Dispatch<SetStateAction<Insight[]>> = useCallback(
    (action) => {
      updateBundle((prev) =>
        patchBundle(prev, {
          insights: typeof action === "function" ? action(prev.insights) : action,
        })
      );
    },
    [updateBundle]
  );

  const setTasks: Dispatch<SetStateAction<Task[]>> = useCallback(
    (action) => {
      updateBundle((prev) =>
        patchBundle(prev, {
          tasks: typeof action === "function" ? action(prev.tasks) : action,
        })
      );
    },
    [updateBundle]
  );

  const setDatasources: Dispatch<SetStateAction<DataSource[]>> = useCallback(
    (action) => {
      updateBundle((prev) =>
        patchBundle(prev, {
          datasources: typeof action === "function" ? action(prev.datasources) : action,
        })
      );
    },
    [updateBundle]
  );

  const loadClient = useCallback(
    async (id: number, options?: { syncFirst?: boolean }) => {
      const gen = ++loadGenRef.current;
      setError(null);
      setSelectedClientId(id);
      syncFirstRef.current = Boolean(options?.syncFirst);
      await queryClient.fetchQuery({
        queryKey: clientDataKeys.bundle(id),
        queryFn: () =>
          fetchClientBundle(id, {
            syncFirst: options?.syncFirst,
            syncedRef: syncedRef.current,
          }),
        staleTime: 0,
      });
      if (gen === loadGenRef.current) setHasLoadedOnce(true);
    },
    [queryClient]
  );

  const syncClient = useCallback(
    async (id: number) => {
      setSyncing(true);
      setLastSyncResults(null);
      try {
        const result = await api.metrics.sync(id);
        setLastSyncResults(result.results || null);
        if (result.sources?.length) {
          queryClient.setQueryData<ClientBundle>(clientDataKeys.bundle(id), (prev) =>
            patchBundle(prev, { datasources: result.sources || [] })
          );
        }
        await loadClient(id);
        return {
          results: result.results || {},
          sources: result.sources || [],
          insightsCreated: result.insights_created || 0,
        };
      } catch (e) {
        setError(e instanceof Error ? e.message : "Sync failed");
        throw e;
      } finally {
        setSyncing(false);
      }
    },
    [loadClient, queryClient]
  );

  const clearError = useCallback(() => setError(null), []);

  useEffect(() => {
    void api.settings
      .get()
      .then((settings) => {
        const raw = settings.assignee_presets || DEFAULT_ASSIGNEE;
        setAssigneePresets(
          raw
            .split(",")
            .map((s: string) => s.trim())
            .filter(Boolean)
        );
      })
      .catch(() => {
        /* defaults */
      });
  }, []);

  return {
    selectedClientId,
    client: bundle.client,
    metrics: bundle.metrics,
    insights: bundle.insights,
    tasks: bundle.tasks,
    datasources: bundle.datasources,
    loading: bundleQuery.isFetching || syncing,
    hasLoadedOnce,
    error,
    syncing,
    syncedRef,
    lastSyncResults,
    assigneePresets,
    loadClient,
    syncClient,
    setSelectedClientId,
    setClient,
    setMetrics,
    setInsights,
    setTasks,
    setDatasources,
    setHasLoadedOnce,
    setError,
    setLastSyncResults,
    clearError,
  };
}

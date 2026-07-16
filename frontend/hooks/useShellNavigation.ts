"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ShellTab =
  "portfolio" | "detect" | "charts" | "prescribe" | "execute" | "prove" | "report" | "settings";

/** Focused Detect sections: situation → problems → funnel → explore */
export type DetectSegment = "health" | "levers" | "funnel" | "explore";
export type ExploreMode = "rankings" | "opportunities" | "inventory";
export type PrescribeSegment = "fixes" | "ai_plan" | "briefs";

type ShellNavState = {
  tab: ShellTab;
  detect: DetectSegment;
  prescribe: PrescribeSegment;
  explore: ExploreMode;
  clientId: number | null;
};

const SHELL_TABS = new Set<ShellTab>([
  "portfolio",
  "detect",
  "charts",
  "prescribe",
  "execute",
  "prove",
  "report",
  "settings",
]);

const PRESCRIBE_SEGMENTS = new Set<PrescribeSegment>(["fixes", "ai_plan", "briefs"]);
const EXPLORE_MODES = new Set<ExploreMode>(["rankings", "opportunities", "inventory"]);

function readQuery(): URLSearchParams {
  if (typeof window === "undefined") return new URLSearchParams();
  return new URLSearchParams(window.location.search);
}

function parseShellFromQuery(qs: URLSearchParams): ShellNavState {
  let tabRaw = (qs.get("tab") || "portfolio") as ShellTab;
  // Legacy: charts is no longer a primary stage — land on Detect
  if (tabRaw === "charts") tabRaw = "detect";
  const tab = SHELL_TABS.has(tabRaw) ? tabRaw : "portfolio";
  // Nested Detect segments collapsed — always treat as health overview
  const detect: DetectSegment = "health";
  const prescribeRaw = (qs.get("prescribe") || "fixes") as PrescribeSegment;
  const prescribe = PRESCRIBE_SEGMENTS.has(prescribeRaw) ? prescribeRaw : "fixes";
  const exploreRaw = (qs.get("explore") || qs.get("dig") || "rankings") as ExploreMode;
  const explore = EXPLORE_MODES.has(exploreRaw) ? exploreRaw : "rankings";
  const clientRaw = qs.get("client");
  const clientId = clientRaw && /^\d+$/.test(clientRaw) ? Number(clientRaw) : null;
  return { tab, detect, prescribe, explore, clientId };
}

function writeQuery(params: ShellNavState) {
  if (typeof window === "undefined") return;
  const qs = new URLSearchParams();
  // Never persist legacy charts as a primary tab
  const tab = params.tab === "charts" ? "detect" : params.tab;
  qs.set("tab", tab);
  if (params.clientId) qs.set("client", String(params.clientId));
  if (tab === "detect" && params.explore) qs.set("dig", params.explore);
  if (tab === "prescribe") qs.set("prescribe", params.prescribe);
  const next = `${window.location.pathname}?${qs.toString()}`;
  const cur = `${window.location.pathname}${window.location.search}`;
  if (next !== cur) {
    window.history.replaceState(null, "", next);
  }
}

/** Navigation helpers extracted from the app shell to keep page.tsx thinner. */
export function useShellNavigation(initial: ShellTab = "portfolio") {
  const boot = useRef(typeof window !== "undefined" ? parseShellFromQuery(readQuery()) : null);
  const [activeTab, setActiveTabState] = useState<ShellTab>(boot.current?.tab ?? initial);
  const [detectSegment, setDetectSegmentState] = useState<DetectSegment>(
    boot.current?.detect ?? "health"
  );
  const [exploreMode, setExploreModeState] = useState<ExploreMode>(
    boot.current?.explore ?? "rankings"
  );
  const [prescribeSegment, setPrescribeSegmentState] = useState<PrescribeSegment>(
    boot.current?.prescribe ?? "fixes"
  );
  const [urlClientId, setUrlClientId] = useState<number | null>(boot.current?.clientId ?? null);
  const skipWrite = useRef(false);
  const navRef = useRef<ShellNavState>({
    tab: boot.current?.tab ?? initial,
    detect: boot.current?.detect ?? "health",
    prescribe: boot.current?.prescribe ?? "fixes",
    explore: boot.current?.explore ?? "rankings",
    clientId: boot.current?.clientId ?? null,
  });

  const applyNav = useCallback((patch: Partial<ShellNavState>) => {
    const next: ShellNavState = { ...navRef.current, ...patch };
    navRef.current = next;
    if (patch.tab !== undefined) setActiveTabState(next.tab);
    if (patch.detect !== undefined) setDetectSegmentState(next.detect);
    if (patch.prescribe !== undefined) setPrescribeSegmentState(next.prescribe);
    if (patch.explore !== undefined) setExploreModeState(next.explore);
    if (patch.clientId !== undefined) setUrlClientId(next.clientId);
    if (!skipWrite.current) {
      writeQuery(next);
    }
  }, []);

  const setActiveTab = useCallback(
    (tab: ShellTab | ((prev: ShellTab) => ShellTab)) => {
      const next = typeof tab === "function" ? tab(navRef.current.tab) : tab;
      applyNav({ tab: next });
    },
    [applyNav]
  );

  const setDetectSegment = useCallback((s: DetectSegment) => applyNav({ detect: s }), [applyNav]);

  const setExploreMode = useCallback((m: ExploreMode) => applyNav({ explore: m }), [applyNav]);

  const setPrescribeSegment = useCallback(
    (s: PrescribeSegment) => applyNav({ prescribe: s }),
    [applyNav]
  );

  const setShellClientId = useCallback(
    (id: number | null) => {
      if (navRef.current.clientId === id) return;
      applyNav({ clientId: id });
    },
    [applyNav]
  );

  useEffect(() => {
    const onPop = () => {
      skipWrite.current = true;
      const parsed = parseShellFromQuery(readQuery());
      navRef.current = parsed;
      setActiveTabState(parsed.tab);
      setDetectSegmentState(parsed.detect);
      setPrescribeSegmentState(parsed.prescribe);
      setExploreModeState(parsed.explore);
      setUrlClientId(parsed.clientId);
      skipWrite.current = false;
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigateShell = useCallback(
    (tab: string) => {
      if (tab === "portfolio") {
        applyNav({ tab: "portfolio" });
        return;
      }
      if (tab === "settings") {
        applyNav({ tab: "settings" });
        return;
      }
      // Charts / explore / funnel / levers all land on Detect (Dig deeper handles panels)
      if (tab === "levers" || tab === "growth_levers") {
        applyNav({ tab: "detect", detect: "health", explore: "rankings" });
        return;
      }
      if (
        tab === "detect" ||
        tab === "dashboard" ||
        tab === "overview" ||
        tab === "health" ||
        tab === "situation"
      ) {
        applyNav({ tab: "detect", detect: "health" });
        return;
      }
      if (tab === "funnel" || tab === "diagnose") {
        applyNav({ tab: "detect", detect: "health" });
        return;
      }
      if (tab === "explore") {
        applyNav({ tab: "detect", detect: "health", explore: "rankings" });
        return;
      }
      if (tab === "opportunities") {
        applyNav({ tab: "detect", detect: "health", explore: "opportunities" });
        return;
      }
      if (tab === "rankings" || tab === "ranking" || tab === "serp") {
        applyNav({ tab: "detect", detect: "health", explore: "rankings" });
        return;
      }
      if (tab === "prescribe" || tab === "queue" || tab === "fixes") {
        applyNav({ tab: "prescribe", prescribe: "fixes" });
        return;
      }
      if (tab === "actions" || tab === "ai_plan" || tab === "playbook") {
        applyNav({ tab: "prescribe", prescribe: "ai_plan" });
        return;
      }
      if (tab === "briefs") {
        applyNav({ tab: "prescribe", prescribe: "briefs" });
        return;
      }
      if (tab === "execute" || tab === "tasks" || tab === "work") {
        applyNav({ tab: "execute" });
        return;
      }
      if (tab === "prove" || tab === "impact" || tab === "measure") {
        applyNav({ tab: "prove" });
        return;
      }
      if (tab === "report" || tab === "reports" || tab === "results") {
        applyNav({ tab: "report" });
        return;
      }
      // Legacy charts tab → Detect (Dig deeper opens charts in workspace)
      if (tab === "charts" || tab === "trends") {
        applyNav({ tab: "detect", detect: "health" });
        return;
      }
      if (SHELL_TABS.has(tab as ShellTab)) {
        applyNav({ tab: tab as ShellTab });
      }
    },
    [applyNav]
  );

  const scrollToFixes = useCallback(() => {
    applyNav({ tab: "prescribe", prescribe: "fixes" });
  }, [applyNav]);

  const copyDeepLink = useCallback(async () => {
    if (typeof window === "undefined") return false;
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      return true;
    } catch {
      return false;
    }
  }, []);

  return {
    activeTab,
    setActiveTab,
    detectSegment,
    setDetectSegment,
    exploreMode,
    setExploreMode,
    prescribeSegment,
    setPrescribeSegment,
    navigateShell,
    scrollToFixes,
    urlClientId,
    setShellClientId,
    copyDeepLink,
  };
}

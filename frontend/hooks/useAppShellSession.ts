"use client";

import {
  useState,
  useEffect,
  useCallback,
  useRef,
  type Dispatch,
  type SetStateAction,
} from "react";
import { api, Client, DataSource } from "@/lib/api";
import type { DetectSegment, ShellTab } from "@/hooks/useShellNavigation";

const THEME_STORAGE_KEY = "kinexis-theme";
const DEFAULT_THEME = "dark";

export type AppShellPhase = "loading" | "login" | "app";

export interface UseAppShellSessionOptions {
  urlClientId: number | null;
  selectedClientId: number | null;
  setSelectedClientId: Dispatch<SetStateAction<number | null>>;
  setClient: Dispatch<SetStateAction<Client | null>>;
  setHasLoadedOnce: Dispatch<SetStateAction<boolean>>;
  setDatasources: Dispatch<SetStateAction<DataSource[]>>;
  setActiveTab: (tab: ShellTab | ((prev: ShellTab) => ShellTab)) => void;
  setDetectSegment: (segment: DetectSegment) => void;
  setShellClientId: (id: number | null) => void;
  toastError: (message: string) => void;
}

/** Theme, auth/login phase, and client-list lifecycle for the app shell. */
export function useAppShellSession({
  urlClientId,
  selectedClientId,
  setSelectedClientId,
  setClient,
  setHasLoadedOnce,
  setDatasources,
  setActiveTab,
  setDetectSegment,
  setShellClientId,
  toastError,
}: UseAppShellSessionOptions) {
  const [phase, setPhase] = useState<AppShellPhase>("loading");
  const [theme, setTheme] = useState<"light" | "dark">(DEFAULT_THEME);
  const [clientList, setClientList] = useState<Client[]>([]);
  const autoSelectFirstClient = useRef(false);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "light" ? "dark" : "light";
      return next;
    });
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light") setTheme("light");
  }, []);

  useEffect(() => {
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;

    const resolvePhase = async (cloudflareConnected: boolean, onboardingComplete: boolean) => {
      if (cloudflareConnected) {
        if (!onboardingComplete) {
          await api.onboarding.complete().catch((e) => {
            console.warn("Failed to mark onboarding complete", e);
          });
        }
        setPhase("app");
      } else {
        setPhase("login");
      }
    };

    const checkStatus = async () => {
      for (let attempt = 0; attempt < 12; attempt++) {
        if (cancelled) return;
        try {
          const s = await api.onboarding.status();
          if (cancelled) return;
          await resolvePhase(s.cloudflare_connected, s.onboarding_complete);
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 500));
        }
      }
      if (!cancelled) setPhase("login");
    };

    checkStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleConnected = useCallback(async () => {
    await api.onboarding.complete().catch((e) => {
      console.warn("Failed to mark onboarding complete", e);
    });
    autoSelectFirstClient.current = true;
    setPhase("app");
  }, []);

  const handleSignOut = useCallback(async () => {
    try {
      await api.auth.signOut();
    } catch (e) {
      console.warn("Sign out failed", e);
    }
    setSelectedClientId(null);
    setClient(null);
    setHasLoadedOnce(false);
    setDatasources([]);
    setPhase("login");
  }, [setSelectedClientId, setClient, setHasLoadedOnce, setDatasources]);

  useEffect(() => {
    const unsubscribe = window.kinexis?.onSignOutComplete?.(() => {
      handleSignOut().catch((e) => {
        console.warn("Sign out from desktop bridge failed", e);
        toastError("Sign out failed");
      });
    });
    return () => {
      unsubscribe?.();
    };
  }, [handleSignOut, toastError]);

  const handleClientsLoaded = useCallback(
    (clients: Client[]) => {
      setClientList(clients);
      if (urlClientId && clients.some((c) => c.id === urlClientId)) {
        setSelectedClientId(urlClientId);
        return;
      }
      if (autoSelectFirstClient.current && clients.length > 0) {
        autoSelectFirstClient.current = false;
        const first = clients[0];
        if (!first) return;
        setSelectedClientId(first.id);
        setShellClientId(first.id);
        setActiveTab("detect");
        setDetectSegment("health");
      }
    },
    [setActiveTab, setDetectSegment, urlClientId, setShellClientId, setSelectedClientId]
  );

  useEffect(() => {
    if (urlClientId && !selectedClientId && clientList.some((c) => c.id === urlClientId)) {
      setSelectedClientId(urlClientId);
    }
  }, [urlClientId, selectedClientId, clientList, setSelectedClientId]);

  const handleClientRemoved = useCallback(
    (id: number) => {
      setClientList((prev) => prev.filter((c) => c.id !== id));
      if (selectedClientId === id) {
        setSelectedClientId(null);
        setClient(null);
        setActiveTab("portfolio");
      }
    },
    [selectedClientId, setActiveTab, setSelectedClientId, setClient]
  );

  return {
    phase,
    theme,
    toggleTheme,
    clientList,
    handleConnected,
    handleSignOut,
    handleClientsLoaded,
    handleClientRemoved,
  };
}

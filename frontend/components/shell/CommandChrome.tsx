"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { Search, Minus, Square, X, Copy, Sun, Moon, Cog } from "lucide-react";
import ClientSwitcher from "@/components/shell/ClientSwitcher";
import AccountsMenu from "@/components/shell/AccountsMenu";
import type { Client } from "@/lib/api";
import { WINDOWS_CLOSE_RED } from "@/lib/brandColors";

type Props = {
  selectedClientId: number | null;
  activeTab: string;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  onCommandPalette?: () => void;
  onSelectClient: (id: number) => void;
  onGoPortfolio: () => void;
  onGoSettings: () => void;
  onSignOut: () => void | Promise<void>;
  onClientsLoaded?: (clients: Client[]) => void;
  onClientRemoved?: (id: number) => void;
  requestAddClient?: number;
};

function isMac() {
  if (typeof navigator === "undefined") return false;
  const uaData = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData;
  if (uaData?.platform) return uaData.platform === "macOS";
  return /Mac/i.test(navigator.userAgent || "");
}

export default function CommandChrome({
  selectedClientId,
  activeTab,
  theme,
  onToggleTheme,
  onCommandPalette,
  onSelectClient,
  onGoPortfolio,
  onGoSettings,
  onSignOut,
  onClientsLoaded,
  onClientRemoved,
  requestAddClient = 0,
}: Props) {
  const [isElectron, setIsElectron] = useState(false);
  const [shortcut, setShortcut] = useState("Ctrl+K");
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    setIsElectron(Boolean(window.kinexis));
    setShortcut(isMac() ? "⌘K" : "Ctrl+K");
  }, []);

  useEffect(() => {
    if (!isElectron) return;
    const api = window.kinexis;
    void api?.windowIsMaximized?.().then((v) => setMaximized(Boolean(v)));
    return api?.onWindowMaximized?.((v) => setMaximized(Boolean(v)));
  }, [isElectron]);

  return (
    <header
      className="command-chrome titlebar-drag z-[60] flex shrink-0 select-none items-center gap-2 border-b border-[color:var(--border-subtle)] px-3 backdrop-blur-md sm:gap-3 sm:px-4"
      style={
        {
          height: "var(--titlebar-h)",
          WebkitAppRegion: "drag",
        } as CSSProperties
      }
      onDoubleClick={() => {
        if (isElectron) void window.kinexis?.windowMaximize?.();
      }}
    >
      <div className="titlebar-no-drag flex min-w-0 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={onGoPortfolio}
          className="mark motion-micro shrink-0 hover:opacity-90"
          aria-label="Mission Control"
        >
          <img
            src="/logo.svg"
            alt=""
            draggable={false}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </button>
        <span className="text-wordmark hidden text-[15px] leading-none lg:inline">Kinexis</span>
        <span className="hidden h-4 w-px bg-[color:var(--border-default)] sm:block" aria-hidden />
        <ClientSwitcher
          selectedClientId={selectedClientId}
          activeTab={activeTab}
          onSelectClient={onSelectClient}
          onGoPortfolio={onGoPortfolio}
          onClientsLoaded={onClientsLoaded}
          onClientRemoved={onClientRemoved}
          requestOpen={requestAddClient}
        />
      </div>

      <div className="flex min-w-0 flex-1 justify-center px-1">
        {onCommandPalette && (
          <button
            type="button"
            onClick={onCommandPalette}
            className="titlebar-no-drag text-muted motion-micro hidden w-full max-w-md items-center gap-2 border border-[color:var(--border-subtle)] bg-[color:var(--surface)] px-4 py-2 text-[13px] shadow-panel hover:border-[color:var(--border-default)] hover:text-ink-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kinexis-focus/30 sm:inline-flex"
            style={
              {
                WebkitAppRegion: "no-drag",
                borderRadius: "var(--radius-md)",
              } as CSSProperties
            }
          >
            <Search size={14} strokeWidth={1.75} className="shrink-0 opacity-50" />
            <span className="flex-1 truncate text-left">Jump to client, stage, or action…</span>
            <kbd className="kbd ml-auto">{shortcut}</kbd>
          </button>
        )}
      </div>

      <div className="titlebar-no-drag flex shrink-0 items-center gap-0.5">
        {onCommandPalette && (
          <button
            type="button"
            onClick={onCommandPalette}
            className="icon-btn sm:hidden"
            aria-label="Command palette"
          >
            <Search size={15} strokeWidth={1.5} />
          </button>
        )}
        <button
          type="button"
          onClick={onGoSettings}
          aria-label="Settings"
          aria-current={activeTab === "settings" ? "page" : undefined}
          className={`icon-btn ${activeTab === "settings" ? "text-kinexis-focus" : ""}`}
        >
          <Cog size={15} strokeWidth={1.5} />
        </button>
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className="icon-btn"
        >
          {theme === "dark" ? (
            <Sun size={15} strokeWidth={1.5} />
          ) : (
            <Moon size={15} strokeWidth={1.5} />
          )}
        </button>
        <AccountsMenu onSignOut={onSignOut} />
      </div>

      {isElectron && (
        <div
          className="titlebar-no-drag -mr-3 flex h-full shrink-0 items-stretch sm:-mr-4"
          style={{ WebkitAppRegion: "no-drag" } as CSSProperties}
        >
          <button
            type="button"
            aria-label="Minimize"
            className="text-muted motion-micro flex h-full w-[46px] items-center justify-center hover:bg-[color:var(--hover-fill)] hover:text-ink"
            onClick={() => void window.kinexis?.windowMinimize?.()}
          >
            <Minus size={14} strokeWidth={1.5} />
          </button>
          <button
            type="button"
            aria-label={maximized ? "Restore" : "Maximize"}
            className="text-muted motion-micro flex h-full w-[46px] items-center justify-center hover:bg-[color:var(--hover-fill)] hover:text-ink"
            onClick={() => void window.kinexis?.windowMaximize?.()}
          >
            {maximized ? (
              <Copy size={11} strokeWidth={1.5} className="rotate-180" />
            ) : (
              <Square size={11} strokeWidth={1.5} />
            )}
          </button>
          <button
            type="button"
            aria-label="Close"
            className="text-muted motion-micro flex h-full w-[46px] items-center justify-center hover:text-white"
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = WINDOWS_CLOSE_RED;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "";
            }}
            onClick={() => void window.kinexis?.windowClose?.()}
          >
            <X size={14} strokeWidth={1.5} />
          </button>
        </div>
      )}
    </header>
  );
}

"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { Search, Minus, Square, X, Copy, Sun, Moon } from "lucide-react";
import { WINDOWS_CLOSE_RED } from "@/lib/brandColors";

type Props = {
  title?: string;
  onCommandPalette?: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
};

function isMac() {
  if (typeof navigator === "undefined") return false;
  const uaData = (navigator as any).userAgentData;
  if (uaData?.platform) return uaData.platform === "macOS";
  return /Mac/i.test(navigator.userAgent || "");
}

export default function TitleBar({
  title = "Kinexis",
  onCommandPalette,
  theme,
  onToggleTheme,
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
      className="titlebar-drag z-[60] flex shrink-0 select-none items-center gap-3 border-b border-[color:var(--border-subtle)] bg-surface-light/90 px-4 backdrop-blur-sm"
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
      <div className="flex min-w-0 items-center gap-3">
        <div className="mark">
          <img
            src="/logo.svg"
            alt=""
            draggable={false}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
        <span className="text-wordmark truncate text-[16px] leading-none">
          {title === "Kinexis" ? "Kinexis" : title}
        </span>
        {title !== "Kinexis" && (
          <span className="text-muted hidden text-[12px] font-medium sm:inline">Kinexis</span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 justify-center px-2">
        {onCommandPalette && (
          <button
            type="button"
            onClick={onCommandPalette}
            className="titlebar-no-drag text-muted motion-micro hidden w-80 max-w-md items-center gap-2 border border-[color:var(--border-subtle)] bg-surface px-4 py-2 text-[13px] shadow-panel hover:border-[color:var(--border-default)] hover:bg-surface hover:text-ink-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kinexis-focus/30 sm:inline-flex"
            style={
              {
                WebkitAppRegion: "no-drag",
                borderRadius: "var(--radius-md)",
              } as CSSProperties
            }
          >
            <Search size={14} strokeWidth={1.75} className="shrink-0 opacity-50" />
            <span className="flex-1 truncate text-left">Search clients & actions…</span>
            <kbd className="kbd ml-auto">{shortcut}</kbd>
          </button>
        )}
      </div>

      <div className="titlebar-no-drag flex shrink-0 items-center">
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
      </div>

      {isElectron && (
        <div
          className="titlebar-no-drag -mr-4 flex h-full shrink-0 items-stretch"
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

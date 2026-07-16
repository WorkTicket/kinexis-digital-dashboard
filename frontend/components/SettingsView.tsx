"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Save,
  Zap,
  DatabaseBackup,
  Download,
  Check,
  Undo2,
  ShieldCheck,
  Wifi,
  Eye,
  Activity,
  AlertCircle,
  Trash2,
} from "lucide-react";
import { api, type AppSettings } from "@/lib/api";
import { useToast } from "@/components/Toast";
import ConfirmDialog from "@/components/ConfirmDialog";
import { ErrorState } from "@/components/ui/ErrorState";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

type Usage = {
  week_total_calls: number;
  week_estimated_cost_usd: number;
  by_client: {
    client_id: number | null;
    client_name: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost_usd: number;
  }[];
};

const IMPACT_WINDOWS = [
  { days: 7, label: "1 week", desc: "Fast feedback" },
  { days: 14, label: "2 weeks", desc: "Recommended" },
  { days: 28, label: "4 weeks", desc: "Longer measurement" },
] as const;

export default function SettingsView() {
  const { success, error: toastError } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [original, setOriginal] = useState<AppSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [backingUp, setBackingUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accentError, setAccentError] = useState<string>();
  const [ollamaUrlError, setOllamaUrlError] = useState<string>();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [updateResult, setUpdateResult] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [savedTimer, setSavedTimer] = useState<number | null>(null);

  const checkForUpdates = useCallback(async () => {
    setCheckingUpdate(true);
    setUpdateResult("Checking...");
    if (!window.kinexis?.checkForUpdates) {
      setUpdateResult("Update check unavailable in this install.");
      setCheckingUpdate(false);
      return;
    }
    try {
      const unsub = window.kinexis?.onUpdateStatus?.((data) => {
        if (data.status === "available") {
          setUpdateResult(`Downloading update v${data.version || ""}...`);
        } else if (data.status === "downloading" && data.percent !== undefined) {
          setUpdateResult(`Downloading... ${data.percent}%`);
        } else if (data.status === "downloaded") {
          setUpdateResult("Ready! Restart when prompted.");
          setCheckingUpdate(false);
          unsub?.();
        } else if (data.status === "up-to-date") {
          setUpdateResult("Already up to date.");
          setCheckingUpdate(false);
          unsub?.();
        } else if (data.status === "error") {
          setUpdateResult(data.message || "Update check failed.");
          setCheckingUpdate(false);
          unsub?.();
        }
      });
      const result = await window.kinexis?.checkForUpdates?.();
      if (!result?.ok && result?.error) {
        setUpdateResult(result.error);
        setCheckingUpdate(false);
        unsub?.();
      }
    } catch {
      setUpdateResult("Update check failed.");
      setCheckingUpdate(false);
    }
  }, []);

  const isDirty =
    settings && original ? JSON.stringify(settings) !== JSON.stringify(original) : false;

  const loadSettings = useCallback(() => {
    setError(null);
    api.settings
      .get()
      .then((s) => {
        setSettings(s);
        setOriginal(s);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load settings"));
    api.settings
      .aiUsage()
      .then(setUsage)
      .catch((e) => {
        console.warn("Failed to load AI usage", e);
        setUsage(null);
      });
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  useEffect(() => {
    return () => {
      if (savedTimer) clearTimeout(savedTimer);
    };
  }, [savedTimer]);

  const validateAccent = (hex: string) => {
    if (!hex) {
      setAccentError(undefined);
      return true;
    }
    if (!/^#[0-9A-Fa-f]{3,6}$/.test(hex)) {
      setAccentError("Must be a hex color like #0891B2");
      return false;
    }
    setAccentError(undefined);
    return true;
  };

  const validateOllamaUrl = (url: string) => {
    if (!url) {
      setOllamaUrlError(undefined);
      return true;
    }
    try {
      new URL(url);
      setOllamaUrlError(undefined);
      return true;
    } catch {
      setOllamaUrlError("Enter a valid URL (e.g. http://localhost:11434)");
      return false;
    }
  };

  const save = async () => {
    if (!settings) return;
    if (!validateAccent(settings.agency_accent || "")) return;
    if (settings.ai_provider === "ollama" && !validateOllamaUrl(settings.ollama_base_url || ""))
      return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await api.settings.update({
        ai_provider: settings.ai_provider,
        ollama_base_url: settings.ollama_base_url,
        ollama_model: settings.ollama_model,
        ollama_fallback_model: settings.ollama_fallback_model,
        pagespeed_api_key: settings.pagespeed_api_key,
        bing_api_key: settings.bing_api_key,
        clarity_api_token: settings.clarity_api_token,
        google_ads_developer_token: settings.google_ads_developer_token,
        assignee_presets: settings.assignee_presets,
        my_agent_name: settings.my_agent_name,
        impact_window_days: settings.impact_window_days,
        agency_name: settings.agency_name,
        agency_accent: settings.agency_accent,
        agency_logo_url: settings.agency_logo_url,
        portal_enabled: settings.portal_enabled,
        public_base_url: settings.public_base_url,
      });
      setSettings(updated);
      setOriginal(updated);
      setSaved(true);
      success("Settings saved");
      if (savedTimer) clearTimeout(savedTimer);
      const timer = window.setTimeout(() => setSaved(false), 3500);
      setSavedTimer(timer);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const discard = () => {
    if (original) {
      setSettings(original);
      setAccentError(undefined);
      setOllamaUrlError(undefined);
    }
  };

  const testAi = async () => {
    setTesting(true);
    try {
      const res = await api.settings.testAi();
      if (res.ok) success(res.message);
      else toastError(res.message);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "AI test failed");
    } finally {
      setTesting(false);
    }
  };

  const backupDb = async () => {
    setBackingUp(true);
    try {
      const res = await api.settings.backup();
      success(res.message || `Backup saved: ${res.filename}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Backup failed");
    } finally {
      setBackingUp(false);
    }
  };

  const resetAll = async () => {
    setResetting(true);
    try {
      const res = await api.settings.resetAll();
      success(res.message || "All data reset. Reloading...");
      setTimeout(() => window.location.reload(), 1500);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Reset failed");
    } finally {
      setResetting(false);
      setConfirmReset(false);
    }
  };

  const toggleKey = (key: string) => {
    setShowKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (!settings && !error) {
    return (
      <div className="flex flex-col items-center gap-3 py-16" role="status">
        <div
          className="h-5 w-5 animate-spin rounded-full border border-[color:var(--border-default)] border-t-kinexis-focus"
          aria-hidden
        />
        <p className="text-muted text-[12px] font-medium">Loading settings</p>
      </div>
    );
  }

  const accentColor =
    settings?.agency_accent?.startsWith("#") && settings.agency_accent.length >= 4
      ? settings.agency_accent
      : "#0891B2";

  return (
    <div className="animate-fade-up mx-auto max-w-2xl pb-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <p className="section-label text-muted mb-1 text-[11px] font-semibold tracking-wide">
            Workspace
          </p>
          <h1 className="text-display text-[24px] leading-tight sm:text-[28px]">Settings</h1>
          <p className="text-muted mt-1.5 text-[13px]">AI, keys, branding, team, and backup</p>
        </div>
        {isDirty && (
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={discard}>
              <Undo2 size={14} />
              Discard
            </Button>
            <Button onClick={save} disabled={saving} size="sm">
              <Save size={14} />
              {saving ? "Saving…" : saved ? "Saved" : "Save"}
            </Button>
          </div>
        )}
      </div>

      {error && settings && (
        <div className="mb-5 flex items-center gap-2 rounded-lg border border-kinexis-risk/20 bg-kinexis-risk/5 px-4 py-3 text-[13px] text-kinexis-risk">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {!settings && error ? (
        <ErrorState title="Couldn't load settings" description={error} onRetry={loadSettings} />
      ) : null}

      {settings && (
        <div className="space-y-5">
          {/* ── AI Provider ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div>
                  <h2 className="text-[15px] font-semibold text-ink">AI Provider</h2>
                  <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                    Choose Anthropic or a local Ollama model for plans, briefs, and narratives
                  </p>
                </div>
              </div>
              <Badge tone={settings.ai_ready ? "proof" : "signal"}>
                {settings.ai_ready ? "Ready" : "Not ready"}
              </Badge>
            </div>

            <div className="mb-4 grid grid-cols-2 gap-3">
              {(["anthropic", "ollama"] as const).map((provider) => {
                const active = settings.ai_provider === provider;
                return (
                  <button
                    key={provider}
                    type="button"
                    onClick={() => setSettings({ ...settings, ai_provider: provider })}
                    className={`rounded-xl border p-4 text-left transition-all duration-micro ${
                      active
                        ? "bg-[color:var(--kinexis-focus)]/[.06] border-kinexis-focus/30 ring-1 ring-inset ring-kinexis-focus/15"
                        : "border-[color:var(--border-subtle)] hover:border-[color:var(--border-default)]"
                    }`}
                  >
                    <div className="mb-1 flex items-center gap-2">
                      <span className="text-[14px] font-semibold capitalize text-ink">
                        {provider}
                      </span>
                      {active && (
                        <span className="text-kinexis-focus">
                          <Check size={14} strokeWidth={2.5} />
                        </span>
                      )}
                    </div>
                    <p className="text-muted text-[11px] leading-snug">
                      {provider === "anthropic"
                        ? "Claude via API key · cloud"
                        : "Local LLM · free, needs RAM"}
                    </p>
                  </button>
                );
              })}
            </div>

            {settings.ai_provider === "anthropic" && (
              <div className="flex items-center gap-2 rounded-lg bg-surface-lighter/60 px-3.5 py-2.5">
                {settings.anthropic_configured ? (
                  <ShieldCheck size={14} className="shrink-0 text-kinexis-proof" />
                ) : (
                  <AlertCircle size={14} className="shrink-0 text-kinexis-signal" />
                )}
                <span className="text-[12px] text-ink-secondary">
                  Anthropic key:{" "}
                  <span
                    className={
                      settings.anthropic_configured
                        ? "font-medium text-kinexis-proof"
                        : "font-medium text-kinexis-signal"
                    }
                  >
                    {settings.anthropic_configured
                      ? "configured"
                      : "missing — set ANTHROPIC_API_KEY"}
                  </span>
                </span>
              </div>
            )}

            {settings.ai_provider === "ollama" && (
              <div className="space-y-3 rounded-xl border border-[color:var(--border-subtle)] bg-surface-lighter/40 p-4">
                <Input
                  label="Ollama base URL"
                  value={settings.ollama_base_url}
                  onChange={(e) => {
                    setSettings({ ...settings, ollama_base_url: e.target.value });
                    if (ollamaUrlError) validateOllamaUrl(e.target.value);
                  }}
                  error={ollamaUrlError}
                  placeholder="http://localhost:11434"
                />
                <div className="grid grid-cols-2 gap-3">
                  <Input
                    label="Primary model"
                    value={settings.ollama_model}
                    onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
                    placeholder="kinexis-marketing-ft"
                  />
                  <Input
                    label="Fallback model"
                    value={settings.ollama_fallback_model || ""}
                    onChange={(e) =>
                      setSettings({ ...settings, ollama_fallback_model: e.target.value })
                    }
                    placeholder="kinexis-marketing"
                    hint="Used when primary is unavailable"
                  />
                </div>
              </div>
            )}

            <div className="mt-4">
              <Button variant="soft" size="sm" onClick={() => void testAi()} disabled={testing}>
                <Zap size={12} />
                {testing ? "Testing…" : "Test AI connection"}
              </Button>
            </div>
          </Panel>

          {/* ── AI Usage ── */}
          {usage && (
            <Panel padding="lg">
              <div className="mb-5 flex items-center gap-3">
                <div>
                  <h2 className="text-[15px] font-semibold text-ink">AI Usage · 7 days</h2>
                </div>
              </div>
              <div className="mb-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg bg-surface-lighter/60 p-3.5">
                  <p className="text-muted text-[11px] font-medium uppercase tracking-wider">
                    Calls
                  </p>
                  <p className="mt-1 text-2xl font-semibold tracking-tight text-ink">
                    {usage.week_total_calls}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-lighter/60 p-3.5">
                  <p className="text-muted text-[11px] font-medium uppercase tracking-wider">
                    Est. cost
                  </p>
                  <p className="mt-1 text-2xl font-semibold tracking-tight text-kinexis-focus">
                    ${usage.week_estimated_cost_usd.toFixed(2)}
                  </p>
                </div>
              </div>
              {usage.by_client.length > 0 && (
                <ul className="divide-y divide-[color:var(--border-subtle)] rounded-lg border border-[color:var(--border-subtle)]">
                  {usage.by_client.slice(0, 8).map((row) => (
                    <li
                      key={`${row.client_id ?? "x"}-${row.client_name}`}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13px]"
                    >
                      <span className="truncate text-ink-secondary">{row.client_name}</span>
                      <span className="text-muted shrink-0 font-mono text-[11px]">
                        {row.calls} calls · ${row.estimated_cost_usd.toFixed(2)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}

          {/* ── Connectors ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Connectors</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  API keys for third-party integrations
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {(
                [
                  {
                    key: "pagespeed_api_key",
                    configuredKey: "pagespeed_api_key_configured",
                    label: "PageSpeed Insights",
                    desc: "Core Web Vitals on sync",
                    icon: Activity,
                  },
                  {
                    key: "bing_api_key",
                    configuredKey: "bing_api_key_configured",
                    label: "Bing Webmaster",
                    desc: "Bing search performance",
                    icon: Wifi,
                  },
                  {
                    key: "clarity_api_token",
                    configuredKey: "clarity_api_token_configured",
                    label: "Microsoft Clarity",
                    desc: "Data Export token — page-level bounce / rage-click sync",
                    icon: Eye,
                  },
                  {
                    key: "google_ads_developer_token",
                    configuredKey: "google_ads_developer_token_configured",
                    label: "Google Ads API",
                    desc: "Developer token for ad metrics",
                    icon: Activity,
                  },
                ] as const
              ).map(({ key, configuredKey, label, desc, icon: Icon }) => {
                const configured = settings[configuredKey];
                const visible = showKeys[key] ?? false;
                return (
                  <div
                    key={key}
                    className="flex items-center gap-4 rounded-xl border border-[color:var(--border-subtle)] p-4 transition-colors hover:border-[color:var(--border-default)]"
                  >
                    <div
                      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                      style={{
                        background: configured
                          ? "color-mix(in srgb, var(--kinexis-proof) 8%, var(--surface-light))"
                          : "color-mix(in srgb, var(--surface) 30%, var(--surface-light))",
                      }}
                    >
                      {configured ? (
                        <ShieldCheck size={15} className="text-kinexis-proof" />
                      ) : (
                        <Icon size={15} className="text-muted" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-ink">{label}</p>
                      <p className="text-muted text-[11px]">{desc}</p>
                      {!visible ? (
                        <button
                          type="button"
                          onClick={() => toggleKey(key)}
                          className="mt-1.5 rounded-md bg-surface-lighter px-2.5 py-1 text-[11px] font-medium text-ink-secondary transition-colors hover:bg-surface-border/40"
                        >
                          {configured ? "•••••••• (saved)" : "Enter key…"}
                        </button>
                      ) : (
                        <div className="mt-2">
                          <Input
                            type="password"
                            showPasswordToggle
                            value={settings[key] || ""}
                            onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
                            autoComplete="off"
                            className="!py-2"
                            placeholder={`Paste ${label} key…`}
                          />
                        </div>
                      )}
                    </div>
                    <div className="shrink-0">
                      <Badge
                        tone={configured ? "proof" : "default"}
                        className={configured ? "" : "opacity-60"}
                      >
                        {configured ? "Active" : "Not set"}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>

          {/* ── Client portal ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Client portal</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Let clients open Pulse and report links from the internet. Agency API stays
                  token-protected; only share links are public.
                </p>
              </div>
            </div>
            <div className="space-y-3">
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={!!settings.portal_enabled}
                  onChange={(e) => setSettings({ ...settings, portal_enabled: e.target.checked })}
                />
                <span>
                  <span className="block text-[13px] font-medium text-ink">
                    Enable remote portal
                  </span>
                  <span className="text-muted text-[12px] leading-relaxed">
                    Binds the API for tunnels and allows remote hosts to open share links. Restart
                    the desktop app after saving.
                  </span>
                </span>
              </label>
              <Input
                label="Public base URL"
                value={settings.public_base_url || ""}
                onChange={(e) => setSettings({ ...settings, public_base_url: e.target.value })}
                placeholder="https://your-tunnel.example"
                hint="Cloudflare Tunnel or ngrok HTTPS URL pointing at this machine :8000 (no trailing slash)"
              />
              {settings.portal?.hint && (
                <p
                  className={`text-[12px] leading-relaxed ${
                    settings.portal.share_links_reachable
                      ? "text-kinexis-proof"
                      : "text-kinexis-signal"
                  }`}
                >
                  {settings.portal.hint}
                  {settings.portal.needs_restart ? " Restart required for bind/remote mode." : ""}
                </p>
              )}
              <div className="text-muted rounded-[var(--radius-md)] border border-[color:var(--border-subtle)] p-3 text-[12px] leading-relaxed">
                <p className="font-medium text-ink">Quick setup</p>
                <ol className="mt-1 list-decimal space-y-1 pl-4">
                  <li>
                    Run a tunnel, e.g.{" "}
                    <code className="text-ink">cloudflared tunnel --url http://127.0.0.1:8000</code>
                  </li>
                  <li>Paste the HTTPS URL above, enable portal, Save, restart Kinexis</li>
                  <li>Report → Client Pulse / Client report link → send to the client</li>
                </ol>
              </div>
            </div>
          </Panel>

          {/* ── White-label ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">White-label</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Shown on client report covers, PDFs, and Success Pulse
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <Input
                label="Agency name"
                value={settings.agency_name || ""}
                onChange={(e) => setSettings({ ...settings, agency_name: e.target.value })}
                placeholder="Kinexis"
                hint="Leave blank to show Kinexis"
              />
              <div className="grid grid-cols-[1fr_auto] items-start gap-3">
                <Input
                  label="Accent color"
                  value={settings.agency_accent || ""}
                  onChange={(e) => {
                    setSettings({ ...settings, agency_accent: e.target.value });
                    if (accentError) validateAccent(e.target.value);
                  }}
                  placeholder="#0891B2"
                  hint="Hex color for report branding"
                  error={accentError}
                />
                <div className="mt-[22px] flex items-center gap-2.5 rounded-lg bg-surface-lighter/60 px-3 py-2">
                  <span
                    className="h-8 w-8 shrink-0 rounded-md border border-[color:var(--border-default)] shadow-sm"
                    style={{ backgroundColor: accentColor }}
                    aria-label={`Report accent preview: ${accentColor}`}
                  />
                  <span className="text-muted-dim font-mono text-[11px]">{accentColor}</span>
                </div>
              </div>
              <Input
                label="Logo URL"
                value={settings.agency_logo_url || ""}
                onChange={(e) => setSettings({ ...settings, agency_logo_url: e.target.value })}
                placeholder="https://… or data:image/…"
                hint="Optional. Without a logo, a wordmark glyph is used"
              />
            </div>
          </Panel>

          {/* ── Team ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Team</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Work board assignees and impact measurement
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <Input
                label="My agent name"
                value={settings.my_agent_name || ""}
                onChange={(e) => setSettings({ ...settings, my_agent_name: e.target.value })}
                placeholder="Alex"
                hint="Defaults Portfolio “My book” and Work Board filters to this name on this workstation"
              />
              <Input
                label="Assignee presets"
                value={settings.assignee_presets || ""}
                onChange={(e) => setSettings({ ...settings, assignee_presets: e.target.value })}
                placeholder="Cursor, Alex, Jordan"
                hint="Comma-separated names for task assignment"
              />
              <div>
                <p className="text-label mb-3">Impact recheck window</p>
                <div className="grid grid-cols-3 gap-2">
                  {IMPACT_WINDOWS.map(({ days, label, desc }) => {
                    const active = (settings.impact_window_days ?? 14) === days;
                    return (
                      <button
                        key={days}
                        type="button"
                        onClick={() => setSettings({ ...settings, impact_window_days: days })}
                        className={`rounded-lg border p-3 text-center transition-all duration-micro ${
                          active
                            ? "bg-[color:var(--kinexis-focus)]/[.06] border-kinexis-focus/30 ring-1 ring-inset ring-kinexis-focus/15"
                            : "border-[color:var(--border-subtle)] hover:border-[color:var(--border-default)]"
                        }`}
                      >
                        <p className="text-[14px] font-semibold text-ink">{label}</p>
                        <p className="text-muted text-[11px]">{desc}</p>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </Panel>

          {/* ── Updates ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Check for Updates</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Download the latest version from GitHub
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button variant="soft" size="sm" onClick={checkForUpdates} disabled={checkingUpdate}>
                <Download size={13} />
                {checkingUpdate ? "Checking..." : "Check for updates"}
              </Button>
              {updateResult && <span className="text-muted text-[12px]">{updateResult}</span>}
            </div>
          </Panel>

          {/* ── Backup ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Database Backup</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Export to a timestamped file under Electron userData
                </p>
              </div>
            </div>

            {settings.database_path && (
              <p className="mb-3 break-all rounded-lg bg-surface-lighter/60 px-3.5 py-2.5 font-mono text-[11px] leading-relaxed text-ink-dim">
                {settings.database_path}
              </p>
            )}
            <Button variant="soft" size="sm" onClick={() => void backupDb()} disabled={backingUp}>
              <DatabaseBackup size={13} />
              {backingUp ? "Backing up..." : "Backup now"}
            </Button>
          </Panel>

          {/* ── Reset ── */}
          <Panel padding="lg">
            <div className="mb-5 flex items-center gap-3">
              <div>
                <h2 className="text-[15px] font-semibold text-ink">Reset all data</h2>
                <p className="text-muted mt-0.5 text-[12px] leading-relaxed">
                  Deletes all clients, metrics, insights, tasks, and reports. Returns to fresh
                  onboarding.
                </p>
              </div>
            </div>
            <Button
              variant="soft"
              size="sm"
              onClick={() => setConfirmReset(true)}
              disabled={resetting}
              className="!border-kinexis-risk/30 !text-kinexis-risk hover:!bg-kinexis-risk/10"
            >
              <Trash2 size={13} />
              Reset everything
            </Button>
          </Panel>

          <ConfirmDialog
            open={confirmReset}
            title="Reset all data?"
            description="This permanently deletes ALL clients, metrics, insights, tasks, reports, and settings. You will be signed out and returned to onboarding. This CANNOT be undone."
            confirmLabel={resetting ? "Resetting..." : "Delete everything"}
            danger
            busy={resetting}
            onConfirm={() => void resetAll()}
            onCancel={() => !resetting && setConfirmReset(false)}
          />
        </div>
      )}

      {/* Sticky save bar */}
      {settings && isDirty && (
        <div
          className="animate-fade-up fixed bottom-0 left-0 right-0 z-30 flex items-center justify-between px-6 py-3 lg:left-[var(--rail-w)] lg:px-8"
          style={{
            background: "color-mix(in srgb, var(--surface-elevated) 92%, transparent)",
            backdropFilter: "blur(12px)",
            borderTop: "1px solid var(--border-subtle)",
            boxShadow: "0 -4px 16px rgba(12,14,18,0.04)",
          }}
        >
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-kinexis-signal" aria-hidden />
            <span className="text-[13px] font-medium text-ink-secondary">Unsaved changes</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="soft" size="sm" onClick={discard}>
              <Undo2 size={14} />
              Discard
            </Button>
            <Button onClick={save} disabled={saving}>
              <Save size={14} />
              {saving ? "Saving…" : "Save settings"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

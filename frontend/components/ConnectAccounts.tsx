"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Cloud, Globe, Check, Loader2, Lock, ArrowRight, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { openSignInUrl } from "@/lib/signIn";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

type Props = {
  onReady: () => void;
};

async function pollUntilConnected(
  check: () => Promise<boolean>,
  onTick?: () => Promise<void>,
  isCancelled?: () => boolean
): Promise<boolean> {
  for (let i = 0; i < 90; i++) {
    if (isCancelled?.()) return false;
    if (i > 0) await new Promise((r) => setTimeout(r, 2000));
    if (onTick) await onTick();
    if (await check()) return true;
  }
  return false;
}

export default function ConnectAccounts({ onReady }: Props) {
  const [cfConnecting, setCfConnecting] = useState(false);
  const [googleConnecting, setGoogleConnecting] = useState(false);
  const [continuing, setContinuing] = useState(false);
  const [error, setError] = useState("");
  const [cfStatus, setCfStatus] = useState<{
    configured: boolean;
    connected: boolean;
    email: string;
    account_name: string;
    zone_count: number;
    client_count: number;
  } | null>(null);
  const [googleStatus, setGoogleStatus] = useState<{
    configured: boolean;
    connected: boolean;
    email: string;
    gsc_linked: number;
    ga4_linked: number;
  } | null>(null);

  const signInCancelledRef = useRef(false);

  const refreshCfStatus = useCallback(async () => {
    try {
      const status = await api.cloudflare.status();
      setCfStatus(status);
      return status;
    } catch {
      return null;
    }
  }, []);

  const refreshGoogleStatus = useCallback(async () => {
    try {
      const status = await api.google.status();
      setGoogleStatus(status);
      return status;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    refreshCfStatus();
    refreshGoogleStatus();
  }, [refreshCfStatus, refreshGoogleStatus]);

  const handleCloudflareSignIn = async () => {
    setCfConnecting(true);
    setError("");
    signInCancelledRef.current = false;
    try {
      const { auth_url } = await api.cloudflare.start();
      if (!auth_url) {
        throw new Error("Cloudflare did not return a sign-in URL.");
      }
      await openSignInUrl(auth_url);

      const connected = await pollUntilConnected(
        async () => (await refreshCfStatus())?.connected ?? false,
        async () => {
          await refreshGoogleStatus();
        },
        () => signInCancelledRef.current
      );

      if (signInCancelledRef.current) return;
      if (!connected) {
        setError("Cloudflare sign-in timed out. Complete sign-in in your browser and try again.");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start Cloudflare sign-in.");
    } finally {
      setCfConnecting(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setGoogleConnecting(true);
    setError("");
    signInCancelledRef.current = false;
    try {
      const { auth_url } = await api.google.start();
      if (!auth_url) {
        throw new Error(
          "Google did not return a sign-in URL. Check oauth.json / GOOGLE_CLIENT_ID."
        );
      }
      await openSignInUrl(auth_url);

      const connected = await pollUntilConnected(
        async () => (await refreshGoogleStatus())?.connected ?? false,
        async () => {
          await refreshCfStatus();
        },
        () => signInCancelledRef.current
      );

      if (signInCancelledRef.current) return;
      if (!connected) {
        setError("Google sign-in timed out. Complete sign-in in your browser and try again.");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start Google sign-in.");
    } finally {
      setGoogleConnecting(false);
    }
  };

  const cancelSignIn = () => {
    signInCancelledRef.current = true;
    setCfConnecting(false);
    setGoogleConnecting(false);
  };

  const handleContinue = async () => {
    if (!cfConnected || continuing) return;
    setContinuing(true);
    setError("");
    try {
      // Enter the app immediately — zone/GSC linking already happened in OAuth callbacks.
      // Metric pulls continue in the background so Continue isn't a 45s wait.
      await api.onboarding.complete().catch((e) => {
        console.warn("Failed to mark onboarding complete", e);
      });
      onReady();
      void api.cloudflare.resync().catch((e) => {
        console.warn("Background Cloudflare resync failed", e);
      });
      if (googleConnected) {
        void api.google.resync().catch((e) => {
          console.warn("Background Google resync failed", e);
        });
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not open the dashboard.");
      setContinuing(false);
    }
  };

  const cfConnected = cfStatus?.connected ?? false;
  const googleConnected = googleStatus?.connected ?? false;
  const googleAvailable = googleStatus?.configured ?? false;

  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden px-6 py-16 sm:py-24">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 70% 45% at 50% 0%, rgba(8,145,178,0.08), transparent 60%)",
        }}
        aria-hidden
      />
      <div className="animate-fade-up relative w-full max-w-[26rem]">
        <div className="mb-10 text-center">
          <div className="mark mx-auto mb-6 !h-11 !w-11">
            <img src="/logo.svg" alt="" />
          </div>
          <h1 className="text-display mb-3">Kinexis</h1>
          <p className="text-muted mx-auto max-w-xs text-[15px] leading-relaxed">
            Connect your stack to diagnose, fix, and prove client growth.
          </p>
        </div>

        <div className="space-y-3">
          <Panel
            padding="lg"
            elevated
            className={`motion-micro ${cfConnected ? "!border-kinexis-focus/30" : ""}`}
          >
            <div className="mb-1 flex items-center gap-3">
              <div
                className={`flex h-10 w-10 items-center justify-center border ${
                  cfConnected
                    ? "border-kinexis-focus/30 bg-kinexis-focus/10"
                    : "border-[color:var(--border-subtle)] bg-surface-lighter"
                }`}
                style={{ borderRadius: "var(--radius-md)" }}
              >
                {cfConnected ? (
                  <Check size={16} strokeWidth={2.25} className="text-kinexis-focus" />
                ) : (
                  <span className="relative inline-flex">
                    <Cloud size={16} strokeWidth={1.75} className="text-ink-secondary" />
                    <span
                      className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-sm bg-[#F6821F]"
                      aria-hidden
                    />
                  </span>
                )}
              </div>
              <div className="min-w-0">
                <h3 className="text-[14px] font-semibold text-ink">Cloudflare</h3>
                <p className="text-muted text-[13px]">Domain discovery &amp; analytics</p>
              </div>
              <Badge tone="brand" className="ml-auto shrink-0">
                Required
              </Badge>
            </div>

            {cfConnected ? (
              <div
                className="mt-4 border border-kinexis-focus/20 bg-kinexis-focus/[0.04] p-3.5"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <p className="text-[13px] font-medium text-ink">
                  {cfStatus?.account_name || cfStatus?.email || "Cloudflare account"} —{" "}
                  {cfStatus?.zone_count ?? 0} zone{(cfStatus?.zone_count ?? 0) !== 1 ? "s" : ""}{" "}
                  imported
                </p>
                <p className="text-muted mt-1 text-xs leading-relaxed">
                  {cfStatus?.client_count ?? 0} client
                  {(cfStatus?.client_count ?? 0) !== 1 ? "s" : ""} ready with analytics
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <p className="text-muted text-xs leading-relaxed">
                  Sign in with your Cloudflare account. Zones and analytics are set up
                  automatically.
                </p>
                <Button
                  type="button"
                  onClick={handleCloudflareSignIn}
                  disabled={cfConnecting}
                  className="w-full !py-2.5"
                >
                  {cfConnecting ? (
                    <>
                      <Loader2 size={14} className="animate-spin" /> Complete sign-in in your
                      browser…
                    </>
                  ) : (
                    <>
                      <Cloud size={14} />
                      Sign in with Cloudflare
                    </>
                  )}
                </Button>
                {cfConnecting && (
                  <Button type="button" variant="ghost" onClick={cancelSignIn} className="w-full">
                    Cancel
                  </Button>
                )}
              </div>
            )}
          </Panel>

          <Panel
            padding="lg"
            elevated
            className={`motion-micro ${googleConnected ? "!border-kinexis-focus/30" : ""}`}
          >
            <div className="mb-1 flex items-center gap-3">
              <div
                className={`flex h-10 w-10 items-center justify-center border ${
                  googleConnected
                    ? "border-kinexis-focus/30 bg-kinexis-focus/10"
                    : "border-[color:var(--border-subtle)] bg-surface-lighter"
                }`}
                style={{ borderRadius: "var(--radius-md)" }}
              >
                {googleConnected ? (
                  <Check size={16} strokeWidth={2.25} className="text-kinexis-focus" />
                ) : (
                  <Globe size={16} strokeWidth={1.75} className="text-muted" />
                )}
              </div>
              <div className="min-w-0">
                <h3 className="text-[14px] font-semibold text-ink">
                  Google Search &amp; Analytics
                </h3>
                <p className="text-muted text-[13px]">Optional — GSC &amp; GA4</p>
              </div>
              <Badge tone="default" className="ml-auto shrink-0">
                Optional
              </Badge>
            </div>

            {googleConnected ? (
              <div
                className="mt-4 border border-kinexis-focus/20 bg-kinexis-focus/[0.04] p-3.5"
                style={{ borderRadius: "var(--radius-md)" }}
              >
                <p className="text-[13px] font-medium text-ink">
                  {googleStatus?.email || "Google account connected"}
                </p>
                <p className="text-muted mt-1 text-xs leading-relaxed">
                  {googleStatus?.gsc_linked ?? 0} Search Console site
                  {(googleStatus?.gsc_linked ?? 0) !== 1 ? "s" : ""} and{" "}
                  {googleStatus?.ga4_linked ?? 0} Analytics propert
                  {(googleStatus?.ga4_linked ?? 0) !== 1 ? "ies" : "y"} linked
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <p className="text-muted text-xs leading-relaxed">
                  Add Google later for clicks, impressions, and sessions — or skip and use
                  Cloudflare now.
                </p>
                {!googleAvailable && googleStatus !== null && (
                  <p className="text-muted text-xs italic">
                    Google sign-in is unavailable in this install. Cloudflare-only mode is active.
                  </p>
                )}
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleGoogleSignIn}
                  disabled={googleConnecting || !googleAvailable}
                  className="w-full !py-2.5"
                >
                  {googleConnecting ? (
                    <>
                      <Loader2 size={14} className="animate-spin" /> Complete sign-in in your
                      browser…
                    </>
                  ) : (
                    <>
                      <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" aria-hidden="true">
                        <path
                          fill="#4285F4"
                          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                        />
                        <path
                          fill="#34A853"
                          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        />
                        <path
                          fill="#FBBC05"
                          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                        />
                        <path
                          fill="#EA4335"
                          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                        />
                      </svg>
                      Sign in with Google
                    </>
                  )}
                </Button>
                {googleConnecting && (
                  <Button type="button" variant="ghost" onClick={cancelSignIn} className="w-full">
                    Cancel
                  </Button>
                )}
              </div>
            )}
          </Panel>
        </div>

        {error && (
          <div
            className="mt-4 flex items-start gap-2 border border-kinexis-risk/25 px-3.5 py-2.5 text-[13px] text-kinexis-risk"
            style={{ borderRadius: "var(--radius-md)" }}
          >
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        <div className="mb-6 mt-5 flex items-start gap-2.5">
          <Lock size={14} strokeWidth={1.75} className="mt-0.5 shrink-0 text-ink-dim" />
          <p className="text-muted text-[13px] leading-relaxed">
            Everything runs locally on this computer. Credentials stay encrypted on your machine.
          </p>
        </div>

        {cfConnected && (
          <Button
            type="button"
            onClick={handleContinue}
            disabled={continuing}
            className="w-full !py-3"
          >
            {continuing ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Opening workspace…
              </>
            ) : (
              <>
                Enter workspace <ArrowRight size={15} />
              </>
            )}
          </Button>
        )}

        {!cfConnected && (
          <p className="text-muted text-center text-[13px]">Sign in with Cloudflare to continue</p>
        )}
      </div>
    </div>
  );
}

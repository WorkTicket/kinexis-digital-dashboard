"use client";

import { useEffect, useState } from "react";
import { api, SuccessContractPayload } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Stat } from "@/components/ui/Stat";
import { ErrorState } from "@/components/ui/ErrorState";
import { useToast } from "@/components/Toast";
import { motion } from "@/lib/motion";

type Props = {
  clientId: number;
};

function statusTone(status?: string): "proof" | "danger" | "warning" | "default" {
  if (status === "ahead" || status === "on_track") return "proof";
  if (status === "behind") return "danger";
  if (status === "insufficient_data" || status === "no_data") return "warning";
  return "default";
}

function progressFillClass(status?: string): string {
  if (status === "behind") return "bg-kinexis-risk";
  if (status === "insufficient_data" || status === "no_data") return "bg-kinexis-mist";
  if (status === "ahead" || status === "on_track") return "bg-kinexis-proof";
  return "bg-kinexis-mist";
}

function statusLabel(status?: string): string {
  return (status || "unset").replace(/_/g, " ");
}

export default function SuccessContractCard({ clientId }: Props) {
  const { error: toastError } = useToast();
  const [data, setData] = useState<SuccessContractPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoadError(null);
    api.actions
      .getContract(clientId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "Failed to load success contract";
        setData(null);
        setLoadError(msg);
        toastError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, reloadKey, toastError]);

  if (loadError) {
    return (
      <div className="mb-6">
        <ErrorState
          title="Success contract unavailable"
          description={loadError}
          onRetry={() => setReloadKey((k) => k + 1)}
          className="!py-6"
        />
      </div>
    );
  }

  if (!data) return null;

  const progress = data.progress;
  const brand = data.brand_split;
  const showContract = data.configured && progress;
  const showBrand =
    brand?.current && (brand.current.brand_clicks > 0 || brand.current.non_brand_clicks > 0);
  const insufficient = data.status === "insufficient_data";

  if (!showContract && !showBrand) return null;

  return (
    <div className="animate-fade-up mb-6 space-y-3">
      {showContract && progress && (
        <Panel className={motion.settle}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="section-label">Success contract</p>
              <p className="mt-1.5 text-[13px] font-medium text-ink">
                {progress.label} · target +{progress.target_delta_pct}% / {progress.window_days}d
              </p>
              <p className="text-muted font-mono-data mt-1 text-xs">
                {(progress.current ?? 0).toLocaleString()} now vs{" "}
                {(progress.compare_base ?? 0).toLocaleString()}{" "}
                {progress.change_pct != null
                  ? ` (${progress.change_pct > 0 ? "+" : ""}${progress.change_pct}%)`
                  : ""}
              </p>
              {insufficient && (
                <p className="mt-1.5 text-xs leading-relaxed text-kinexis-signal">
                  Not enough sample yet to call ahead or behind — treat the change as directional
                  only.
                </p>
              )}
            </div>
            <Badge tone={statusTone(data.status)} className="capitalize">
              {statusLabel(data.status)}
            </Badge>
          </div>
          {progress.progress_ratio != null && (
            <div className="progress-track mt-3.5">
              <div
                className={`progress-fill ${progressFillClass(data.status)}`}
                style={{ width: `${Math.min(100, progress.progress_ratio * 100)}%` }}
              />
            </div>
          )}
        </Panel>
      )}

      {showBrand && brand && (
        <div className="metric-grid grid-cols-2">
          <Stat
            label="Non-brand clicks"
            value={(brand.current?.non_brand_clicks ?? 0).toLocaleString()}
            hint={
              brand.change_pct?.non_brand_clicks != null
                ? `${brand.change_pct.non_brand_clicks > 0 ? "+" : ""}${brand.change_pct.non_brand_clicks}% vs prior`
                : undefined
            }
            tone={
              brand.change_pct?.non_brand_clicks == null
                ? "default"
                : brand.change_pct.non_brand_clicks >= 0
                  ? "success"
                  : "danger"
            }
          />
          <Stat
            label="Brand clicks"
            value={(brand.current?.brand_clicks ?? 0).toLocaleString()}
            hint={
              brand.change_pct?.brand_clicks != null
                ? `${brand.change_pct.brand_clicks > 0 ? "+" : ""}${brand.change_pct.brand_clicks}% vs prior`
                : undefined
            }
            tone={
              brand.change_pct?.brand_clicks == null
                ? "default"
                : brand.change_pct.brand_clicks >= 0
                  ? "success"
                  : "danger"
            }
          />
        </div>
      )}
    </div>
  );
}

"use client";

import { ArrowRight, Check } from "lucide-react";
import { GrowthLever } from "@/lib/api";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import GrowthLeverGauge from "@/components/GrowthLeverGauge";

const STEPS = [
  { id: "detected", label: "Detect", color: "bg-kinexis-signal" },
  { id: "prescribed", label: "Prescribe", color: "bg-kinexis-focus" },
  { id: "in_progress", label: "Execute", color: "bg-kinexis-momentum" },
  { id: "proving", label: "Prove", color: "bg-kinexis-proof" },
  { id: "proven", label: "Report", color: "bg-kinexis-mist" },
] as const;

const statusTone: Record<string, "signal" | "brand" | "momentum" | "proof" | "default"> = {
  detected: "signal",
  prescribed: "brand",
  in_progress: "momentum",
  proving: "proof",
  proven: "proof",
};

function stepIndex(status: string): number {
  if (status === "dismissed") return -1;
  const i = STEPS.findIndex((s) => s.id === status);
  return i >= 0 ? i : 0;
}

type Props = {
  lever: GrowthLever;
  busy?: boolean;
  onAction: (lever: GrowthLever, action: string) => void;
};

export default function LeverThreadCard({ lever, busy, onAction }: Props) {
  const idx = stepIndex(lever.status);

  // Detect dig-deeper is diagnosis-only: route into Fix queue. Assign lives on Prescribe.
  const cta =
    lever.status === "detected" || lever.status === "prescribed"
      ? { label: "Open Fix queue", action: "open_fix_queue" }
      : lever.status === "in_progress"
        ? { label: "Open Work queue", action: "complete" }
        : lever.status === "proving"
          ? { label: "View impact", action: "prove" }
          : lever.status === "proven"
            ? {
                label: lever.include_in_report ? "In this week’s report" : "Add to report",
                action: "report",
              }
            : null;

  return (
    <Panel
      className="motion-micro overflow-hidden hover:border-[color:var(--border-strong)]"
      padding={false}
    >
      <div className="px-4 pb-3 pt-4">
        <div className="flex items-start gap-3.5">
          <GrowthLeverGauge
            score={lever.impact_score}
            confidence={lever.confidence_label}
            size={52}
            className="mt-0.5"
          />
          <div className="min-w-0 flex-1">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <Badge tone={statusTone[lever.status] || "default"}>
                {lever.status.replace(/_/g, " ")}
              </Badge>
              {lever.stage && (
                <span className="text-muted font-mono-data text-[12px] font-medium">
                  {lever.stage.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <p className="text-[14px] font-semibold leading-snug text-ink">{lever.title}</p>
            {lever.cause && (
              <p className="text-muted mt-1.5 line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed">
                <span className="font-medium text-ink-secondary">What this means: </span>
                {lever.cause}
              </p>
            )}
            {lever.fix && (
              <p className="mt-1.5 line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-ink-secondary">
                <span className="font-medium text-kinexis-focus">How to fix: </span>
                {lever.fix.replace(/^What this means:[\s\S]*?How to fix:\n?/i, "")}
              </p>
            )}
            {lever.impact_summary && (
              <p className="mt-1.5 text-xs leading-relaxed text-kinexis-proof">
                {lever.impact_summary}
              </p>
            )}
            {lever.confidence_label && (
              <p className="text-muted mt-1 text-[11px]">{lever.confidence_label}</p>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-1">
          {STEPS.map((step, i) => {
            const done = idx > i || lever.status === "proven";
            const current = idx === i;
            return (
              <div key={step.id} className="min-w-0 flex-1">
                <div
                  className={`h-0.5 ${
                    done || current ? step.color : "bg-[color:var(--border-default)]"
                  } ${current ? "opacity-100" : done ? "opacity-55" : "opacity-30"}`}
                />
                <p
                  className={`mt-1.5 truncate text-xs tracking-wide ${
                    current ? "font-medium text-ink" : "text-muted"
                  }`}
                >
                  {step.label}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-[color:var(--border-subtle)] bg-surface px-4 py-2.5">
        {cta && (
          <Button
            variant="soft"
            size="sm"
            disabled={busy || (lever.status === "proven" && lever.include_in_report)}
            onClick={() => onAction(lever, cta.action)}
          >
            {lever.status === "proven" && lever.include_in_report ? (
              <Check size={12} />
            ) : (
              <ArrowRight size={12} />
            )}
            {cta.label}
          </Button>
        )}
        {lever.status !== "dismissed" && lever.status !== "proven" && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => onAction(lever, "dismiss")}
          >
            Dismiss
          </Button>
        )}
      </div>
    </Panel>
  );
}

"use client";

import type { CSSProperties } from "react";
import { chartRingTrack } from "@/lib/chartTheme";

export type LeverGaugeTone = "signal" | "focus" | "proof" | "momentum";

type Props = {
  /** 0–100 impact / priority score */
  score?: number | null;
  /** Maps to role color when score is absent */
  confidence?: "low" | "medium" | "high" | string | null;
  size?: number;
  className?: string;
  /** Accessible label */
  label?: string;
};

const TONE_CSS: Record<LeverGaugeTone, string> = {
  signal: "var(--kinexis-signal)",
  focus: "var(--kinexis-focus)",
  proof: "var(--kinexis-proof)",
  momentum: "var(--kinexis-momentum)",
};

export function resolveLeverTone(
  score: number | null | undefined,
  confidence?: string | null
): LeverGaugeTone {
  if (confidence) {
    const c = confidence.toLowerCase();
    if (c.includes("high") || c.includes("strong")) return "proof";
    if (c.includes("low") || c.includes("weak")) return "signal";
    if (c.includes("med")) return "focus";
  }
  if (score == null) return "focus";
  if (score >= 70) return "proof";
  if (score >= 40) return "focus";
  return "signal";
}

/**
 * Signature Growth Lever gauge — flat progress ring in the same family as
 * ClientHealth / PageSpeed, with the display score as the signature moment.
 */
export default function GrowthLeverGauge({
  score,
  confidence,
  size = 88,
  className = "",
  label = "Growth lever strength",
}: Props) {
  const hasScore = score != null && Number.isFinite(score);
  const value = hasScore ? Math.max(0, Math.min(100, score as number)) : 0;
  const tone = resolveLeverTone(score, confidence);
  const color = TONE_CSS[tone];

  const vb = 120;
  const cx = vb / 2;
  const cy = vb / 2;
  const stroke = size >= 104 ? 9 : size >= 80 ? 8 : size >= 56 ? 7 : 6;
  const r = (vb - stroke) / 2 - 2;
  const circumference = 2 * Math.PI * r;
  const filled = (value / 100) * circumference;
  const offset = circumference - filled;

  const display = hasScore ? Math.round(value) : "—";
  const showCaption = size >= 64;
  const scoreSize = size >= 104 ? 30 : size >= 88 ? 26 : size >= 72 ? 22 : size >= 56 ? 15 : 12;

  return (
    <div
      className={`relative shrink-0 ${className}`.trim()}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label}: ${display}${hasScore ? " of 100" : ""}`}
    >
      <svg
        viewBox={`0 0 ${vb} ${vb}`}
        width={size}
        height={size}
        className="block -rotate-90"
        aria-hidden
      >
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={chartRingTrack} strokeWidth={stroke} />
        {hasScore && (
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="butt"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="animate-lever-arc motion-gauge"
            style={
              {
                "--lever-arc-len": circumference,
                "--lever-arc-offset": offset,
              } as CSSProperties
            }
          />
        )}
      </svg>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-display font-normal tabular-nums leading-none tracking-[-0.02em]"
          style={{
            fontSize: scoreSize,
            color: hasScore ? color : "var(--muted)",
          }}
        >
          {display}
        </span>
        {showCaption && (
          <span className="font-mono-data text-muted mt-1.5 text-[11px] font-medium">impact</span>
        )}
      </div>
    </div>
  );
}

/** Split “1) … 2) …” / “1. …” prescriptions into readable steps. */
export function parseLeverFixSteps(fix: string): string[] {
  const trimmed = fix.trim();
  if (!trimmed) return [];
  const parts = trimmed
    .split(/(?:^|\s)(?:\d{1,2}[\)\.])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (parts.length >= 2) return parts;
  return [trimmed];
}

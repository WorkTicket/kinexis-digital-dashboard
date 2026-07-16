"use client";

import { CHART } from "@/lib/chartTheme";

type PayloadItem = {
  name?: string;
  value?: number | string;
  color?: string;
  dataKey?: string | number;
};

type Props = {
  active?: boolean;
  payload?: PayloadItem[];
  label?: string | number;
  valueFormatter?: (value: number | string, name?: string) => string;
};

/**
 * Shared chart tooltip — matches panel surface tokens, not browser default.
 */
export function KinexisChartTooltip({ active, payload, label, valueFormatter }: Props) {
  if (!active || !payload?.length) return null;

  return (
    <div
      className="rounded-lg border border-[color:var(--border-default)] px-3 py-2 text-xs shadow-dropdown"
      style={{
        background: "var(--surface-elevated)",
        fontFamily: CHART.monoFamily,
      }}
    >
      {label != null && label !== "" && (
        <p className="text-muted mb-1.5 font-ui text-[12px] font-medium">{label}</p>
      )}
      <ul className="space-y-1">
        {payload.map((entry, i) => {
          const raw = entry.value ?? "";
          const formatted =
            valueFormatter && (typeof raw === "number" || typeof raw === "string")
              ? valueFormatter(raw, entry.name)
              : String(raw);
          return (
            <li key={i} className="flex items-center gap-2 text-ink">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: entry.color || CHART.focus }}
              />
              <span className="text-muted font-ui">{entry.name ?? entry.dataKey}</span>
              <span className="font-mono-data ml-auto tabular-nums">{formatted}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

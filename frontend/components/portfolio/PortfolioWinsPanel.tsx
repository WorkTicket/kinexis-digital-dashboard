"use client";

import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import type { AiValueRow, PortfolioWin } from "@/hooks/usePortfolioData";

export type WinsOpenHint = {
  tab?: string;
  task_id?: number;
};

type Props = {
  wins: PortfolioWin[];
  aiValue: AiValueRow[];
  leads30: number;
  revenue30: number;
  onOpenClient: (clientId: number, hint?: WinsOpenHint) => void;
};

export function PortfolioWinsPanel({ wins, aiValue, leads30, revenue30, onOpenClient }: Props) {
  return (
    <CollapsibleSection label="Wins & AI value" className="mt-6">
      {(leads30 > 0 || revenue30 > 0 || wins.length > 0) && (
        <div className="text-muted mb-3 flex flex-wrap gap-4 text-xs">
          {leads30 > 0 && (
            <span>
              Portfolio leads (7d):{" "}
              <span className="font-mono-data text-ink-secondary">{leads30.toLocaleString()}</span>
            </span>
          )}
          {revenue30 > 0 && (
            <span>
              Closed revenue (7d):{" "}
              <span className="font-mono-data text-kinexis-focus">
                ${revenue30.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
            </span>
          )}
          <span>
            Wins (30d): <span className="font-mono-data text-ink-secondary">{wins.length}</span>
          </span>
        </div>
      )}

      {wins.length > 0 && (
        <div className="panel p-4">
          <p className="section-label mb-2">Recent attributed wins</p>
          <ul className="space-y-1.5">
            {wins.slice(0, 5).map((w) => (
              <li key={`${w.client_id}-${w.task_id ?? w.label}`}>
                <button
                  type="button"
                  className="motion-micro flex w-full gap-2 text-left text-[13px] text-ink-secondary hover:text-ink"
                  onClick={() => onOpenClient(w.client_id, { tab: "prove", task_id: w.task_id })}
                >
                  <span className="font-mono-data shrink-0 text-kinexis-focus">
                    +{w.avg_primary_change}%
                  </span>
                  <span className="truncate">
                    {w.client_name ? `${w.client_name} \u00b7 ` : ""}
                    {w.label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {aiValue.length > 0 && (
        <div className="panel mt-3 p-4">
          <p className="section-label mb-1">AI value by client</p>
          <p className="text-muted mb-3 text-xs">
            Accounts that got the most from AI recommendations this month (adoption + attributed
            lift).
          </p>
          <ul className="space-y-1.5">
            {aiValue.slice(0, 8).map((row) => (
              <li key={row.client_id}>
                <button
                  type="button"
                  className="motion-micro flex w-full items-center gap-2 text-left text-[13px] text-ink-secondary hover:text-ink"
                  onClick={() => onOpenClient(row.client_id, { tab: "prescribe" })}
                >
                  <span className="font-mono-data w-12 shrink-0 text-kinexis-focus">
                    {Math.round(row.ai_value_score)}
                  </span>
                  <span className="flex-1 truncate">{row.client_name}</span>
                  <span className="text-muted font-mono-data shrink-0 text-[11px]">
                    {row.plans_adopted} adopted
                    {row.attributed_lift_avg
                      ? ` \u00b7 ${row.attributed_lift_avg >= 0 ? "+" : ""}${row.attributed_lift_avg}%`
                      : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </CollapsibleSection>
  );
}

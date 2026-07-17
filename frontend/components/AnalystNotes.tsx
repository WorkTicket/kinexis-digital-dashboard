"use client";

import { Panel } from "@/components/ui/Panel";

export type NarrativePriority = {
  priority: number;
  title: string;
  severity: string;
  issue: string;
  actions: string[];
  measure: string;
  success_metric?: string;
};

export type ParsedNarrative = {
  headline: string;
  priorities: NarrativePriority[];
  body: string;
};

const FALLBACK_COPY =
  "Not enough synced metrics yet to write a reliable executive summary. Connect datasources and run Sync, then try Save month again.";

function stripMarkdown(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/^[-*_]{3,}\s*$/gm, "")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "• ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function isNarrativeSpam(text: string): boolean {
  const lines = text
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return false;
  const naHits = lines.filter((l) => /n\/a vs prior/i.test(l)).length;
  const scoreHits = lines.filter((l) =>
    /^(overall|people|tasks|issues|risk|next)\s*:/i.test(l)
  ).length;
  const uniqueRatio = new Set(lines).size / lines.length;
  return naHits >= 3 || scoreHits >= 4 || (lines.length >= 6 && uniqueRatio < 0.45);
}

export function parseNarrative(raw: string | null | undefined): ParsedNarrative {
  if (!raw?.trim()) {
    return { headline: "", priorities: [], body: "" };
  }

  const text = raw.trim();
  try {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    const jsonText = start >= 0 && end > start ? text.slice(start, end + 1) : text;
    const data = JSON.parse(jsonText) as Record<string, unknown>;
    if (data && typeof data === "object" && (data.priorities || data.headline || data.summary)) {
      const list = (data.priorities || data.recommendations || []) as unknown[];
      const priorities: NarrativePriority[] = list
        .filter((p): p is Record<string, unknown> => Boolean(p) && typeof p === "object")
        .map((p, i) => {
          let actions = p.actions ?? p.steps ?? [];
          if (typeof actions === "string") actions = [actions];
          if (!Array.isArray(actions)) actions = [];
          return {
            priority: Number(p.priority) || i + 1,
            title: String(p.title || p.name || `Priority ${i + 1}`),
            severity: String(p.severity || "medium").toLowerCase(),
            issue: String(p.issue || p.why || "").trim(),
            actions: (actions as unknown[]).map((a) => String(a).trim()).filter(Boolean),
            measure: String(p.measure || "").trim(),
            success_metric: String(p.success_metric || p.metric || "").trim() || undefined,
          };
        });
      return {
        headline: String(data.headline || data.summary || "").trim(),
        priorities,
        body: "",
      };
    }
  } catch {
    /* legacy prose */
  }

  return { headline: "", priorities: [], body: stripMarkdown(text) };
}

function severityTone(severity: string) {
  if (severity === "high" || severity === "critical") {
    return "bg-kinexis-risk/15 text-kinexis-risk border-kinexis-risk/30";
  }
  if (severity === "low") {
    return "bg-surface-elevated text-muted border-surface-border";
  }
  return "bg-kinexis-signal/15 text-kinexis-signal border-kinexis-signal/30";
}

type Props = {
  content: string;
  className?: string;
  /** Softer bordered cards when rendered inside a Panel (e.g. report executive summary). */
  nested?: boolean;
};

export default function AnalystNotes({ content, className = "", nested = false }: Props) {
  const narrative = parseNarrative(content);

  if (narrative.priorities.length > 0) {
    return (
      <div className={`space-y-4 ${className}`}>
        {narrative.headline && (
          <p className="text-sm leading-relaxed text-ink-secondary">{narrative.headline}</p>
        )}
        <div className="space-y-3">
          {narrative.priorities.map((p) => {
            const card = (
              <>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="font-mono-data text-muted text-[11px]">#{p.priority}</span>
                  <h4 className="min-w-0 flex-1 text-[13px] font-medium text-ink">{p.title}</h4>
                  <span className={`badge border ${severityTone(p.severity)}`}>{p.severity}</span>
                </div>
                {p.success_metric && (
                  <p className="mb-2 text-[11px] font-medium tracking-wide text-kinexis-focus">
                    Moves {p.success_metric}
                  </p>
                )}
                {p.issue && (
                  <p className="mb-3 text-[13px] leading-relaxed text-ink-secondary">{p.issue}</p>
                )}
                {p.actions.length > 0 && (
                  <ul className="mb-3 space-y-1.5">
                    {p.actions.map((a) => (
                      <li key={a} className="flex gap-2 text-[13px] leading-relaxed text-ink">
                        <span className="text-muted font-mono-data mt-0.5 shrink-0 text-[11px]">
                          →
                        </span>
                        <span>{a}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {p.measure && (
                  <p className="text-muted text-xs leading-relaxed">
                    <span className="font-medium text-ink-dim">Measure: </span>
                    {p.measure}
                  </p>
                )}
              </>
            );

            if (nested) {
              return (
                <div
                  key={`${p.priority}-${p.title}`}
                  className="rounded-md border border-[color:var(--border-subtle)] bg-surface-lighter/40 p-4"
                >
                  {card}
                </div>
              );
            }

            return (
              <Panel key={`${p.priority}-${p.title}`} padding="md">
                {card}
              </Panel>
            );
          })}
        </div>
      </div>
    );
  }

  if (narrative.body) {
    if (isNarrativeSpam(narrative.body)) {
      return (
        <div className={`text-sm leading-relaxed text-ink-secondary ${className}`}>
          {FALLBACK_COPY}
        </div>
      );
    }
    return (
      <div
        className={`whitespace-pre-wrap text-sm leading-relaxed text-ink-secondary ${className}`}
      >
        {narrative.body}
      </div>
    );
  }

  return (
    <div className={`text-sm leading-relaxed text-ink-secondary ${className}`}>{FALLBACK_COPY}</div>
  );
}

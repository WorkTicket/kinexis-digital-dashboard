"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, FileText, Sparkles } from "lucide-react";
import { api, ContentBrief, Insight, Task } from "@/lib/api";
import { useToast } from "@/components/Toast";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { Panel } from "@/components/ui/Panel";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

type Props = {
  clientId: number;
  insights: Insight[];
  onTaskCreated?: (task: Task) => void;
};

function outlinePreview(outline: unknown[]): string[] {
  return outline.slice(0, 10).map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") {
      const o = item as {
        h2?: string;
        title?: string;
        heading?: string;
        notes?: string;
        h3?: string[];
      };
      const head = o.h2 || o.title || o.heading;
      if (head && o.notes) return `${head} — ${o.notes}`;
      if (head && Array.isArray(o.h3) && o.h3.length)
        return `${head} (${o.h3.slice(0, 3).join(", ")})`;
      return head || JSON.stringify(item).slice(0, 100);
    }
    return String(item);
  });
}

export default function BriefsView({ clientId, insights, onTaskCreated }: Props) {
  const { error: toastError } = useToast();
  const [briefs, setBriefs] = useState<ContentBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const contentInsights = insights.filter(
    (i) =>
      !i.resolved &&
      (i.type === "content_opportunity" || i.type.includes("content") || i.type.includes("ctr"))
  );

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const list = await api.actions.listBriefs(clientId);
      setBriefs(list);
    } catch (e) {
      console.warn(e);
      setLoadError(e instanceof Error ? e.message : "Failed to load briefs");
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async (insightId: number) => {
    setGenerating(insightId);
    setError(null);
    try {
      const res = await api.actions.generateBrief(clientId, insightId);
      if (res.status === "skipped") {
        setError(res.message || "AI not configured");
      } else {
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate brief");
    } finally {
      setGenerating(null);
    }
  };

  const approve = async (briefId: number) => {
    try {
      await api.actions.updateBriefStatus(briefId, "approved");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to approve brief");
    }
  };

  const createTask = async (brief: ContentBrief) => {
    try {
      const titles = Array.isArray(brief.title) ? brief.title : [];
      const notes = `Content brief: ${brief.keyword}${titles[0] ? ` — ${titles[0]}` : ""} (${brief.word_count || "?"} words)`;
      const task = await api.tasks.create({
        client_id: clientId,
        insight_id: brief.insight_id || undefined,
        brief_id: brief.id,
        assigned_to: "Content",
        result_notes: notes,
      });
      if (brief.insight_id) {
        api.insights.resolve(brief.insight_id).catch((e) => {
          console.warn("Failed to resolve insight after brief task", e);
          toastError("Task created, but could not mark insight resolved");
        });
      }
      onTaskCreated?.(task);
      if (brief.status === "draft") {
        await api.actions.updateBriefStatus(brief.id, "approved");
        await load();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create task from brief");
    }
  };

  return (
    <div className="animate-fade-up space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="section-label">Writer briefs</h2>
          <p className="section-title">
            Production-ready content briefs for Execute — not the client success report (that lives
            under Report).
          </p>
        </div>
      </div>

      {error && (
        <Panel>
          <p className="text-[13px] text-kinexis-risk">{error}</p>
        </Panel>
      )}

      <Panel padding="lg">
        <p className="section-label mb-3">Generate from insight</p>
        {contentInsights.length === 0 ? (
          <EmptyState
            className="!py-6"
            title="No open content/CTR insights"
            description="Sync data to find opportunities."
          />
        ) : (
          <ul className="space-y-2">
            {contentInsights.slice(0, 8).map((ins) => (
              <li
                key={ins.id}
                className="flex flex-col justify-between gap-2 border-b border-[color:var(--border-subtle)] py-2 last:border-0 sm:flex-row sm:items-center"
              >
                <div className="min-w-0">
                  <Badge tone="default" className="mr-2">
                    {ins.type}
                  </Badge>
                  <span className="line-clamp-2 text-sm text-ink-secondary">{ins.message}</span>
                </div>
                <Button
                  variant="soft"
                  size="sm"
                  disabled={generating != null}
                  onClick={() => generate(ins.id)}
                  className="shrink-0"
                >
                  <Sparkles size={12} />
                  {generating === ins.id ? "Generating…" : "Generate brief"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <section className="space-y-3">
        <p className="section-label">Saved briefs</p>
        {loading ? (
          <LoadingState label="Loading briefs…" variant="spinner" />
        ) : loadError ? (
          <ErrorState
            title="Briefs unavailable"
            description={loadError}
            onRetry={() => void load()}
          />
        ) : briefs.length === 0 ? (
          <EmptyState
            title="No briefs yet"
            description="Generate one from a content opportunity above."
          />
        ) : (
          briefs.map((brief) => (
            <Panel key={brief.id} padding={false} className="overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3.5">
                <div className="flex min-w-0 items-center gap-2">
                  <FileText size={16} className="shrink-0 text-kinexis-focus" />
                  <span className="truncate font-medium text-ink">
                    {brief.keyword || "Untitled keyword"}
                  </span>
                  <Badge tone={brief.status === "approved" ? "brand" : "warning"}>
                    {brief.status}
                  </Badge>
                </div>
                <div className="flex items-center gap-1.5">
                  {brief.status === "draft" && (
                    <Button variant="ghost" size="sm" onClick={() => approve(brief.id)}>
                      <CheckCircle2 size={12} /> Approve
                    </Button>
                  )}
                  <Button variant="soft" size="sm" onClick={() => createTask(brief)}>
                    Create task
                  </Button>
                </div>
              </div>
              <div className="space-y-4 p-5">
                {Array.isArray(brief.title) && brief.title.length > 0 && (
                  <div>
                    <p className="text-muted mb-1.5 text-[12px] font-medium font-semibold">
                      Title options
                    </p>
                    <ul className="space-y-1">
                      {brief.title.map((t, i) => (
                        <li key={i} className="text-sm text-ink-secondary">
                          {typeof t === "string" ? t : JSON.stringify(t)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="text-muted flex flex-wrap gap-4 text-xs">
                  {brief.word_count ? (
                    <span className="font-mono-data">{brief.word_count} words</span>
                  ) : null}
                  {brief.related_keywords?.length > 0 && (
                    <span className="max-w-full truncate">
                      Keywords: {brief.related_keywords.slice(0, 6).join(", ")}
                    </span>
                  )}
                </div>
                {Array.isArray(brief.outline) && brief.outline.length > 0 && (
                  <div>
                    <p className="text-muted mb-1.5 text-[12px] font-medium font-semibold">
                      Outline
                    </p>
                    <ul className="text-muted list-disc space-y-1 pl-5 text-sm">
                      {outlinePreview(brief.outline).map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Panel>
          ))
        )}
      </section>
    </div>
  );
}

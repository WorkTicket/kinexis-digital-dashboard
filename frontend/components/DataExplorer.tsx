"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  Cell,
} from "recharts";
import { api, Opportunities } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { LoadingState } from "@/components/ui/LoadingState";
import { CHART, chartAxisTick, chartGridProps, chartToneForDelta } from "@/lib/chartTheme";

type Props = {
  clientId: number;
  days: number;
  onDaysChange: (days: number) => void;
};

export default function DataExplorer({ clientId, days, onDaysChange }: Props) {
  const [data, setData] = useState<Opportunities | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const opp = await api.metrics.opportunities(clientId, days);
      setData(opp);
    } catch (e) {
      console.warn(e);
      setData(null);
      setError(e instanceof Error ? e.message : "Failed to load opportunities");
    } finally {
      setLoading(false);
    }
  }, [clientId, days]);

  useEffect(() => {
    void load();
  }, [load]);

  const scatterData = useMemo(() => {
    if (!data?.landing_pages?.length) return [];
    return data.landing_pages.map((r) => ({
      page: r.page,
      sessions: r.sessions,
      cvr: r.cvr,
      conversions: r.conversions,
      vs_avg: r.vs_avg,
      // Bubble size for ZAxis (min size so small pages stay visible)
      size: Math.max(40, Math.min(400, r.sessions)),
    }));
  }, [data]);

  return (
    <div className="animate-fade-up space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="section-label">Opportunity explorer</h2>
          <p className="section-title">Queries, CTR gaps, and landing-page conversion.</p>
        </div>
        <div className="flex gap-2">
          {[14, 28, 56].map((d) => (
            <Button
              key={d}
              size="sm"
              variant={days === d ? "soft" : "ghost"}
              onClick={() => onDaysChange(d)}
            >
              {d}d
            </Button>
          ))}
        </div>
      </div>

      {loading ? (
        <LoadingState variant="table" rows={6} />
      ) : error ? (
        <ErrorState
          title="Couldn’t load opportunities"
          description={error}
          onRetry={() => void load()}
        />
      ) : !data ? (
        <EmptyState
          title="No opportunity data"
          description="Connect Search Console and GA4, then sync to populate rising queries, CTR gaps, and landing pages."
        />
      ) : (
        <>
          <Table
            title="Rising queries"
            empty="No rising queries in range."
            headers={["Query", "Impr.", "Growth", "Pos", "Clicks"]}
            rows={data.rising_queries.map((r) => [
              r.query,
              r.impressions.toLocaleString(),
              `+${r.growth_pct}%`,
              r.position.toFixed(1),
              r.clicks.toLocaleString(),
            ])}
          />
          <Table
            title="CTR underperformers"
            empty="No CTR gaps detected."
            headers={["Page", "Impr.", "CTR", "Expected", "Gap"]}
            rows={data.ctr_underperformers.map((r) => [
              r.page,
              r.impressions.toLocaleString(),
              `${(r.ctr > 1 ? r.ctr : r.ctr * 100).toFixed(1)}%`,
              `${(r.expected_ctr > 1 ? r.expected_ctr : r.expected_ctr * 100).toFixed(1)}%`,
              `${r.gap_pct}%`,
            ])}
          />

          <Panel className="overflow-hidden" padding={false}>
            <div className="border-b border-surface-border/80 px-4 py-4">
              <p className="text-sm font-semibold text-ink">
                Landing pages · traffic vs conversion
              </p>
              <p className="text-muted mt-0.5 text-xs">
                Sessions (x) vs conversion rate (y). Larger dots = more traffic. Green = above avg
                CVR.
              </p>
            </div>
            {scatterData.length === 0 ? (
              <p className="text-muted px-4 py-6 text-sm">
                No landing page data. Connect GA4 and sync to populate this view.
              </p>
            ) : (
              <>
                <div className="h-[280px] px-2 pb-2 pt-4 sm:h-[320px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid {...chartGridProps} />
                      <XAxis
                        type="number"
                        dataKey="sessions"
                        name="Sessions"
                        tick={chartAxisTick}
                        axisLine={false}
                        tickLine={false}
                        label={{
                          value: "Sessions",
                          position: "insideBottom",
                          offset: -2,
                          fill: CHART.axisFill,
                          fontSize: 11,
                        }}
                      />
                      <YAxis
                        type="number"
                        dataKey="cvr"
                        name="CVR %"
                        unit="%"
                        tick={chartAxisTick}
                        axisLine={false}
                        tickLine={false}
                        width={48}
                        label={{
                          value: "CVR %",
                          angle: -90,
                          position: "insideLeft",
                          fill: CHART.axisFill,
                          fontSize: 11,
                        }}
                      />
                      <ZAxis type="number" dataKey="size" range={[40, 280]} />
                      <Tooltip
                        cursor={{ strokeDasharray: "3 3" }}
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const p = payload[0]?.payload as (typeof scatterData)[0] | undefined;
                          if (!p) return null;
                          return (
                            <div
                              className="max-w-[240px] rounded-lg border border-[color:var(--border-default)] bg-surface-elevated px-3 py-2 text-xs shadow-dropdown"
                              style={{ fontFamily: CHART.monoFamily }}
                            >
                              <p
                                className="mb-1 truncate font-ui font-medium text-ink"
                                title={p.page}
                              >
                                {p.page}
                              </p>
                              <p className="text-muted font-mono-data">
                                {p.sessions.toLocaleString()} sessions ·{" "}
                                {p.conversions.toLocaleString()} conv · {p.cvr.toFixed(2)}% CVR
                              </p>
                              <p className="text-muted font-mono-data mt-0.5">
                                {p.vs_avg >= 0 ? "+" : ""}
                                {p.vs_avg.toFixed(2)}pp vs avg
                              </p>
                            </div>
                          );
                        }}
                      />
                      <Scatter data={scatterData} fill={CHART.focus}>
                        {scatterData.map((entry) => (
                          <Cell
                            key={entry.page}
                            fill={chartToneForDelta(entry.vs_avg)}
                            fillOpacity={0.75}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                <Table
                  title=""
                  empty="No landing page data."
                  headers={["Page", "Sessions", "Conv.", "CVR", "vs avg"]}
                  rows={data.landing_pages.map((r) => [
                    r.page,
                    r.sessions.toLocaleString(),
                    r.conversions.toLocaleString(),
                    `${r.cvr.toFixed(2)}%`,
                    `${r.vs_avg >= 0 ? "+" : ""}${r.vs_avg.toFixed(2)}pp`,
                  ])}
                  nested
                />
              </>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function Table({
  title,
  empty,
  headers,
  rows,
  nested = false,
}: {
  title: string;
  empty: string;
  headers: string[];
  rows: string[][];
  nested?: boolean;
}) {
  const body =
    rows.length === 0 ? (
      <p className="text-muted px-4 py-6 text-sm">{empty}</p>
    ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-muted border-b border-surface-border/60 text-left text-[12px] font-medium">
              {headers.map((h) => (
                <th key={h} className="whitespace-nowrap px-4 py-3 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-surface-border/40 last:border-0">
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={`px-4 py-3 ${j === 0 ? "max-w-[280px] truncate text-ink" : "font-mono-data text-muted"}`}
                    title={j === 0 ? cell : undefined}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );

  if (nested) {
    return <div className="border-t border-surface-border/80">{body}</div>;
  }

  return (
    <Panel className="overflow-hidden" padding={false}>
      <div className="border-b border-surface-border/80 px-4 py-4">
        <p className="text-sm font-semibold text-ink">{title}</p>
      </div>
      {body}
    </Panel>
  );
}

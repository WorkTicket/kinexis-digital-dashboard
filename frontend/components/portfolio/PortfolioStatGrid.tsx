"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, BarChart3, DollarSign, Target, TrendingUp, Users } from "lucide-react";

function AnimatedNumber({ value, className = "" }: { value: number; className?: string }) {
  const prevRef = useRef(value);
  const [animKey, setAnimKey] = useState(0);

  useEffect(() => {
    if (prevRef.current !== value) {
      setAnimKey((k) => k + 1);
      prevRef.current = value;
    }
  }, [value]);

  return (
    <span key={animKey} className={`animate-counter inline-block ${className}`}>
      {value.toLocaleString()}
    </span>
  );
}

type Props = {
  clientCount: number;
  healthy: number;
  atRisk: number;
  critical: number;
  watch: number;
  overdue: number;
  totalClicks: number;
  revenue30: number;
  leads30: number;
  avgAttributedLift: number;
  winsCount: number;
};

export function PortfolioStatGrid({
  clientCount,
  healthy,
  atRisk,
  critical,
  watch,
  overdue,
  totalClicks,
  revenue30,
  leads30,
  avgAttributedLift,
  winsCount,
}: Props) {
  return (
    <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <Users size={12} className="text-kinexis-focus" />
          <span className="text-muted text-[11px] font-medium leading-none">Clients</span>
        </div>
        <AnimatedNumber
          value={clientCount}
          className="text-[22px] font-semibold tabular-nums text-ink"
        />
        <span className="text-muted text-[11px]">{healthy} healthy</span>
      </div>
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <AlertTriangle size={12} className="text-kinexis-risk" />
          <span className="text-muted text-[11px] font-medium leading-none">At Risk</span>
        </div>
        <AnimatedNumber
          value={atRisk}
          className="text-[22px] font-semibold tabular-nums text-kinexis-risk"
        />
        <span className="text-muted text-[11px]">
          {critical} critical \u00b7 {watch} watch
        </span>
      </div>
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <Target size={12} className="text-kinexis-momentum" />
          <span className="text-muted text-[11px] font-medium leading-none">Overdue</span>
        </div>
        <AnimatedNumber
          value={overdue}
          className="text-[22px] font-semibold tabular-nums text-kinexis-momentum"
        />
        <span className="text-muted text-[11px]">clients with late work</span>
      </div>
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <BarChart3 size={12} className="text-kinexis-proof" />
          <span className="text-muted text-[11px] font-medium leading-none">Clicks 7d</span>
        </div>
        <AnimatedNumber
          value={totalClicks}
          className="text-[22px] font-semibold tabular-nums text-ink"
        />
        <span className="text-muted text-[11px]">portfolio total</span>
      </div>
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <DollarSign size={12} className="text-kinexis-proof" />
          <span className="text-muted text-[11px] font-medium leading-none">Revenue 7d</span>
        </div>
        <span className="text-[22px] font-semibold tabular-nums text-ink">
          ${revenue30.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </span>
        <span className="text-muted text-[11px]">
          {leads30 > 0 ? `${leads30.toLocaleString()} leads` : "no CRM data"}
        </span>
      </div>
      <div className="panel flex flex-col gap-1 !p-3.5">
        <div className="flex items-center gap-1.5">
          <TrendingUp size={12} className="text-kinexis-focus" />
          <span className="text-muted text-[11px] font-medium leading-none">Avg Win Lift</span>
        </div>
        <span
          className={`text-[22px] font-semibold tabular-nums ${avgAttributedLift >= 0 ? "text-kinexis-proof" : "text-kinexis-risk"}`}
        >
          {avgAttributedLift >= 0 ? "+" : ""}
          {avgAttributedLift.toFixed(0)}%
        </span>
        <span className="text-muted text-[11px]">{winsCount} wins 30d</span>
      </div>
    </div>
  );
}

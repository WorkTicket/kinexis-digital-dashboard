"use client";

import { ReportAgencyMark } from "@/components/report/ReportAgencyMark";
import type { ReportAgency, SuccessReport } from "@/lib/api";

type Props = {
  report: SuccessReport;
  agency: ReportAgency;
  periodLabel: string;
};

export function ReportCover({ report, agency, periodLabel }: Props) {
  const isMonthly = report.period.mode === "monthly";

  return (
    <header className="report-cover relative flex flex-col bg-[var(--surface)]">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
        style={{ backgroundColor: agency.accent }}
        aria-hidden
      />
      <ReportAgencyMark
        name={agency.name}
        accent={agency.accent}
        logoUrl={agency.logo_url || undefined}
      />
      <h1 className="text-display mt-16 max-w-[16ch] break-words font-display font-normal leading-[1.06] tracking-[-0.03em] text-[var(--kinexis-ink)] sm:mt-20">
        {report.client.name}
      </h1>
      <p className="mt-6 max-w-md text-[15px] leading-relaxed text-ink-secondary">
        {periodLabel}
        {!isMonthly && (
          <span className="mt-1 block font-mono text-xs text-[var(--kinexis-mist)]">
            {report.period.start} → {report.period.end}
          </span>
        )}
      </p>
    </header>
  );
}

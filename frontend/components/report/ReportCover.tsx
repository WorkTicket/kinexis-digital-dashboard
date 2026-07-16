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
  const isDiagnostic = report.report_kind === "diagnostic";
  const showPowered = agency.is_white_label && agency.name.trim().toLowerCase() !== "kinexis";

  return (
    <header className="report-cover relative flex min-h-[420px] flex-col bg-[var(--surface)] px-6 py-10 sm:min-h-[520px] sm:px-10 sm:py-14">
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
      <p className="mt-14 text-[12px] font-medium text-[var(--kinexis-mist)]">
        {isDiagnostic ? "Diagnostic / kickoff report" : "Client success report"}
      </p>
      <h1 className="mt-3 max-w-[14ch] break-words font-display text-[2.5rem] font-normal leading-[1.08] tracking-[-0.025em] text-[var(--kinexis-ink)] sm:text-5xl md:text-[3.5rem]">
        {report.client.name}
      </h1>
      <p className="mt-5 max-w-md text-[14px] leading-relaxed text-ink-secondary">
        {isDiagnostic
          ? "Findings and prescriptions — not yet executed or proven"
          : isMonthly
            ? "Monthly performance"
            : "Success report"}{" "}
        · {periodLabel}
        {!isMonthly && (
          <span className="mt-1 block font-mono text-xs text-[var(--kinexis-mist)] sm:ml-2 sm:mt-0 sm:inline">
            {report.period.start} → {report.period.end}
          </span>
        )}
      </p>
      <div className="mt-auto border-t border-[color:var(--border-subtle)] pt-16">
        <p className="pt-5 text-[13px] text-[var(--kinexis-mist)]">
          {report.client.industry || "Digital performance"}
        </p>
        {showPowered && (
          <p className="mt-2 text-[12px] font-medium text-[var(--kinexis-mist)]">
            Proof engine by Kinexis
          </p>
        )}
      </div>
    </header>
  );
}

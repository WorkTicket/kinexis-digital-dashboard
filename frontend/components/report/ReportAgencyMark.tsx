"use client";

type Props = {
  name: string;
  accent: string;
  logoUrl?: string;
  className?: string;
};

/** Agency / Kinexis mark for report cover — logo URL or wordmark glyph. */
export function ReportAgencyMark({ name, accent, logoUrl, className = "" }: Props) {
  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={name}
        className={`h-9 max-w-[200px] object-contain object-left ${className}`.trim()}
      />
    );
  }

  const initial = (name || "K").trim().charAt(0).toUpperCase() || "K";

  return (
    <div className={`flex items-center gap-3 ${className}`.trim()}>
      <span
        className="inline-flex h-8 w-8 items-center justify-center font-display text-base font-normal text-white"
        style={{ backgroundColor: accent, borderRadius: "var(--radius-sm)" }}
        aria-hidden
      >
        {initial}
      </span>
      <span className="font-display text-xl font-normal tracking-[-0.02em] text-[var(--kinexis-ink)]">
        {name}
      </span>
    </div>
  );
}

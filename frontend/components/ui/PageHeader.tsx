type Props = {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  meta?: React.ReactNode;
  /** "page" = shell-level title; "section" = nested under client header */
  level?: "page" | "section";
  eyebrow?: string;
  className?: string;
};

export function PageHeader({
  title,
  description,
  actions,
  meta,
  level = "page",
  eyebrow,
  className = "",
}: Props) {
  const TitleTag = level === "page" ? "h1" : "h2";
  const titleClass =
    level === "page" ? "text-title" : "text-[15px] font-semibold text-ink tracking-tight";

  return (
    <header className={`animate-fade-up mb-8 ${className}`.trim()}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          {eyebrow && (
            <p className="mb-2 text-[12px] font-semibold tracking-tight text-kinexis-focus">
              {eyebrow}
            </p>
          )}
          <TitleTag className={`${titleClass} truncate`}>{title}</TitleTag>
          {description && <p className="text-subtitle mt-2.5 max-w-xl">{description}</p>}
          {meta && <div className="text-caption mt-2.5">{meta}</div>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2 pb-0.5">{actions}</div>}
      </div>
    </header>
  );
}

type Props = {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
};

export function EmptyState({ title, description, action, icon, className = "" }: Props) {
  return (
    <div className={`empty-state ${className}`.trim()}>
      {icon && (
        <div
          className="mx-auto mb-5 flex h-12 w-12 items-center justify-center border border-kinexis-focus/15 bg-kinexis-focus/[0.08] text-kinexis-focus"
          style={{ borderRadius: "var(--radius-lg)" }}
          aria-hidden
        >
          {icon}
        </div>
      )}
      <p className="text-[16px] font-semibold tracking-tight text-ink">{title}</p>
      {description && (
        <p className="text-muted mx-auto mt-2 max-w-sm text-[14px] leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}

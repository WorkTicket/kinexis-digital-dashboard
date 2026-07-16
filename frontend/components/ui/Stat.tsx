type Props = {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "default" | "success" | "danger" | "warning" | "brand";
  onClick?: () => void;
  active?: boolean;
  className?: string;
};

const toneValue: Record<NonNullable<Props["tone"]>, string> = {
  default: "text-ink",
  success: "text-kinexis-proof",
  danger: "text-kinexis-risk",
  warning: "text-kinexis-signal",
  brand: "text-kinexis-focus",
};

export function Stat({
  label,
  value,
  hint,
  tone = "default",
  onClick,
  active,
  className = "",
}: Props) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-pressed={onClick ? (active ?? false) : undefined}
      aria-label={onClick ? label : undefined}
      className={`metric-tile motion-micro text-left ${
        onClick ? "cursor-pointer hover:border-[color:var(--border-strong)]" : ""
      } ${active ? "!border-kinexis-focus/40 !bg-kinexis-focus/[0.06]" : ""} ${className}`.trim()}
    >
      <p className="text-label whitespace-nowrap">{label}</p>
      <p className={`text-metric mt-2 text-[1.5rem] leading-none ${toneValue[tone]}`}>{value}</p>
      {hint && <p className="text-caption mt-2 truncate">{hint}</p>}
    </Comp>
  );
}

type Tone =
  "default" | "brand" | "success" | "danger" | "warning" | "signal" | "proof" | "momentum" | "risk";

/** Soft tint badges — studio language */
const toneClass: Record<Tone, string> = {
  default: "bg-surface-lighter text-ink-secondary border border-[color:var(--border-subtle)]",
  brand: "bg-kinexis-focus/10 text-kinexis-focus border border-kinexis-focus/15",
  success: "bg-kinexis-proof/10 text-kinexis-proof border border-kinexis-proof/15",
  proof: "bg-kinexis-proof/10 text-kinexis-proof border border-kinexis-proof/15",
  danger: "bg-kinexis-risk/10 text-kinexis-risk border border-kinexis-risk/15",
  risk: "bg-kinexis-risk/10 text-kinexis-risk border border-kinexis-risk/15",
  warning: "bg-kinexis-signal/10 text-kinexis-signal border border-kinexis-signal/15",
  signal: "bg-kinexis-signal/10 text-kinexis-signal border border-kinexis-signal/15",
  momentum: "bg-kinexis-momentum/10 text-kinexis-momentum border border-kinexis-momentum/15",
};

type Props = {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
};

export function Badge({ children, tone = "default", className = "" }: Props) {
  return <span className={`badge ${toneClass[tone]} ${className}`.trim()}>{children}</span>;
}

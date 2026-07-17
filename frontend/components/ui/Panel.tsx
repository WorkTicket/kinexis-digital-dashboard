type Props = {
  children: React.ReactNode;
  className?: string;
  elevated?: boolean;
  padding?: boolean | "sm" | "md" | "lg";
  id?: string;
};

const padClass = {
  sm: "p-4",
  md: "p-4",
  lg: "p-6",
};

export function Panel({ children, className = "", elevated = false, padding = true, id }: Props) {
  const pad = padding === false ? "" : padding === true ? padClass.md : padClass[padding];

  return (
    <div id={id} className={`${elevated ? "panel-elevated" : "panel"} ${pad} ${className}`.trim()}>
      {children}
    </div>
  );
}

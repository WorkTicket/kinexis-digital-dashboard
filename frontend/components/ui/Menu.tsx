"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";

type MenuContextValue = {
  close: () => void;
  open: boolean;
};

const MenuContext = createContext<MenuContextValue | null>(null);

type MenuProps = {
  trigger: (props: { open: boolean; toggle: () => void; menuId: string }) => ReactNode;
  children: ReactNode;
  align?: "left" | "right";
  side?: "top" | "bottom" | "auto";
  className?: string;
  contentClassName?: string;
  onOpenChange?: (open: boolean) => void;
  fullWidth?: boolean;
};

export function Menu({
  trigger,
  children,
  align = "right",
  side = "auto",
  className = "",
  contentClassName = "",
  onOpenChange,
  fullWidth = false,
}: MenuProps) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<"top" | "bottom">("bottom");
  const ref = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback(() => {
    setOpen(false);
    onOpenChange?.(false);
    queueMicrotask(() => {
      const btn = ref.current?.querySelector<HTMLElement>("[aria-haspopup='menu']");
      btn?.focus();
    });
  }, [onOpenChange]);

  const toggle = useCallback(() => {
    setOpen((prev) => {
      const next = !prev;
      onOpenChange?.(next);
      return next;
    });
  }, [onOpenChange]);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, close]);

  useEffect(() => {
    if (!open || !ref.current) return;
    if (side === "top" || side === "bottom") {
      setPlacement(side);
      return;
    }
    const rect = ref.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    setPlacement(spaceBelow < 180 && rect.top > spaceBelow ? "top" : "bottom");
  }, [open, side]);

  useEffect(() => {
    if (!open || !menuRef.current) return;
    const items = () =>
      Array.from(
        menuRef.current!.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])')
      );

    const list = items();
    list[0]?.focus();

    const onKey = (e: KeyboardEvent) => {
      const current = items();
      if (!current.length) return;
      const idx = current.indexOf(document.activeElement as HTMLButtonElement);

      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = idx < 0 ? 0 : (idx + 1) % current.length;
        current[next]?.focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const next = idx < 0 ? current.length - 1 : (idx - 1 + current.length) % current.length;
        current[next]?.focus();
      } else if (e.key === "Home") {
        e.preventDefault();
        current[0]?.focus();
      } else if (e.key === "End") {
        e.preventDefault();
        current[current.length - 1]?.focus();
      } else if (e.key === "Tab") {
        e.preventDefault();
        close();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  // focus restore handled via querySelector on close
  return (
    <MenuContext.Provider value={{ close, open }}>
      <div
        ref={ref}
        className={`relative shrink-0 ${fullWidth ? "flex w-full" : "inline-flex"} ${
          open ? "z-50" : ""
        } ${className}`.trim()}
      >
        {trigger({ open, toggle, menuId })}
        {open && (
          <div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-orientation="vertical"
            className={`panel animate-scale-in absolute z-50 w-max min-w-[10.5rem] max-w-[16rem] rounded-lg py-1 shadow-dropdown ${
              placement === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5"
            } ${align === "right" ? "right-0" : "left-0"} ${contentClassName}`.trim()}
          >
            {children}
          </div>
        )}
      </div>
    </MenuContext.Provider>
  );
}

type MenuItemProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  danger?: boolean;
  icon?: ReactNode;
};

export function MenuItem({
  children,
  danger = false,
  icon,
  className = "",
  onClick,
  ...rest
}: MenuItemProps) {
  const ctx = useContext(MenuContext);

  return (
    <button
      type="button"
      role="menuitem"
      className={`motion-micro flex w-full items-center gap-2 px-3 py-2 text-sm outline-none focus-visible:bg-[color:var(--hover-fill)] disabled:cursor-not-allowed disabled:opacity-40 ${
        danger
          ? "text-kinexis-risk hover:bg-kinexis-risk/10 focus-visible:bg-kinexis-risk/10"
          : "text-ink-secondary hover:bg-[color:var(--hover-fill)] hover:text-ink"
      } ${className}`.trim()}
      onClick={(e) => {
        onClick?.(e);
        ctx?.close();
      }}
      {...rest}
    >
      {icon && <span className="shrink-0 opacity-80">{icon}</span>}
      <span className="truncate text-left">{children}</span>
    </button>
  );
}

export function MenuSeparator() {
  return <div role="separator" className="my-1 h-px bg-[color:var(--border-subtle)]" />;
}

type MenuIconTriggerProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  open?: boolean;
  menuId?: string;
  children: ReactNode;
};

/** Ghost icon trigger for overflow menus (use MoreVertical for ⋮). */
export function MenuIconTrigger({
  label,
  open = false,
  menuId,
  children,
  className = "",
  type = "button",
  onClick,
  ...rest
}: MenuIconTriggerProps) {
  return (
    <button
      type={type}
      aria-label={label}
      aria-haspopup="menu"
      aria-expanded={open}
      aria-controls={open ? menuId : undefined}
      title={label}
      className={`text-muted motion-micro inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-[color:var(--hover-fill)] hover:text-ink disabled:opacity-40 ${
        open ? "bg-white/[0.06] text-ink" : ""
      } ${className}`.trim()}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

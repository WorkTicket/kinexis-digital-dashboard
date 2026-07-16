"use client";

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "soft";
type Size = "sm" | "md";

const variantClass: Record<Variant, string> = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  soft: "btn-soft",
};

const sizeClass: Record<Size, string> = {
  sm: "!px-2.5 !py-1.5 !text-xs",
  md: "",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  { variant = "primary", size = "md", className = "", children, type = "button", ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`${variantClass[variant]} ${sizeClass[size]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  );
});

"use client";

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  label: string;
  size?: "sm" | "md";
};

const sizeClass = {
  sm: "h-7 w-7",
  md: "h-8 w-8",
};

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { children, label, size = "md", className = "", type = "button", ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={`icon-btn ${sizeClass[size]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  );
});

"use client";

import { forwardRef, useState } from "react";
import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";

type FieldProps = {
  label?: string;
  hint?: string;
  error?: string;
  className?: string;
  id?: string;
};

function FieldShell({
  label,
  hint,
  error,
  id,
  children,
}: FieldProps & { children: React.ReactNode }) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="text-label mb-1.5 block">
          {label}
        </label>
      )}
      {children}
      {error ? (
        <p className="mt-1.5 text-xs text-kinexis-risk" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-caption mt-1.5">{hint}</p>
      ) : null}
    </div>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> &
  FieldProps & {
    showPasswordToggle?: boolean;
  };

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, className = "", id, type, showPasswordToggle, ...rest },
  ref
) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  const isPassword = type === "password";
  const [showPassword, setShowPassword] = useState(false);
  const resolvedType = isPassword && showPassword ? "text" : type;

  return (
    <FieldShell label={label} hint={hint} error={error} id={inputId}>
      <div className="relative">
        <input
          ref={ref}
          id={inputId}
          type={resolvedType}
          className={`input-field ${error ? "!border-kinexis-risk/50" : ""} ${isPassword && showPasswordToggle !== false ? "pr-10" : ""} ${className}`.trim()}
          {...rest}
        />
        {isPassword && showPasswordToggle !== false && (
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="text-muted motion-micro absolute right-2 top-1/2 -translate-y-1/2 p-2 hover:text-ink-secondary"
            style={{ borderRadius: "var(--radius-sm)" }}
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? (
              <EyeOff size={14} strokeWidth={1.5} />
            ) : (
              <Eye size={14} strokeWidth={1.5} />
            )}
          </button>
        )}
      </div>
    </FieldShell>
  );
});

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & FieldProps;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, className = "", id, children, ...rest },
  ref
) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  return (
    <FieldShell label={label} hint={hint} error={error} id={inputId}>
      <select
        ref={ref}
        id={inputId}
        className={`input-field ${error ? "!border-kinexis-risk/50" : ""} ${className}`.trim()}
        {...rest}
      >
        {children}
      </select>
    </FieldShell>
  );
});

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & FieldProps;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className = "", id, ...rest },
  ref
) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
  return (
    <FieldShell label={label} hint={hint} error={error} id={inputId}>
      <textarea
        ref={ref}
        id={inputId}
        className={`input-field min-h-[88px] resize-y ${error ? "!border-kinexis-risk/50" : ""} ${className}`.trim()}
        {...rest}
      />
    </FieldShell>
  );
});

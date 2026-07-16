"use client";

export default function ShellLoadingScreen() {
  return (
    <div className="app-shell shell-atmosphere flex flex-col items-center justify-center gap-6">
      <div className="mark animate-fade-up !h-12 !w-12">
        <img src="/logo.svg" alt="" className="opacity-95" />
      </div>
      <div
        className="h-6 w-6 animate-spin rounded-full border-2 border-[color:var(--border-default)] border-t-kinexis-focus"
        aria-hidden
      />
      <p className="text-muted animate-fade-up text-[13px] font-medium">Starting Kinexis</p>
    </div>
  );
}

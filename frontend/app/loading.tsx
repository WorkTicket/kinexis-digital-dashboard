export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="text-center">
        <div
          className="text-title mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-xl font-bold text-white shadow-panel-lg"
          style={{ background: "var(--brand-gradient)" }}
        >
          K
        </div>
        <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-surface-border border-t-kinexis-focus" />
        <p className="text-body mt-4 font-medium text-muted">Loading Kinexis…</p>
      </div>
    </div>
  );
}

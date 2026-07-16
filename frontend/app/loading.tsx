export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#08090c]">
      <div className="text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563EB] to-[#06B6D4] text-lg font-bold text-white shadow-lg shadow-[#06B6D4]/30">
          K
        </div>
        <div className="mx-auto h-7 w-7 animate-spin rounded-full border-2 border-[#2a2d35] border-t-[#06B6D4]" />
        <p className="mt-4 text-sm font-medium text-[#82899a]">Loading Kinexis…</p>
      </div>
    </div>
  );
}

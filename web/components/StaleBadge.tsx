import { cn } from "@/lib/cn";

export function StaleBadge({ stale }: { stale: boolean }) {
  if (!stale) {
    return null;
  }
  return (
    <span
      className={cn(
        "rounded border border-down/40 px-1.5 py-0.5 text-[11px] uppercase tracking-wide text-down",
      )}
    >
      stale
    </span>
  );
}

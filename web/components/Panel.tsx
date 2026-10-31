import type { ReactNode } from "react";

export function Panel({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded border border-line p-4">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-[11px] uppercase tracking-wide text-mute">{title}</h2>
        {note ? <span className="text-[11px] text-mute">{note}</span> : null}
      </div>
      {children}
    </section>
  );
}

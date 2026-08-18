"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { fetchHealth, type Health } from "@/lib/api";

const TABS = [
  { href: "/", label: "Live", live: true },
  { href: "/outlook", label: "Outlook" },
  { href: "/dynamics", label: "Dynamics" },
  { href: "/valuation", label: "Valuation" },
  { href: "/opportunities", label: "Opportunities" },
  { href: "/watchlist", label: "Watchlist" },
] as const;

export function AppChrome() {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    void fetchHealth().then(setHealth);
  }, []);

  const dbOk = health?.ok === true;

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-ink/95 backdrop-blur">
      <div className="flex h-12 items-center gap-6 px-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 text-sm font-semibold tracking-tight">
          <Logo />
          Sector Panel
        </Link>
        <nav className="flex min-w-0 flex-1 items-center gap-1">
          {TABS.map((tab) => {
            const active = tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href);
            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={cn(
                  "relative rounded px-2.5 py-1 text-[13px] transition-colors",
                  active ? "text-white" : "text-mute hover:text-white",
                )}
              >
                <span className="inline-flex items-center gap-1.5">
                  {"live" in tab && tab.live ? (
                    <span className="h-1.5 w-1.5 rounded-full bg-down" aria-hidden />
                  ) : null}
                  {tab.label}
                </span>
                {active ? (
                  <span className="absolute inset-x-2 -bottom-[11px] h-px bg-white" />
                ) : null}
              </Link>
            );
          })}
        </nav>
        <label className="hidden md:block">
          <span className="sr-only">Search</span>
          <input
            disabled
            placeholder="Search names, sectors..."
            className="h-8 w-56 rounded border border-line bg-panel px-3 text-[13px] text-mute outline-none"
          />
        </label>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full border px-2.5 py-1 text-[12px] tabular-nums",
              "border-line text-mute",
            )}
            title="Risk-On is computed from stored prices on Day 5"
          >
            Risk-On —
          </span>
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              dbOk ? "bg-up" : "bg-down",
            )}
            title={dbOk ? "Postgres connected" : "API or database unreachable"}
          />
        </div>
      </div>
    </header>
  );
}

function Logo() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M1 12.5 5 8l3 2.5L15 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

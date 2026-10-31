import Link from "next/link";

import { cn } from "@/lib/cn";

export function TickerLink({ ticker, className }: { ticker: string; className?: string }) {
  return (
    <Link href={`/t/${encodeURIComponent(ticker)}`} className={cn("hover:underline", className)}>
      {ticker}
    </Link>
  );
}

import { WatchlistView } from "@/components/WatchlistView";
import { fetchWatchlist } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function WatchlistPage({
  searchParams,
}: {
  searchParams: Promise<{ ticker?: string | string[] }>;
}) {
  const params = await searchParams;
  const ticker = first(params.ticker) ?? "";
  const tape = await fetchWatchlist(ticker);
  return <WatchlistView tape={tape} selected={ticker} />;
}

function first(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

import { PageHeader } from "@/components/PageHeader";

export default function WatchlistPage() {
  return (
    <PageHeader title="Watchlist">
      Names you track, delayed quotes, sparklines, and a TradingView chart. Seed tickers
      are already in Postgres; quotes arrive with Day 2 / Day 18.
    </PageHeader>
  );
}

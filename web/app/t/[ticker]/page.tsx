import { TickerView } from "@/components/TickerView";
import { fetchTicker } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function TickerPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  const symbol = decodeURIComponent(ticker).toUpperCase();
  const result = await fetchTicker(symbol);
  if (!result.ok) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{symbol}</h1>
        <p className="text-sm text-mute">
          {result.status === 404
            ? `${symbol} is not stored. Add it to the Watchlist to hydrate bars and SEC facts.`
            : "Ticker API unreachable. Start uvicorn, then refresh."}
        </p>
      </div>
    );
  }
  return <TickerView tape={result.data} />;
}

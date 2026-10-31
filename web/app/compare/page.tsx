import { CompareView } from "@/components/CompareView";
import { fetchCompare } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ tickers?: string | string[]; with?: string | string[] }>;
}) {
  const params = await searchParams;
  const tickers = [...split(params.tickers), ...split(params.with)].filter(
    (item, index, all) => all.indexOf(item) === index,
  );
  const query = tickers.join(",");
  const result = tickers.length >= 2 ? await fetchCompare(tickers) : null;
  return <CompareView tape={result?.ok ? result.data : null} query={query} />;
}

function split(value: string | string[] | undefined): string[] {
  const raw = Array.isArray(value) ? value.join(",") : (value ?? "");
  return raw
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

import { ValuationView } from "@/components/ValuationView";
import { fetchValuation } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ValuationPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string | string[];
    industry?: string | string[];
    sort?: string | string[];
    min_rev?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const q = first(params.q) ?? "";
  const industry = first(params.industry) ?? "";
  const sort = first(params.sort) ?? "pctile";
  const minRev = first(params.min_rev) ?? "";
  const tape = await fetchValuation({ q, industry, sort, minRev });
  return <ValuationView tape={tape} query={{ q, industry, sort, min_rev: minRev }} />;
}

function first(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

import { OpportunitiesView } from "@/components/OpportunitiesView";
import { fetchOpportunities } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OpportunitiesPage({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string | string[]; as_of?: string | string[] }>;
}) {
  const params = await searchParams;
  const sort = first(params.sort) ?? "rank";
  const asOf = first(params.as_of) ?? "";
  const tape = await fetchOpportunities({ sort, asOf });
  return <OpportunitiesView tape={tape} query={{ sort, asOf }} />;
}

function first(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

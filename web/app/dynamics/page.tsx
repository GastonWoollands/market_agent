import { DynamicsView } from "@/components/DynamicsView";
import { fetchDynamics } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DynamicsPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string | string[]; lead?: string | string[]; lag?: string | string[] }>;
}) {
  const params = await searchParams;
  const asOf = first(params.as_of);
  const tape = await fetchDynamics({
    asOf,
    lead: first(params.lead),
    lag: first(params.lag),
  });
  return <DynamicsView tape={tape} asOf={asOf} />;
}

function first(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

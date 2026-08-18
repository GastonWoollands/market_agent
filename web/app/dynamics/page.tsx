import { DynamicsView } from "@/components/DynamicsView";
import { fetchDynamics } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function DynamicsPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = params.as_of;
  const asOf = Array.isArray(raw) ? raw[0] : raw;
  const tape = await fetchDynamics(asOf);
  return <DynamicsView tape={tape} />;
}

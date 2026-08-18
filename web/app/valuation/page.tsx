import { ValuationView } from "@/components/ValuationView";
import { fetchValuation } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ValuationPage() {
  const tape = await fetchValuation();
  return <ValuationView tape={tape} />;
}

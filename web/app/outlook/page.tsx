import { OutlookView } from "@/components/OutlookView";
import { fetchOutlook } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OutlookPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = params.as_of;
  const asOf = Array.isArray(raw) ? raw[0] : raw;
  const tape = await fetchOutlook(asOf);
  return <OutlookView tape={tape} />;
}

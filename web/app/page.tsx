import { LiveTapeView } from "@/components/LiveTape";
import { fetchLive } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function LivePage({
  searchParams,
}: {
  searchParams: Promise<{ lever?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = params.lever;
  const lever = (Array.isArray(raw) ? raw[0] : raw) || "DGS10";
  const tape = await fetchLive(lever);
  return <LiveTapeView tape={tape} />;
}

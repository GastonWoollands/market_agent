import { LiveTapeView } from "@/components/LiveTape";
import { fetchLive } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function LivePage() {
  const tape = await fetchLive();
  return <LiveTapeView tape={tape} />;
}

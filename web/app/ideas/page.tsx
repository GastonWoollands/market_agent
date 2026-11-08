import { IdeasView } from "@/components/IdeasView";
import { fetchIdeas } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function IdeasPage() {
  const tape = await fetchIdeas();
  return <IdeasView tape={tape} />;
}

import demoData from "@/lib/demo-data.json";
import RequestDetailClient from "./RequestDetailClient";

/**
 * A static export has to know every dynamic route at build time. The demo holds
 * exactly one request, so its id comes straight from the recorded data rather
 * than being hardcoded here.
 */
export function generateStaticParams() {
  return [{ id: (demoData as { request: { id: string } }).request.id }];
}

export default function RequestDetailPage() {
  return <RequestDetailClient />;
}

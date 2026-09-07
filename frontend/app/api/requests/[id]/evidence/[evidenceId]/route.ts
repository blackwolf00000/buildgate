import { NextResponse } from "next/server";
import { DEMO } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

/** Resolves an evidence reference to the real chunk text it cites. */
export async function GET(
  _req: Request,
  { params }: { params: { evidenceId: string } }
) {
  const id = decodeURIComponent(params.evidenceId);
  const chunk = DEMO.chunks.find((c) => c.evidence_id === id);
  if (!chunk) {
    return NextResponse.json(
      { detail: "Evidence not found for this request" },
      { status: 404 }
    );
  }
  return NextResponse.json(chunk);
}

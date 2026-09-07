import { NextResponse } from "next/server";
import { getRun, serializeRun } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { runId: string } }
) {
  const run = getRun(params.runId);
  if (!run) {
    return NextResponse.json({ detail: "Review run not found" }, { status: 404 });
  }
  return NextResponse.json(serializeRun(run));
}

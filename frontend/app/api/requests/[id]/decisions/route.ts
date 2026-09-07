import { NextResponse } from "next/server";
import { decisionFor, latestRun, runIsComplete } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function GET() {
  const run = latestRun();
  // A decision only exists once the board has finished, as in the real backend.
  if (!run || !runIsComplete(run)) return NextResponse.json([]);
  return NextResponse.json([decisionFor(run)]);
}

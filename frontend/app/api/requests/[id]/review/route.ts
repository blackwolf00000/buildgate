import { NextResponse } from "next/server";
import { serializeRun, startRun } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

/** Starts a simulated run. Agents complete on a timer, so the polling UI
 *  behaves exactly as it does against the real backend. */
export async function POST() {
  return NextResponse.json(serializeRun(startRun()), { status: 202 });
}

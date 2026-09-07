import { NextResponse } from "next/server";
import { latestRun, serializeRun } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function GET() {
  const run = latestRun();
  return NextResponse.json(run ? [serializeRun(run)] : []);
}

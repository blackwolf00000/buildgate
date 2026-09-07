import { NextResponse } from "next/server";
import { DEMO, requestStatus } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json([{ ...DEMO.request, status: requestStatus() }]);
}

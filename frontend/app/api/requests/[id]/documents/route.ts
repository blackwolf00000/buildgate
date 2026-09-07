import { NextResponse } from "next/server";
import { DEMO } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(DEMO.documents);
}

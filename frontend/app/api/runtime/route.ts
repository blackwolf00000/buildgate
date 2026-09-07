import { NextResponse } from "next/server";
import { DEMO } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

/** Reports demo mode honestly rather than claiming a live local runtime. */
export async function GET() {
  return NextResponse.json({
    mode: "demo",
    database: { connected: true },
    ollama: { reachable: false, host: "not available in the hosted demo" },
    embedding: {
      configured_provider: "none",
      active_provider: "recorded",
      model: DEMO.model_name,
    },
    outbound_http: { allowed: 0, rejected: 0, allowed_hosts: [] },
    storage_dir: "n/a",
  });
}

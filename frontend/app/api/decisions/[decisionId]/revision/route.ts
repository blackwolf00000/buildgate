import { NextResponse } from "next/server";
import { decisionFor, findRunByDecisionId } from "@/lib/demo-store";

export const dynamic = "force-dynamic";

export async function POST(
  req: Request,
  { params }: { params: { decisionId: string } }
) {
  const run = findRunByDecisionId(params.decisionId);
  if (!run) {
    return NextResponse.json({ detail: "Decision not found" }, { status: 404 });
  }
  if (run.resolution.accepted_at || run.resolution.overridden_at) {
    return NextResponse.json(
      { detail: "This decision has already been resolved" },
      { status: 409 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const actor = String(body.actor ?? "").trim();
  if (!actor) {
    return NextResponse.json({ detail: "actor is required" }, { status: 422 });
  }

  run.resolution.accepted_at = new Date().toISOString();
  run.resolution.accepted_by = actor;

  return NextResponse.json(decisionFor(run));
}

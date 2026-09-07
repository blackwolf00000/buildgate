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
  // Mirrors the backend: every field mandatory, blank counts as missing, and
  // accepted risks must be explicitly ticked. Enforced here, not merely
  // disabled in the form.
  const actor = String(body.actor ?? "").trim();
  const reason = String(body.override_reason ?? "").trim();
  const riskOwner = String(body.override_risk_owner ?? "").trim();
  const approver = String(body.override_approver_name ?? "").trim();
  const risks = (Array.isArray(body.override_accepted_risks)
    ? body.override_accepted_risks
    : []
  )
    .map((r: unknown) => String(r ?? "").trim())
    .filter(Boolean);

  const missing: string[] = [];
  if (!actor) missing.push("actor");
  if (!reason) missing.push("override_reason");
  if (!riskOwner) missing.push("override_risk_owner");
  if (!approver) missing.push("override_approver_name");
  if (!risks.length) missing.push("override_accepted_risks");
  if (missing.length) {
    return NextResponse.json(
      { detail: "Override requires every field: " + missing.sort().join(", ") },
      { status: 422 }
    );
  }

  run.resolution.overridden_at = new Date().toISOString();
  run.resolution.accepted_by = actor;
  run.resolution.override_reason = reason;
  run.resolution.override_risk_owner = riskOwner;
  run.resolution.override_approver_name = approver;
  run.resolution.override_accepted_risks = risks;

  return NextResponse.json(decisionFor(run));
}

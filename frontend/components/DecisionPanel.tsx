"use client";

import { useState } from "react";
import { Decision, api } from "@/lib/api";

const DECISION_STYLES: Record<string, string> = {
  APPROVED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  REVISE: "border-amber-200 bg-amber-50 text-amber-900",
  BLOCKED: "border-red-200 bg-red-50 text-red-800",
};

export function DecisionPanel({
  decision,
  onChanged,
}: {
  decision: Decision;
  onChanged: () => void;
}) {
  const resolved = decision.accepted_at !== null || decision.overridden_at !== null;

  return (
    <div className="space-y-4">
      <div className={`rounded-lg border p-4 ${DECISION_STYLES[decision.status] || "border-slate-200 bg-white"}`}>
        <div className="flex items-center justify-between">
          <span className="text-lg font-semibold">{decision.status}</span>
          <span className="text-xs opacity-80">
            policy {decision.policy_version} · {decision.model_name}
          </span>
        </div>

        {!decision.review_complete && (
          <p className="mt-2 text-sm font-medium">
            This review was incomplete — at least one reviewer did not return, so it can
            never approve.
          </p>
        )}

        <div className="mt-3">
          <div className="text-xs uppercase tracking-wide opacity-70">Rules that fired</div>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {decision.rule_ids.map((ruleId, index) => (
              <li
                key={ruleId}
                className="rounded border border-current/20 bg-white/60 px-1.5 py-0.5 font-mono text-[11px]"
                title={index === 0 ? "Deciding rule" : "Fired but outranked — recorded, not discarded"}
              >
                {index === 0 ? "▶ " : ""}
                {ruleId}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {resolved ? <ResolvedNotice decision={decision} /> : <DecisionActions decision={decision} onChanged={onChanged} />}
    </div>
  );
}

function ResolvedNotice({ decision }: { decision: Decision }) {
  if (decision.overridden_at) {
    return (
      <div className="rounded-lg border border-purple-200 bg-purple-50 p-4 text-sm text-purple-900">
        <div className="font-medium">
          Overridden on {new Date(decision.overridden_at).toLocaleString()}
        </div>
        <dl className="mt-2 space-y-1">
          <Row label="Reason" value={decision.override_reason} />
          <Row label="Risk owner" value={decision.override_risk_owner} />
          <Row label="Approver" value={decision.override_approver_name} />
          <Row
            label="Accepted risks"
            value={(decision.override_accepted_risks || []).join("; ")}
          />
        </dl>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
      Accepted by <span className="font-medium">{decision.accepted_by}</span> on{" "}
      {new Date(decision.accepted_at!).toLocaleString()}.
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex gap-2">
      <dt className="w-28 shrink-0 text-xs uppercase tracking-wide opacity-70">{label}</dt>
      <dd className="flex-1">{value || "—"}</dd>
    </div>
  );
}

function DecisionActions({
  decision,
  onChanged,
}: {
  decision: Decision;
  onChanged: () => void;
}) {
  const [actor, setActor] = useState("");
  const [note, setNote] = useState("");
  const [showOverride, setShowOverride] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Override fields. Every one is mandatory, and the server rejects a blank
  // just as hard as an absent key -- the button stays disabled to match, but
  // the server is the actual control.
  const [reason, setReason] = useState("");
  const [riskOwner, setRiskOwner] = useState("");
  const [approver, setApprover] = useState("");
  const [risks, setRisks] = useState<string[]>([]);

  const suggestedRisks = [
    "Proceeding without the evidence the reviewers asked for",
    "Accepting the blockers raised in this review",
    "Delivery may slip against the stated deadline",
  ];

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  const overrideReady =
    actor.trim() !== "" &&
    reason.trim() !== "" &&
    riskOwner.trim() !== "" &&
    approver.trim() !== "" &&
    risks.length > 0;

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div>
        <label className="block text-xs uppercase tracking-wide text-slate-400">
          Your name (recorded in the audit trail)
        </label>
        <input
          value={actor}
          onChange={(e) => setActor(e.target.value)}
          placeholder="e.g. Marcus Webb"
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy || actor.trim() === ""}
          onClick={() => run(() => api.acceptDecision(decision.id, actor.trim()))}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Accept recommendation
        </button>
        <button
          type="button"
          disabled={busy || actor.trim() === ""}
          onClick={() => run(() => api.requestRevision(decision.id, actor.trim(), note))}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
        >
          Send for revision
        </button>
        <button
          type="button"
          onClick={() => setShowOverride((v) => !v)}
          className="rounded-md border border-purple-300 px-4 py-2 text-sm font-medium text-purple-800 hover:bg-purple-50"
        >
          {showOverride ? "Cancel override" : "Override…"}
        </button>
      </div>

      <div>
        <label className="block text-xs uppercase tracking-wide text-slate-400">
          Note (optional, sent with a revision request)
        </label>
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
      </div>

      {showOverride && (
        <div className="space-y-3 rounded-md border border-purple-200 bg-purple-50/50 p-4">
          <p className="text-sm text-purple-900">
            An override records that a named human went against the recommendation. Every
            field below is required and enforced by the server.
          </p>

          <Labelled label="Why are you overriding?">
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
          </Labelled>

          <Labelled label="Risk owner">
            <input
              value={riskOwner}
              onChange={(e) => setRiskOwner(e.target.value)}
              placeholder="Who owns the consequences?"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
          </Labelled>

          <Labelled label="Approver name">
            <input
              value={approver}
              onChange={(e) => setApprover(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
          </Labelled>

          <Labelled label="Accepted risks — tick each one you are accepting">
            <div className="space-y-1">
              {suggestedRisks.map((risk) => (
                <label key={risk} className="flex items-start gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={risks.includes(risk)}
                    onChange={(e) =>
                      setRisks((prev) =>
                        e.target.checked ? [...prev, risk] : prev.filter((r) => r !== risk)
                      )
                    }
                    className="mt-1"
                  />
                  <span>{risk}</span>
                </label>
              ))}
            </div>
          </Labelled>

          <button
            type="button"
            disabled={busy || !overrideReady}
            onClick={() =>
              run(() =>
                api.overrideDecision(decision.id, {
                  actor: actor.trim(),
                  override_reason: reason.trim(),
                  override_risk_owner: riskOwner.trim(),
                  override_approver_name: approver.trim(),
                  override_accepted_risks: risks,
                })
              )
            }
            className="rounded-md bg-purple-700 px-4 py-2 text-sm font-medium text-white hover:bg-purple-600 disabled:opacity-50"
          >
            Record override
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

function Labelled({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-slate-400">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

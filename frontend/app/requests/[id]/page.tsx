"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, AuditEvent, BuildGateDocument, BuildGateRequest, Decision } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { DocumentUpload } from "@/components/DocumentUpload";
import { EvidenceSearch } from "@/components/EvidenceSearch";
import { ReviewPanel } from "@/components/ReviewPanel";
import { DecisionPanel } from "@/components/DecisionPanel";

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = params.id;

  const [request, setRequest] = useState<BuildGateRequest | null>(null);
  const [documents, setDocuments] = useState<BuildGateDocument[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [req, docs, auditTrail, decisionRows] = await Promise.all([
        api.getRequest(requestId),
        api.listDocuments(requestId),
        api.getAuditTrail(requestId),
        api.listDecisions(requestId),
      ]);
      setRequest(req);
      setDocuments(docs);
      setAudit(auditTrail);
      setDecisions(decisionRows);
    } catch (err) {
      setError(String(err));
    }
  }, [requestId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "PROCESSING" || d.status === "UPLOADED");
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(() => {
        api.listDocuments(requestId).then(setDocuments).catch(() => {});
      }, 2000);
    }
    if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [documents, requestId]);

  if (error) {
    return <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>;
  }

  if (!request) {
    return <p className="text-sm text-slate-500">Loading...</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold text-slate-900">{request.title}</h1>
          <StatusBadge status={request.status} />
        </div>
        <p className="mt-2 text-sm text-slate-600">{request.description}</p>
      </div>

      <div className="grid grid-cols-2 gap-6 rounded-lg border border-slate-200 bg-white p-4 text-sm sm:grid-cols-3">
        <Field label="Requester" value={request.requester} />
        <Field label="Department" value={request.department} />
        <Field label="Priority" value={request.priority} />
        <Field
          label="Deadline"
          value={`${request.requested_deadline}${request.deadline_is_fixed ? " (fixed)" : " (flexible)"}`}
        />
        <Field label="Target users" value={request.target_users} />
        <Field label="Expected outcome" value={request.expected_outcome} />
      </div>

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-900">Business reason</h2>
        <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
          {request.business_reason}
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-900">Documents</h2>
        <DocumentUpload requestId={requestId} documents={documents} onUploaded={loadAll} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-900">Review board</h2>
        <ReviewPanel requestId={requestId} onRunComplete={loadAll} />
      </section>

      {decisions.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-medium text-slate-900">Decision</h2>
          <DecisionPanel decision={decisions[0]} onChanged={loadAll} />
          {decisions.length > 1 && (
            <p className="mt-2 text-xs text-slate-500">
              {decisions.length - 1} earlier decision
              {decisions.length > 2 ? "s are" : " is"} retained from previous runs and never
              overwritten.
            </p>
          )}
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-900">Evidence search</h2>
        <EvidenceSearch requestId={requestId} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium text-slate-900">Audit trail</h2>
        {audit.length === 0 ? (
          <p className="text-sm text-slate-500">No audit events yet.</p>
        ) : (
          <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white text-sm">
            {audit.map((event) => (
              <li key={event.id} className="px-4 py-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-800">
                    {event.event_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs text-slate-500">
                    {event.actor} · {new Date(event.created_at).toLocaleString()}
                  </span>
                </div>
                <AuditDetail event={event} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * Surfaces the parts of an audit payload that explain an outcome -- the rules
 * that fired, the policy and model behind them, and who owned an override --
 * so the trail can be read without going to the database.
 */
function AuditDetail({ event }: { event: AuditEvent }) {
  const payload = event.payload;
  if (!payload) return null;

  const bits: string[] = [];
  const deciding = payload.deciding_rule_id as string | undefined;
  const status = payload.status as string | undefined;
  const agent = payload.agent as string | undefined;
  const ruleIds = payload.rule_ids as string[] | undefined;
  const riskOwner = payload.override_risk_owner as string | undefined;
  const approver = payload.override_approver_name as string | undefined;
  const model = payload.model_name as string | undefined;
  const policy = payload.policy_version as string | undefined;

  if (agent) bits.push(agent);
  if (status) bits.push(status);
  if (deciding) bits.push(`deciding rule ${deciding}`);
  else if (ruleIds && ruleIds.length > 0) bits.push(ruleIds.join(", "));
  if (riskOwner) bits.push(`risk owner ${riskOwner}`);
  if (approver) bits.push(`approver ${approver}`);
  if (policy) bits.push(`policy ${policy}`);
  if (model) bits.push(model);

  if (bits.length === 0) return null;
  return <div className="mt-0.5 text-xs text-slate-500">{bits.join(" · ")}</div>;
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-slate-800">{value || "—"}</div>
    </div>
  );
}

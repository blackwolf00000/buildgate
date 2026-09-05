"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api, AuditEvent, BuildGateDocument, BuildGateRequest } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { DocumentUpload } from "@/components/DocumentUpload";
import { EvidenceSearch } from "@/components/EvidenceSearch";

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>();
  const requestId = params.id;

  const [request, setRequest] = useState<BuildGateRequest | null>(null);
  const [documents, setDocuments] = useState<BuildGateDocument[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const [req, docs, auditTrail] = await Promise.all([
        api.getRequest(requestId),
        api.listDocuments(requestId),
        api.getAuditTrail(requestId),
      ]);
      setRequest(req);
      setDocuments(docs);
      setAudit(auditTrail);
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
              <li key={event.id} className="flex items-center justify-between px-4 py-2">
                <span className="font-medium text-slate-800">{event.event_type.replace(/_/g, " ")}</span>
                <span className="text-xs text-slate-500">
                  {event.actor} · {new Date(event.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-slate-800">{value || "—"}</div>
    </div>
  );
}

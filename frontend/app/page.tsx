"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BuildGateRequest, RuntimeInfo } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function DashboardPage() {
  const [requests, setRequests] = useState<BuildGateRequest[]>([]);
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listRequests(), api.runtime()])
      .then(([reqs, rt]) => {
        setRequests(reqs);
        setRuntime(rt);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  const counts = requests.reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">
          Requests are challenged with local evidence before engineering capacity is committed.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      {runtime && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
          <span className="font-medium text-slate-800">Runtime:</span> mode {runtime.mode} · database{" "}
          {runtime.database.connected ? "connected" : "unreachable"} · embeddings via{" "}
          {runtime.embedding.active_provider} · outbound calls {runtime.outbound_http.allowed} allowed /{" "}
          {runtime.outbound_http.rejected} rejected
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {["DRAFT", "REVIEWING", "APPROVED", "BLOCKED"].map((status) => (
          <div key={status} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-2xl font-semibold text-slate-900">{counts[status] || 0}</div>
            <div className="text-xs text-slate-500">{status.replace(/_/g, " ")}</div>
          </div>
        ))}
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium text-slate-900">Recent requests</h2>
          <Link href="/requests" className="text-sm text-slate-600 hover:text-slate-900">
            View all
          </Link>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading...</p>
        ) : requests.length === 0 ? (
          <p className="text-sm text-slate-500">
            No requests yet. <Link href="/requests/new" className="underline">Create the first one</Link>.
          </p>
        ) : (
          <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
            {requests.slice(0, 8).map((r) => (
              <Link
                key={r.id}
                href={`/requests/${r.id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-slate-50"
              >
                <div>
                  <div className="font-medium text-slate-900">{r.title}</div>
                  <div className="text-xs text-slate-500">
                    {r.department || "No department"} · Deadline {r.requested_deadline}
                    {r.deadline_is_fixed ? " (fixed)" : ""}
                  </div>
                </div>
                <StatusBadge status={r.status} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

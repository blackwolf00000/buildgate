"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, BuildGateRequest } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function RequestsListPage() {
  const [requests, setRequests] = useState<BuildGateRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listRequests()
      .then(setRequests)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Requests</h1>
        <Link
          href="/requests/new"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          New Request
        </Link>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <p className="text-sm text-slate-500">Loading...</p>
      ) : requests.length === 0 ? (
        <p className="text-sm text-slate-500">No requests yet.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Title</th>
                <th className="px-4 py-2">Department</th>
                <th className="px-4 py-2">Deadline</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {requests.map((r) => (
                <tr key={r.id} className="cursor-pointer hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/requests/${r.id}`} className="font-medium text-slate-900 hover:underline">
                      {r.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{r.department || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {r.requested_deadline}
                    {r.deadline_is_fixed && (
                      <span className="ml-1 text-xs text-amber-600" title="This deadline is contractually or externally fixed.">
                        (fixed)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

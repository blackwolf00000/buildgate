"use client";

import { useState } from "react";
import { api, ResolvedEvidence } from "@/lib/api";

/**
 * A clickable evidence reference. Clicking resolves the id against the
 * request's own chunks and shows the exact local text behind the claim -- the
 * point being that a finding can always be checked against its source rather
 * than taken on trust.
 */
export function EvidenceRef({
  requestId,
  evidenceId,
}: {
  requestId: string;
  evidenceId: string;
}) {
  const [chunk, setChunk] = useState<ResolvedEvidence | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (chunk || loading) return;

    setLoading(true);
    setError(null);
    try {
      setChunk(await api.resolveEvidence(requestId, evidenceId));
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  // The full id is long and opaque; show the document stub and chunk index.
  const label = chunk
    ? `${chunk.document_filename} #${chunk.chunk_index}`
    : `${evidenceId.slice(0, 12)}…#${evidenceId.split("-CHUNK-")[1] ?? "?"}`;

  return (
    <span className="inline-block">
      <button
        type="button"
        onClick={toggle}
        title={evidenceId}
        className="rounded border border-slate-300 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-700 hover:border-slate-500 hover:bg-slate-100"
      >
        {open ? "▾" : "▸"} {label}
      </button>

      {open && (
        <span className="mt-1 block rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-700">
          {loading && <span className="text-slate-500">Resolving…</span>}
          {error && <span className="text-red-600">{error}</span>}
          {chunk && (
            <>
              <span className="mb-1 block font-mono text-[11px] text-slate-500">
                {chunk.evidence_id}
              </span>
              <span className="block whitespace-pre-wrap">{chunk.content}</span>
            </>
          )}
        </span>
      )}
    </span>
  );
}

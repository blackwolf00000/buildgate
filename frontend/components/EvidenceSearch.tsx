"use client";

import { useState } from "react";
import { api, EvidenceChunk } from "@/lib/api";

export function EvidenceSearch({ requestId }: { requestId: string }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EvidenceChunk[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const res = await api.searchEvidence(requestId, query);
      setResults(res);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          placeholder="Search the request's evidence, e.g. 'data classification'"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {results && (
        results.length === 0 ? (
          <p className="text-sm text-slate-500">No matching evidence found.</p>
        ) : (
          <ul className="space-y-3">
            {results.map((chunk) => (
              <li key={chunk.evidence_id} className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
                  <span className="font-mono">{chunk.evidence_id}</span>
                  <span>
                    {chunk.document_filename}
                    {chunk.score !== null && ` · score ${chunk.score.toFixed(3)}`}
                  </span>
                </div>
                <p className="text-sm text-slate-800">{chunk.content}</p>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}

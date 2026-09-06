"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AgentReview, AgentRun, Finding, ReviewRun, api } from "@/lib/api";
import { EvidenceRef } from "@/components/EvidenceRef";

const AGENT_STATE_STYLES: Record<string, string> = {
  PENDING: "bg-slate-100 text-slate-600",
  RUNNING: "bg-blue-100 text-blue-700",
  COMPLETE: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-red-100 text-red-700",
};

const SEVERITY_STYLES: Record<string, string> = {
  INFO: "bg-slate-100 text-slate-600",
  LOW: "bg-slate-100 text-slate-700",
  MEDIUM: "bg-amber-100 text-amber-800",
  HIGH: "bg-orange-100 text-orange-800",
  CRITICAL: "bg-red-100 text-red-700",
};

const AGENT_STATUS_STYLES: Record<string, string> = {
  PASS: "bg-emerald-100 text-emerald-700",
  WARNING: "bg-amber-100 text-amber-800",
  FAIL: "bg-orange-100 text-orange-800",
  BLOCK: "bg-red-100 text-red-700",
};

export function ReviewPanel({
  requestId,
  onRunComplete,
}: {
  requestId: string;
  onRunComplete: () => void;
}) {
  const [run, setRun] = useState<ReviewRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const notifiedRef = useRef<string | null>(null);

  const loadLatest = useCallback(async () => {
    try {
      const runs = await api.listReviewRuns(requestId);
      setRun(runs[0] ?? null);
    } catch (err) {
      setError(String(err));
    }
  }, [requestId]);

  useEffect(() => {
    loadLatest();
  }, [loadLatest]);

  // A single agent call takes minutes, so the run is polled rather than
  // awaited. Polling stops as soon as the run leaves an in-flight state.
  useEffect(() => {
    const inFlight = run && (run.status === "PENDING" || run.status === "RUNNING");

    if (inFlight && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        try {
          const fresh = await api.getReviewRun(run!.id);
          setRun(fresh);
        } catch {
          // transient poll failures are not worth surfacing mid-run
        }
      }, 3000);
    }

    if (!inFlight && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }

    // Tell the page once, when a run finishes, so it can pick up the decision.
    if (run && run.status === "COMPLETE" && notifiedRef.current !== run.id) {
      notifiedRef.current = run.id;
      onRunComplete();
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [run, onRunComplete]);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      setRun(await api.triggerReview(requestId));
    } catch (err) {
      setError(String(err));
    } finally {
      setStarting(false);
    }
  }

  const inFlight = run && (run.status === "PENDING" || run.status === "RUNNING");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4">
        <div className="text-sm">
          {run ? (
            <>
              <span className="font-medium text-slate-800">
                Run {run.status.toLowerCase()}
              </span>
              <span className="text-slate-500">
                {" "}
                · {run.model_name} · policy {run.policy_version}
              </span>
              {run.completed_at && (
                <span className="text-slate-500">
                  {" "}
                  · {new Date(run.completed_at).toLocaleString()}
                </span>
              )}
            </>
          ) : (
            <span className="text-slate-500">No review has been run yet.</span>
          )}
        </div>
        <button
          type="button"
          onClick={start}
          disabled={starting || !!inFlight}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {inFlight ? "Review running…" : starting ? "Starting…" : run ? "Re-run review" : "Run review"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {run && (
        <>
          <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white text-sm">
            {run.agent_runs.map((agentRun) => (
              <AgentRunRow key={agentRun.agent} agentRun={agentRun} />
            ))}
          </ul>

          {run.error && (
            <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {run.error}
            </p>
          )}

          {run.reviews.map((review) => (
            <AgentReviewCard key={review.id} review={review} requestId={requestId} />
          ))}
        </>
      )}
    </div>
  );
}

function AgentRunRow({ agentRun }: { agentRun: AgentRun }) {
  return (
    <li className="flex items-center justify-between px-4 py-2">
      <span className="font-medium text-slate-800">{agentRun.agent}</span>
      <span className="flex items-center gap-3 text-xs text-slate-500">
        {agentRun.latency_ms !== null && <span>{(agentRun.latency_ms / 1000).toFixed(1)}s</span>}
        {agentRun.attempts > 1 && <span>{agentRun.attempts} attempts</span>}
        {agentRun.error_class && <span className="text-red-600">{agentRun.error_class}</span>}
        <span
          className={`inline-flex rounded-full px-2 py-0.5 font-medium ${
            AGENT_STATE_STYLES[agentRun.state] || "bg-slate-100 text-slate-600"
          }`}
        >
          {agentRun.state}
        </span>
      </span>
    </li>
  );
}

function AgentReviewCard({ review, requestId }: { review: AgentReview; requestId: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-slate-900">{review.agent}</h3>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">
            score {review.score} · confidence {review.confidence.toFixed(2)}
          </span>
          <span
            className={`inline-flex rounded-full px-2 py-0.5 font-medium ${
              AGENT_STATUS_STYLES[review.status] || "bg-slate-100 text-slate-600"
            }`}
          >
            {review.status}
          </span>
        </div>
      </div>

      <p className="mt-2 text-sm text-slate-700">{review.summary}</p>

      {review.critical_information_missing && (
        <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          This reviewer flagged that information it needed was not present in the evidence.
        </p>
      )}

      {review.findings.length > 0 && (
        <ul className="mt-3 space-y-3">
          {review.findings.map((finding, index) => (
            <FindingRow
              key={`${review.id}-${index}`}
              finding={finding}
              requestId={requestId}
            />
          ))}
        </ul>
      )}

      <ListBlock label="Required actions" items={review.required_actions} />
      <ListBlock label="Open questions" items={review.questions} />
      <ListBlock label="Assumptions" items={review.assumptions} />
    </div>
  );
}

function FindingRow({ finding, requestId }: { finding: Finding; requestId: string }) {
  return (
    <li className="rounded-md border border-slate-200 p-3">
      <div className="flex items-start justify-between gap-3">
        <span className="text-sm font-medium text-slate-800">{finding.title}</span>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${
            SEVERITY_STYLES[finding.severity] || "bg-slate-100 text-slate-600"
          }`}
        >
          {finding.severity}
        </span>
      </div>

      <p className="mt-1 text-sm text-slate-600">{finding.description}</p>

      <div className="mt-2 flex flex-wrap items-start gap-1.5">
        {finding.evidence_ids.map((evidenceId) => (
          <EvidenceRef key={evidenceId} requestId={requestId} evidenceId={evidenceId} />
        ))}

        {finding.evidence_status === "MISSING" && (
          <span
            className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800"
            title={
              finding.stripped_evidence_ids.length > 0
                ? `Stripped unresolvable ids: ${finding.stripped_evidence_ids.join(", ")}`
                : "This finding cited no supporting evidence"
            }
          >
            evidence missing
            {finding.stripped_evidence_ids.length > 0 &&
              ` · ${finding.stripped_evidence_ids.length} fabricated id stripped`}
          </span>
        )}
      </div>
    </li>
  );
}

function ListBlock({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

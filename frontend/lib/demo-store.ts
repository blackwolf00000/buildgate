/**
 * The hosted demo's data layer.
 *
 * BuildGate's real backend needs Ollama, a pgvector Postgres, background jobs
 * that outlive a request, and ~100s per agent call. None of that is deployable
 * on Vercel's free plan, so this branch serves a *recording* of a real review
 * run -- captured from qwen2.5:3b against the seeded demo request -- through
 * the same API surface the UI already speaks.
 *
 * What is real here: the request, the documents, every chunk, every agent
 * finding and score, and the evidence ids. What is simulated: the passage of
 * time during a run. What is genuinely computed, not recorded: the decision,
 * which runs through the ported policy engine on every request.
 *
 * State is module-level and therefore per-instance and ephemeral. That is
 * acceptable for a demo and is stated in the UI; it is not a persistence layer.
 */
import demoData from "@/lib/demo-data.json";
import { evaluate, type AgentReviewInput, type SeverityValue } from "@/lib/decisionEngine";

export const DEMO = demoData as unknown as DemoData;

interface DemoFinding {
  category?: string;
  severity: SeverityValue;
  title: string;
  description: string;
  evidence_ids?: string[];
  stripped_evidence_ids?: string[];
  evidence_status?: "OK" | "MISSING";
}

interface DemoReview {
  id: string;
  agent: string;
  score: number;
  status: "PASS" | "WARNING" | "FAIL" | "BLOCK";
  confidence: number;
  summary: string;
  findings: DemoFinding[];
  questions: string[];
  required_actions: string[];
  assumptions: string[];
  critical_information_missing: boolean;
  deadline_assessment: string | null;
  created_at: string;
}

interface DemoData {
  request: Record<string, unknown> & { id: string; deadline_is_fixed: boolean };
  documents: Record<string, unknown>[];
  chunks: {
    evidence_id: string;
    document_id: string;
    document_filename: string;
    chunk_index: number;
    content: string;
  }[];
  model_name: string;
  policy_version: string;
  reviews: DemoReview[];
  audit: {
    id: string;
    event_type: string;
    actor: string;
    payload: Record<string, unknown> | null;
    created_at: string;
  }[];
}

export const EXPECTED_AGENTS = DEMO.reviews.map((r) => r.agent).sort();

/** Recorded per-agent latencies, compressed so a demo run takes ~14s rather
 *  than the ~12 minutes the real board takes on CPU. The ratio between agents
 *  is preserved so the progress still looks like a real run. */
const AGENT_SECONDS: Record<string, number> = {};
EXPECTED_AGENTS.forEach((agent, i) => {
  AGENT_SECONDS[agent] = 2 + i * 2;
});

type Resolution = {
  accepted_at?: string;
  accepted_by?: string;
  overridden_at?: string;
  override_reason?: string;
  override_risk_owner?: string;
  override_accepted_risks?: string[];
  override_approver_name?: string;
};

interface RunState {
  id: string;
  startedAt: number;
  resolution: Resolution;
}

// Per-instance and ephemeral by design; see the module docstring.
const runs = new Map<string, RunState>();
let latestRunId: string | null = null;

export function startRun(): RunState {
  const id = crypto.randomUUID();
  const state: RunState = { id, startedAt: Date.now(), resolution: {} };
  runs.set(id, state);
  latestRunId = id;
  return state;
}

export function getRun(id: string): RunState | undefined {
  return runs.get(id);
}

export function latestRun(): RunState | undefined {
  return latestRunId ? runs.get(latestRunId) : undefined;
}

export function findRunByDecisionId(decisionId: string): RunState | undefined {
  for (const state of runs.values()) {
    if (decisionIdFor(state) === decisionId) return state;
  }
  return undefined;
}

/** Stable per-run decision id, so accept/override can address it. */
export function decisionIdFor(state: RunState): string {
  return `decision-${state.id}`;
}

function elapsed(state: RunState): number {
  return (Date.now() - state.startedAt) / 1000;
}

/** Which agents have finished, derived from elapsed time. */
export function agentStates(state: RunState) {
  const secs = elapsed(state);
  let cumulative = 0;
  return EXPECTED_AGENTS.map((agent) => {
    const duration = AGENT_SECONDS[agent];
    const startsAt = cumulative;
    cumulative += duration;
    const done = secs >= cumulative;
    const running = !done && secs >= startsAt;
    return {
      agent,
      state: done ? "COMPLETE" : running ? "RUNNING" : "PENDING",
      error_class: null,
      latency_ms: done ? Math.round(duration * 1000) : null,
      attempts: done ? 1 : 0,
    };
  });
}

export function runIsComplete(state: RunState): boolean {
  return agentStates(state).every((a) => a.state === "COMPLETE");
}

export function completedReviews(state: RunState): DemoReview[] {
  const done = new Set(
    agentStates(state).filter((a) => a.state === "COMPLETE").map((a) => a.agent)
  );
  return DEMO.reviews.filter((r) => done.has(r.agent));
}

/** The decision is computed, never recorded. */
export function decisionFor(state: RunState) {
  const reviews: AgentReviewInput[] = completedReviews(state).map((r) => ({
    agent: r.agent,
    score: r.score,
    status: r.status,
    confidence: r.confidence,
    critical_information_missing: r.critical_information_missing,
    deadline_assessment: (r.deadline_assessment ?? null) as never,
    finding_severities: r.findings.map((f) => f.severity),
  }));

  const result = evaluate({
    reviews,
    expectedAgents: EXPECTED_AGENTS,
    deadlineIsFixed: DEMO.request.deadline_is_fixed,
  });

  return {
    id: decisionIdFor(state),
    review_run_id: state.id,
    request_id: DEMO.request.id,
    status: result.status,
    policy_version: DEMO.policy_version,
    model_name: DEMO.model_name,
    review_complete: result.review_complete,
    rule_ids: result.rule_ids,
    accepted_at: state.resolution.accepted_at ?? null,
    accepted_by: state.resolution.accepted_by ?? null,
    overridden_at: state.resolution.overridden_at ?? null,
    override_reason: state.resolution.override_reason ?? null,
    override_risk_owner: state.resolution.override_risk_owner ?? null,
    override_accepted_risks: state.resolution.override_accepted_risks ?? null,
    override_approver_name: state.resolution.override_approver_name ?? null,
    created_at: new Date(state.startedAt).toISOString(),
  };
}

export function serializeRun(state: RunState) {
  const agents = agentStates(state);
  const complete = agents.every((a) => a.state === "COMPLETE");
  return {
    id: state.id,
    request_id: DEMO.request.id,
    status: complete ? "COMPLETE" : "RUNNING",
    model_name: DEMO.model_name,
    policy_version: DEMO.policy_version,
    error: null,
    created_at: new Date(state.startedAt).toISOString(),
    completed_at: complete ? new Date().toISOString() : null,
    agent_runs: agents,
    reviews: completedReviews(state),
  };
}

export function requestStatus(): string {
  const state = latestRun();
  if (!state) return "DRAFT";
  if (state.resolution.overridden_at) return "OVERRIDDEN";
  if (state.resolution.accepted_at) {
    const d = decisionFor(state);
    return d.status === "APPROVED" ? "APPROVED" : d.status === "BLOCKED" ? "BLOCKED" : "REVISE";
  }
  return runIsComplete(state) ? "REVIEWING" : "REVIEWING";
}

export function auditEvents() {
  const events = [...DEMO.audit];
  const state = latestRun();
  if (!state) return events;

  const at = (offsetSeconds: number) =>
    new Date(state.startedAt + offsetSeconds * 1000).toISOString();

  events.push({
    id: `ev-start-${state.id}`,
    event_type: "REVIEW_STARTED",
    actor: "demo",
    payload: { review_run_id: state.id, model_name: DEMO.model_name },
    created_at: at(0),
  });

  let cumulative = 0;
  for (const agent of EXPECTED_AGENTS) {
    cumulative += AGENT_SECONDS[agent];
    const review = DEMO.reviews.find((r) => r.agent === agent);
    if (review && elapsed(state) >= cumulative) {
      events.push({
        id: `ev-agent-${agent}-${state.id}`,
        event_type: "AGENT_REVIEW_COMPLETED",
        actor: "demo",
        payload: { agent, status: review.status, score: review.score },
        created_at: at(cumulative),
      });
    }
  }

  if (runIsComplete(state)) {
    const d = decisionFor(state);
    events.push({
      id: `ev-decision-${state.id}`,
      event_type: "DECISION_CREATED",
      actor: "demo",
      payload: {
        status: d.status,
        deciding_rule_id: d.rule_ids[0],
        rule_ids: d.rule_ids,
        policy_version: d.policy_version,
        model_name: d.model_name,
      },
      created_at: at(cumulative),
    });
  }

  const r = state.resolution;
  if (r.accepted_at) {
    events.push({
      id: `ev-accepted-${state.id}`,
      event_type: "DECISION_ACCEPTED",
      actor: r.accepted_by ?? "unknown",
      payload: { decision_id: decisionIdFor(state) },
      created_at: r.accepted_at,
    });
  }
  if (r.overridden_at) {
    events.push({
      id: `ev-overridden-${state.id}`,
      event_type: "DECISION_OVERRIDDEN",
      actor: r.accepted_by ?? "unknown",
      payload: {
        override_risk_owner: r.override_risk_owner,
        override_approver_name: r.override_approver_name,
        override_accepted_risks: r.override_accepted_risks,
      },
      created_at: r.overridden_at,
    });
  }
  return events;
}

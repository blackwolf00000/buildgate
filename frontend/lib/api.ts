/**
 * Client for the static Hugging Face Space build.
 *
 * A Static Space serves files and runs no server, so the route handlers used by
 * the Vercel demo cannot exist here. Every call below runs in the browser
 * against `lib/demo-store`, which holds the recorded review run and computes
 * decisions through the ported policy engine.
 *
 * The shapes returned are identical to the FastAPI backend's, so the components
 * are unchanged from `main`.
 *
 * **One thing genuinely weakens here.** The real product enforces the override
 * rules server-side, deliberately, so that a caller bypassing the form still
 * cannot record an unaccountable decision. In a static build there is no server
 * to enforce anything: `overrideDecision` below applies the same checks, but
 * they are client-side and therefore advisory. The UI says so. If you want the
 * enforcement demonstrated honestly, use the `hosting` branch on Vercel, where
 * it runs in a route handler.
 */
import {
  DEMO,
  auditEvents,
  decisionFor,
  findRunByDecisionId,
  latestRun,
  requestStatus,
  runIsComplete,
  serializeRun,
  startRun,
  getRun,
} from "@/lib/demo-store";

export type RequestStatus =
  | "DRAFT"
  | "READY_FOR_REVIEW"
  | "REVIEWING"
  | "APPROVED"
  | "REVISE"
  | "BLOCKED"
  | "OVERRIDDEN";

export type DocumentStatus = "UPLOADED" | "PROCESSING" | "READY" | "PROCESSING_FAILED";
export type AgentRunState = "PENDING" | "RUNNING" | "COMPLETE" | "FAILED";
export type ReviewRunStatus = "PENDING" | "RUNNING" | "COMPLETE" | "FAILED";
export type EvidenceStatus = "OK" | "MISSING";
export type FindingSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AgentStatusValue = "PASS" | "WARNING" | "FAIL" | "BLOCK";
export type DecisionStatusValue = "APPROVED" | "REVISE" | "BLOCKED";

export interface BuildGateRequest {
  id: string;
  title: string;
  description: string;
  business_reason: string;
  requested_deadline: string;
  deadline_is_fixed: boolean;
  requester: string | null;
  department: string | null;
  expected_outcome: string | null;
  target_users: string | null;
  priority: string | null;
  notes: string | null;
  status: RequestStatus;
  created_at: string;
  updated_at: string;
}

export interface RequestCreateInput {
  title: string;
  description: string;
  business_reason: string;
  requested_deadline: string;
  deadline_is_fixed: boolean;
  requester?: string;
  department?: string;
  expected_outcome?: string;
  target_users?: string;
  priority?: string;
  notes?: string;
}

export interface BuildGateDocument {
  id: string;
  request_id: string;
  original_filename: string;
  extension: string;
  size_bytes: number;
  status: DocumentStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceChunk {
  evidence_id: string;
  document_id: string;
  document_filename: string;
  chunk_index: number;
  content: string;
  score: number | null;
}

export interface ResolvedEvidence {
  evidence_id: string;
  document_id: string;
  document_filename: string;
  chunk_index: number;
  content: string;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  actor: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface RuntimeInfo {
  mode: string;
  database: { connected: boolean };
  ollama: { reachable: boolean; host: string };
  embedding: { configured_provider: string; active_provider: string; model: string };
  outbound_http: { allowed: number; rejected: number; allowed_hosts: string[] };
  storage_dir: string;
}

export interface Finding {
  category?: string;
  severity: FindingSeverity;
  title: string;
  description: string;
  evidence_ids: string[];
  stripped_evidence_ids: string[];
  evidence_status: EvidenceStatus;
}

export interface AgentReview {
  id: string;
  agent: string;
  score: number;
  status: AgentStatusValue;
  confidence: number;
  summary: string;
  findings: Finding[];
  questions: string[];
  required_actions: string[];
  assumptions: string[];
  critical_information_missing: boolean;
  deadline_assessment: string | null;
  created_at: string;
}

export interface AgentRun {
  agent: string;
  state: AgentRunState;
  error_class: string | null;
  latency_ms: number | null;
  attempts: number;
}

export interface ReviewRun {
  id: string;
  request_id: string;
  status: ReviewRunStatus;
  model_name: string;
  policy_version: string;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  agent_runs: AgentRun[];
  reviews: AgentReview[];
}

export interface Decision {
  id: string;
  review_run_id: string;
  request_id: string;
  status: DecisionStatusValue;
  policy_version: string;
  model_name: string;
  review_complete: boolean;
  rule_ids: string[];
  accepted_at: string | null;
  accepted_by: string | null;
  overridden_at: string | null;
  override_reason: string | null;
  override_risk_owner: string | null;
  override_accepted_risks: string[] | null;
  override_approver_name: string | null;
  created_at: string;
}

export interface OverrideInput {
  actor: string;
  override_reason: string;
  override_risk_owner: string;
  override_approver_name: string;
  override_accepted_risks: string[];
}

/** Keeps every call asynchronous so the components are untouched. */
const ok = <T>(value: T): Promise<T> => Promise.resolve(value);

function fail(status: number, detail: string): never {
  throw new Error(`${status}: ${detail}`);
}

export const api = {
  runtime: () =>
    ok<RuntimeInfo>({
      mode: "demo-static",
      database: { connected: true },
      ollama: { reachable: false, host: "not available in a static demo" },
      embedding: {
        configured_provider: "none",
        active_provider: "recorded",
        model: DEMO.model_name,
      },
      outbound_http: { allowed: 0, rejected: 0, allowed_hosts: [] },
      storage_dir: "n/a",
    }),

  listRequests: () =>
    ok<BuildGateRequest[]>([
      { ...(DEMO.request as unknown as BuildGateRequest), status: requestStatus() as RequestStatus },
    ]),

  getRequest: (_id?: string) =>
    ok<BuildGateRequest>({
      ...(DEMO.request as unknown as BuildGateRequest),
      status: requestStatus() as RequestStatus,
    }),

  createRequest: (_input: RequestCreateInput): Promise<BuildGateRequest> =>
    fail(501, "Creating requests needs the real backend; this demo is read-only"),

  updateRequest: (_id?: string, _input?: Partial<RequestCreateInput>): Promise<BuildGateRequest> =>
    fail(501, "Editing requests needs the real backend; this demo is read-only"),

  getAuditTrail: (_id?: string) => ok<AuditEvent[]>(auditEvents() as AuditEvent[]),

  listDocuments: (_requestId?: string) => ok<BuildGateDocument[]>(DEMO.documents as unknown as BuildGateDocument[]),

  uploadDocument: (_requestId?: string, _file?: File): Promise<BuildGateDocument> =>
    fail(501, "Uploads need the real backend; this demo ships five fixed documents"),

  searchEvidence: (_requestId: string, query: string) => {
    // Keyword scoring: a static build has no embedding model, so this is not
    // semantic retrieval and the UI says so.
    const terms = query.toLowerCase().trim().split(/\s+/).filter((t) => t.length > 2);
    const scored = DEMO.chunks.map((chunk) => {
      const text = chunk.content.toLowerCase();
      const hits = terms.reduce((n, t) => n + (text.split(t).length - 1), 0);
      return { ...chunk, score: terms.length ? Math.min(hits / (terms.length * 3), 1) : 0 };
    });
    scored.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
    return ok<EvidenceChunk[]>(scored as EvidenceChunk[]);
  },

  triggerReview: (_requestId?: string) => ok<ReviewRun>(serializeRun(startRun()) as unknown as ReviewRun),

  getReviewRun: (runId: string) => {
    const run = getRun(runId);
    if (!run) fail(404, "Review run not found");
    return ok<ReviewRun>(serializeRun(run) as unknown as ReviewRun);
  },

  listReviewRuns: (_requestId?: string) => {
    const run = latestRun();
    return ok<ReviewRun[]>(run ? [serializeRun(run) as unknown as ReviewRun] : []);
  },

  resolveEvidence: (_requestId: string, evidenceId: string) => {
    const chunk = DEMO.chunks.find((c) => c.evidence_id === evidenceId);
    if (!chunk) fail(404, "Evidence not found for this request");
    return ok<ResolvedEvidence>(chunk);
  },

  listDecisions: (_requestId?: string) => {
    const run = latestRun();
    if (!run || !runIsComplete(run)) return ok<Decision[]>([]);
    return ok<Decision[]>([decisionFor(run) as unknown as Decision]);
  },

  acceptDecision: (decisionId: string, actor: string) => {
    const run = findRunByDecisionId(decisionId);
    if (!run) fail(404, "Decision not found");
    if (run.resolution.accepted_at || run.resolution.overridden_at) {
      fail(409, "This decision has already been resolved");
    }
    if (!actor.trim()) fail(422, "actor is required");
    run.resolution.accepted_at = new Date().toISOString();
    run.resolution.accepted_by = actor.trim();
    return ok<Decision>(decisionFor(run) as unknown as Decision);
  },

  requestRevision: (decisionId: string, actor: string, _note?: string | null) => {
    const run = findRunByDecisionId(decisionId);
    if (!run) fail(404, "Decision not found");
    if (run.resolution.accepted_at || run.resolution.overridden_at) {
      fail(409, "This decision has already been resolved");
    }
    if (!actor.trim()) fail(422, "actor is required");
    run.resolution.accepted_at = new Date().toISOString();
    run.resolution.accepted_by = actor.trim();
    return ok<Decision>(decisionFor(run) as unknown as Decision);
  },

  overrideDecision: (decisionId: string, input: OverrideInput) => {
    const run = findRunByDecisionId(decisionId);
    if (!run) fail(404, "Decision not found");
    if (run.resolution.accepted_at || run.resolution.overridden_at) {
      fail(409, "This decision has already been resolved");
    }

    // The same rules the backend applies -- but client-side, and therefore
    // advisory rather than enforcement. See the note at the top of this file.
    const risks = (input.override_accepted_risks || [])
      .map((r) => String(r ?? "").trim())
      .filter(Boolean);
    const missing: string[] = [];
    if (!input.actor?.trim()) missing.push("actor");
    if (!input.override_reason?.trim()) missing.push("override_reason");
    if (!input.override_risk_owner?.trim()) missing.push("override_risk_owner");
    if (!input.override_approver_name?.trim()) missing.push("override_approver_name");
    if (!risks.length) missing.push("override_accepted_risks");
    if (missing.length) {
      fail(422, `Override requires every field: ${missing.sort().join(", ")}`);
    }

    run.resolution.overridden_at = new Date().toISOString();
    run.resolution.accepted_by = input.actor.trim();
    run.resolution.override_reason = input.override_reason.trim();
    run.resolution.override_risk_owner = input.override_risk_owner.trim();
    run.resolution.override_approver_name = input.override_approver_name.trim();
    run.resolution.override_accepted_risks = risks;
    return ok<Decision>(decisionFor(run) as unknown as Decision);
  },
};

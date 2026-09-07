// An empty NEXT_PUBLIC_API_BASE_URL means "same origin", which is how the
// hosted demo runs: the Next.js route handlers under /app/api serve the same
// contract the FastAPI backend does. `??` rather than `||` so the empty string
// is honoured instead of falling back to localhost.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RequestStatus =
  | "DRAFT"
  | "READY_FOR_REVIEW"
  | "REVIEWING"
  | "APPROVED"
  | "REVISE"
  | "BLOCKED"
  | "OVERRIDDEN";

export type DocumentStatus = "UPLOADED" | "PROCESSING" | "READY" | "PROCESSING_FAILED";

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

export type AgentRunState = "PENDING" | "RUNNING" | "COMPLETE" | "FAILED";
export type ReviewRunStatus = "PENDING" | "RUNNING" | "COMPLETE" | "FAILED";
export type EvidenceStatus = "OK" | "MISSING";
export type FindingSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AgentStatusValue = "PASS" | "WARNING" | "FAIL" | "BLOCK";
export type DecisionStatusValue = "APPROVED" | "REVISE" | "BLOCKED";

export interface Finding {
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

export interface ResolvedEvidence {
  evidence_id: string;
  document_id: string;
  document_filename: string;
  chunk_index: number;
  content: string;
}

export interface OverrideInput {
  actor: string;
  override_reason: string;
  override_risk_owner: string;
  override_approver_name: string;
  override_accepted_risks: string[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore parse errors, fall back to statusText
    }
    throw new Error(`${res.status}: ${detail}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  runtime: () => request<RuntimeInfo>("/api/runtime"),

  listRequests: () => request<BuildGateRequest[]>("/api/requests"),
  getRequest: (id: string) => request<BuildGateRequest>(`/api/requests/${id}`),
  createRequest: (input: RequestCreateInput) =>
    request<BuildGateRequest>("/api/requests", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  updateRequest: (id: string, input: Partial<RequestCreateInput>) =>
    request<BuildGateRequest>(`/api/requests/${id}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  getAuditTrail: (id: string) => request<AuditEvent[]>(`/api/requests/${id}/audit`),

  listDocuments: (requestId: string) =>
    request<BuildGateDocument[]>(`/api/requests/${requestId}/documents`),
  uploadDocument: async (requestId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<BuildGateDocument>(`/api/requests/${requestId}/documents`, {
      method: "POST",
      body: form,
    });
  },

  searchEvidence: (requestId: string, query: string) =>
    request<EvidenceChunk[]>(
      `/api/requests/${requestId}/evidence-search?q=${encodeURIComponent(query)}`
    ),
  triggerReview: (requestId: string) =>
    request<ReviewRun>(`/api/requests/${requestId}/review`, { method: "POST" }),
  getReviewRun: (runId: string) => request<ReviewRun>(`/api/reviews/${runId}`),
  listReviewRuns: (requestId: string) =>
    request<ReviewRun[]>(`/api/requests/${requestId}/reviews`),
  resolveEvidence: (requestId: string, evidenceId: string) =>
    request<ResolvedEvidence>(
      `/api/requests/${requestId}/evidence/${encodeURIComponent(evidenceId)}`
    ),

  listDecisions: (requestId: string) =>
    request<Decision[]>(`/api/requests/${requestId}/decisions`),
  acceptDecision: (decisionId: string, actor: string) =>
    request<Decision>(`/api/decisions/${decisionId}/accept`, {
      method: "POST",
      body: JSON.stringify({ actor }),
    }),
  requestRevision: (decisionId: string, actor: string, note?: string) =>
    request<Decision>(`/api/decisions/${decisionId}/revision`, {
      method: "POST",
      body: JSON.stringify({ actor, note: note || null }),
    }),
  overrideDecision: (decisionId: string, input: OverrideInput) =>
    request<Decision>(`/api/decisions/${decisionId}/override`, {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

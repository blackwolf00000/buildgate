const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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
};

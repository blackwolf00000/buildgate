"use client";

import { useState } from "react";
import { RequestCreateInput } from "@/lib/api";

interface Props {
  onSubmit: (input: RequestCreateInput) => Promise<void>;
  submitLabel?: string;
}

const initialState: RequestCreateInput = {
  title: "",
  description: "",
  business_reason: "",
  requested_deadline: "",
  deadline_is_fixed: false,
  requester: "",
  department: "",
  expected_outcome: "",
  target_users: "",
  priority: "",
  notes: "",
};

export function RequestForm({ onSubmit, submitLabel = "Create Request" }: Props) {
  const [form, setForm] = useState<RequestCreateInput>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update<K extends keyof RequestCreateInput>(key: K, value: RequestCreateInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(form);
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500";
  const labelClass = "block text-sm font-medium text-slate-700";

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      <div>
        <label className={labelClass}>Title *</label>
        <input
          required
          className={inputClass}
          value={form.title}
          onChange={(e) => update("title", e.target.value)}
        />
      </div>

      <div>
        <label className={labelClass}>Description *</label>
        <textarea
          required
          rows={4}
          className={inputClass}
          value={form.description}
          onChange={(e) => update("description", e.target.value)}
        />
      </div>

      <div>
        <label className={labelClass}>Business reason *</label>
        <textarea
          required
          rows={3}
          className={inputClass}
          value={form.business_reason}
          onChange={(e) => update("business_reason", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Requested deadline *</label>
          <input
            required
            type="date"
            className={inputClass}
            value={form.requested_deadline}
            onChange={(e) => update("requested_deadline", e.target.value)}
          />
        </div>
        <div className="flex items-end pb-2">
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-1"
              checked={form.deadline_is_fixed}
              onChange={(e) => update("deadline_is_fixed", e.target.checked)}
            />
            <span>This deadline is contractually or externally fixed.</span>
          </label>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Requester</label>
          <input
            className={inputClass}
            value={form.requester}
            onChange={(e) => update("requester", e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>Department</label>
          <input
            className={inputClass}
            value={form.department}
            onChange={(e) => update("department", e.target.value)}
          />
        </div>
      </div>

      <div>
        <label className={labelClass}>Expected outcome</label>
        <textarea
          rows={2}
          className={inputClass}
          value={form.expected_outcome}
          onChange={(e) => update("expected_outcome", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className={labelClass}>Target users</label>
          <input
            className={inputClass}
            value={form.target_users}
            onChange={(e) => update("target_users", e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>Priority</label>
          <input
            className={inputClass}
            value={form.priority}
            onChange={(e) => update("priority", e.target.value)}
          />
        </div>
      </div>

      <div>
        <label className={labelClass}>Notes</label>
        <textarea
          rows={2}
          className={inputClass}
          value={form.notes}
          onChange={(e) => update("notes", e.target.value)}
        />
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
      >
        {submitting ? "Saving..." : submitLabel}
      </button>
    </form>
  );
}

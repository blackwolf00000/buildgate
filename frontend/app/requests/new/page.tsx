"use client";

import { useRouter } from "next/navigation";
import { api, RequestCreateInput } from "@/lib/api";
import { RequestForm } from "@/components/RequestForm";

export default function NewRequestPage() {
  const router = useRouter();

  async function handleSubmit(input: RequestCreateInput) {
    const created = await api.createRequest(input);
    router.push(`/requests/${created.id}`);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">New Request</h1>
      <RequestForm onSubmit={handleSubmit} />
    </div>
  );
}

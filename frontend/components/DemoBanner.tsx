"use client";

import { useEffect, useState } from "react";
import { api, RuntimeInfo } from "@/lib/api";

/**
 * States plainly what the hosted demo is and is not.
 *
 * BuildGate's whole argument is that it runs locally and never sends customer
 * context to a cloud model. A hosted demo cannot do that, so it says so rather
 * than quietly implying a live review is happening.
 */
export function DemoBanner() {
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);

  useEffect(() => {
    api.runtime().then(setRuntime).catch(() => {});
  }, []);

  if (!runtime || runtime.mode !== "demo") return null;

  return (
    <div className="border-b border-amber-200 bg-amber-50">
      <div className="mx-auto max-w-5xl px-4 py-2.5 text-xs text-amber-900">
        <span className="font-semibold">Hosted demo.</span>{" "}
        The reviewer output below is a <span className="font-medium">recording</span> of a real
        run against <code className="font-mono">{runtime.embedding.model}</code> on a local
        machine — no model runs here. The decision, its rules, and the override checks are
        computed live by the same policy code as the real product. Evidence search is keyword
        matching rather than embeddings. State resets when the server idles.
      </div>
    </div>
  );
}

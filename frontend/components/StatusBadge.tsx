const REQUEST_STYLES: Record<string, string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  READY_FOR_REVIEW: "bg-blue-100 text-blue-700",
  REVIEWING: "bg-amber-100 text-amber-700",
  APPROVED: "bg-emerald-100 text-emerald-700",
  REVISE: "bg-amber-100 text-amber-800",
  BLOCKED: "bg-red-100 text-red-700",
  OVERRIDDEN: "bg-purple-100 text-purple-700",
};

const DOCUMENT_STYLES: Record<string, string> = {
  UPLOADED: "bg-slate-100 text-slate-700",
  PROCESSING: "bg-blue-100 text-blue-700",
  READY: "bg-emerald-100 text-emerald-700",
  PROCESSING_FAILED: "bg-red-100 text-red-700",
};

export function StatusBadge({ status, kind = "request" }: { status: string; kind?: "request" | "document" }) {
  const styles = kind === "document" ? DOCUMENT_STYLES : REQUEST_STYLES;
  const className = styles[status] || "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${className}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

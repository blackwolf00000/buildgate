"use client";

import { useRef, useState } from "react";
import { api, BuildGateDocument } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

interface Props {
  requestId: string;
  documents: BuildGateDocument[];
  onUploaded: () => void;
}

export function DocumentUpload({ requestId, documents, onUploaded }: Props) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        await api.uploadDocument(requestId, file);
      }
      onUploaded();
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <input
          ref={inputRef}
          type="file"
          accept=".md,.txt"
          multiple
          disabled={uploading}
          onChange={(e) => handleFiles(e.target.files)}
          className="block text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-slate-700"
        />
        <p className="mt-1 text-xs text-slate-500">Accepted formats: .md, .txt</p>
        {uploading && <p className="mt-1 text-xs text-slate-500">Uploading...</p>}
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </div>

      {documents.length === 0 ? (
        <p className="text-sm text-slate-500">No documents uploaded yet.</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
          {documents.map((doc) => (
            <li key={doc.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="text-sm font-medium text-slate-900">{doc.original_filename}</div>
                {doc.status === "PROCESSING_FAILED" && doc.failure_reason && (
                  <div className="mt-0.5 text-xs text-red-600">{doc.failure_reason}</div>
                )}
                <div className="text-xs text-slate-500">{(doc.size_bytes / 1024).toFixed(1)} KB</div>
              </div>
              <StatusBadge status={doc.status} kind="document" />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function citationNumber(c: any, i: number): number {
  const raw = c.source_index ?? c.index ?? c.source_number ?? c.n;
  if (typeof raw === "number") return raw;
  const m = String(c.label ?? c.source ?? "").match(/\d+/);
  return m ? Number(m[0]) : i + 1;
}

export default function CitationDrawer({
  citation,
  index,
  sources,
  onClose,
}: {
  citation: any;
  index: number;
  sources: any[];
  onClose: () => void;
}) {
  const n = citationNumber(citation, index);
  const src = sources[n - 1];
  const chunkId = citation.chunk_id ?? src?.chunk_id ?? src?.id ?? citation.id;

  const { data } = useQuery({
    queryKey: ["chunk", chunkId],
    enabled: !!chunkId,
    queryFn: async () => (await api.get(`/chunks/${chunkId}`)).data,
  });

  const content = data?.content ?? src?.content ?? src?.text ?? null;

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-md space-y-3 overflow-y-auto bg-white p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Source {n}</h2>
          <button onClick={onClose} className="rounded border px-3 py-1">Close</button>
        </div>
        {data?.document && (
          <div className="rounded bg-gray-50 p-2 text-sm">
            <div className="font-medium">{data.document.filename}</div>
            <div className="text-gray-500">
              {data.document.source_type} · chunk #{data.chunk_index} · {data.token_count} tokens
            </div>
          </div>
        )}
        {content ? (
          <p className="whitespace-pre-wrap text-sm">{content}</p>
        ) : (
          <pre className="overflow-auto rounded bg-gray-50 p-2 text-xs">
            {JSON.stringify({ citation, source: src }, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
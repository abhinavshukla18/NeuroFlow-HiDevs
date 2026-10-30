"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

type Chunk = { id: string; chunk_index: number; content: string; token_count: number };
type Similar = {
  id: string;
  document_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  similarity: number;
};

export default function DocumentDrawer({
  doc,
  onClose,
}: {
  doc: { document_id: string; filename: string };
  onClose: () => void;
}) {
  const [similar, setSimilar] = useState<Similar[]>([]);
  const [source, setSource] = useState<string | null>(null);

  const { data: chunks = [] } = useQuery<Chunk[]>({
    queryKey: ["chunks", doc.document_id],
    queryFn: async () => (await api.get(`/documents/${doc.document_id}/chunks`)).data,
  });

  async function findSimilar(id: string) {
    setSource(id);
    const res = await api.get(`/chunks/${id}/similar`);
    setSimilar(res.data);
  }

  const score = new Map(similar.map((s) => [s.id, s.similarity]));
  const others = similar.filter((s) => s.document_id !== doc.document_id);

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-xl space-y-4 overflow-y-auto bg-white p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">{doc.filename}</h2>
          <button onClick={onClose} className="rounded border px-3 py-1">Close</button>
        </div>
        <p className="text-sm text-gray-500">{chunks.length} chunks</p>

        {chunks.map((c) => {
          const sim = score.get(c.id);
          return (
            <div
              key={c.id}
              className={`space-y-1 rounded border p-3 text-sm ${
                sim !== undefined
                  ? "border-yellow-400 bg-yellow-50"
                  : c.id === source
                  ? "border-blue-400 bg-blue-50"
                  : "bg-white"
              }`}
            >
              <div className="flex items-center justify-between text-xs text-gray-500">
                <span>
                  #{c.chunk_index} · {c.token_count} tokens
                  {sim !== undefined && <b className="ml-2 text-yellow-700">similarity {sim}</b>}
                </span>
                <button onClick={() => findSimilar(c.id)} className="text-blue-600 hover:underline">
                  Find similar chunks
                </button>
              </div>
              <p className="whitespace-pre-wrap">{c.content}</p>
            </div>
          );
        })}

        {others.length > 0 && (
          <div className="space-y-2">
            <h3 className="font-semibold">Similar chunks in other documents</h3>
            {others.map((s) => (
              <div key={s.id} className="rounded border border-yellow-400 bg-yellow-50 p-3 text-sm">
                <div className="text-xs text-gray-500">
                  {s.filename} · #{s.chunk_index} ·{" "}
                  <b className="text-yellow-700">similarity {s.similarity}</b>
                </div>
                <p className="whitespace-pre-wrap">{s.content}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
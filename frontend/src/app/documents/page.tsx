"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import DocumentDrawer from "./DocumentDrawer";

type Doc = {
  document_id: string;
  filename: string;
  source_type: string;
  status: string;
  chunk_count: number | null;
  created_at: string;
};

type Upload = { name: string; size: number; progress: number; error?: string };

const DONE = ["complete", "completed", "ready", "indexed", "done"];
const FAILED = ["failed", "error"];

const ICONS: Record<string, string> = {
  pdf: "📕", docx: "📘", csv: "📊", text: "📄", image: "🖼️", url: "🔗",
};

function Badge({ status }: { status: string }) {
  if (DONE.includes(status))
    return <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">{status}</span>;
  if (FAILED.includes(status))
    return <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">{status}</span>;
  return (
    <span className="inline-flex items-center gap-1.5 rounded bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
      <span className="h-2 w-2 animate-pulse rounded-full bg-blue-600" />
      {status}
    </span>
  );
}

export default function Documents() {
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [selected, setSelected] = useState<Doc | null>(null);

  const { data: docs = [] } = useQuery<Doc[]>({
    queryKey: ["documents"],
    queryFn: async () => (await api.get("/documents")).data,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((d) => !DONE.includes(d.status) && !FAILED.includes(d.status)) ? 3000 : false,
  });

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    setUploads((u) => [...u, ...list.map((f) => ({ name: f.name, size: f.size, progress: 0 }))]);
    await Promise.all(
      list.map(async (f) => {
        const form = new FormData();
        form.append("file", f);
        try {
          await api.post("/ingest", form, {
            onUploadProgress: (e) => {
              const p = e.total ? Math.round((e.loaded / e.total) * 100) : 0;
              setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, progress: p } : x)));
            },
          });
          setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, progress: 100 } : x)));
        } catch (err: any) {
          const msg = err?.response?.data?.detail ?? "Upload failed";
          setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, error: String(msg) } : x)));
        }
      })
    );
    qc.invalidateQueries({ queryKey: ["documents"] });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-bold">Documents</h1>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          uploadFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded border-2 border-dashed p-10 text-center ${
          dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-white"
        }`}
      >
        Drag and drop files here, or click to choose
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          onChange={(e) => e.target.files && uploadFiles(e.target.files)}
        />
      </div>

      {uploads.length > 0 && (
        <div className="space-y-2 rounded border bg-white p-3">
          {uploads.map((u, i) => (
            <div key={i} className="text-sm">
              <div className="flex justify-between">
                <span>
                  {ICONS[u.name.split(".").pop() === "pdf" ? "pdf" : "text"]} {u.name} (
                  {(u.size / 1024).toFixed(0)} KB)
                </span>
                <span className={u.error ? "text-red-600" : ""}>{u.error ?? `${u.progress}%`}</span>
              </div>
              <div className="h-1.5 rounded bg-gray-200">
                <div
                  className={`h-1.5 rounded ${u.error ? "bg-red-500" : "bg-blue-500"}`}
                  style={{ width: `${u.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <table className="w-full rounded border bg-white text-sm">
        <thead className="bg-gray-100 text-left">
          <tr>
            <th className="p-2">File</th>
            <th className="p-2">Type</th>
            <th className="p-2">Status</th>
            <th className="p-2">Chunks</th>
            <th className="p-2">Ingested</th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr
              key={d.document_id}
              onClick={() => setSelected(d)}
              className="cursor-pointer border-t hover:bg-gray-50"
            >
              <td className="p-2">
                {ICONS[d.source_type] ?? "📄"} {d.filename}
              </td>
              <td className="p-2">{d.source_type}</td>
              <td className="p-2">
                <Badge status={d.status} />
              </td>
              <td className="p-2">{d.chunk_count ?? "-"}</td>
              <td className="p-2">{new Date(d.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selected && <DocumentDrawer doc={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
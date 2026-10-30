"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import AnalyticsDrawer from "./AnalyticsDrawer";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type Pipeline = {
  id: string;
  name: string;
  description: string | null;
  version: number;
  status: string;
  run_count: number;
  avg_overall_score: string | null;
  last_run_at: string | null;
};

const TEMPLATE = JSON.stringify({ name: "my-pipeline", description: "" }, null, 2);

function scoreColor(score: number | null) {
  if (score === null) return "border-gray-300 bg-white";
  if (score > 0.8) return "border-green-400 bg-green-50";
  if (score >= 0.6) return "border-yellow-400 bg-yellow-50";
  return "border-red-400 bg-red-50";
}

export default function Pipelines() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(TEMPLATE);
  const [selected, setSelected] = useState<Pipeline | null>(null);

  const { data: pipelines = [], isLoading } = useQuery<Pipeline[]>({
    queryKey: ["pipelines"],
    queryFn: async () => (await api.get("/pipelines")).data,
  });

  const create = useMutation({
    mutationFn: async (body: unknown) => (await api.post("/pipelines", body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipelines"] });
      setOpen(false);
      setText(TEMPLATE);
      setErrors([]);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setErrors(detail.map((d: any) => `${(d.loc ?? []).join(".")}: ${d.msg}`));
      } else {
        setErrors([typeof detail === "string" ? detail : "Request failed"]);
      }
    },
  });

  function submit() {
    try {
      const parsed = JSON.parse(text);
      setErrors([]);
      create.mutate(parsed);
    } catch (e: any) {
      setErrors([`Invalid JSON: ${e.message}`]);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Pipelines</h1>
        <button onClick={() => setOpen(true)} className="rounded bg-blue-600 px-4 py-2 text-white">
          Create pipeline
        </button>
      </div>

      {isLoading && <p className="text-gray-500">Loading...</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {pipelines.map((p) => {
          const score = p.avg_overall_score !== null ? Number(p.avg_overall_score) : null;
          return (
            <div
              key={p.id}
              onClick={() => setSelected(p)}
              className={`cursor-pointer rounded border-2 p-4 ${scoreColor(score)}`}
            >
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">{p.name}</h2>
                <span className="text-xs text-gray-500">v{p.version}</span>
              </div>
              <p className="mt-1 line-clamp-2 text-sm text-gray-600">{p.description}</p>
              <div className="mt-3 flex justify-between text-sm">
                <span>{p.run_count} queries</span>
                <span className="font-medium">{score !== null ? score.toFixed(2) : "no score"}</span>
              </div>
            </div>
          );
        })}
      </div>      
      {selected && <AnalyticsDrawer pipeline={selected} onClose={() => setSelected(null)} />}

      {open && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-2xl space-y-3 rounded bg-white p-4">
            <h2 className="text-lg font-semibold">Create pipeline</h2>
            <div className="h-80 overflow-hidden rounded border">
              <Editor
                height="100%"
                defaultLanguage="json"
                value={text}
                onChange={(v) => setText(v ?? "")}
                options={{ minimap: { enabled: false }, fontSize: 13 }}
              />
            </div>
            {errors.length > 0 && (
              <ul className="space-y-1 rounded bg-red-50 p-2 text-sm text-red-700">
                {errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setOpen(false)} className="rounded border px-4 py-2">
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={create.isPending}
                className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {create.isPending ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, API_URL, withToken } from "@/lib/api";

const METRICS = ["faithfulness", "answer_relevance", "context_precision", "context_recall"] as const;
type Metric = (typeof METRICS)[number];

type Item = {
  id: string;
  run_id: string;
  query: string;
  generation: string | null;
  pipeline_id: string;
  pipeline_name: string;
  overall_score: number | null;
  evaluated_at: string;
} & Record<Metric, number | null>;

const color = (v: number | null) =>
  v === null ? "bg-gray-300" : v > 0.8 ? "bg-green-500" : v >= 0.6 ? "bg-yellow-500" : "bg-red-500";

export default function Evaluations() {
  const [live, setLive] = useState<Item[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pipeline, setPipeline] = useState("");
  const [metric, setMetric] = useState<Metric | "">("");
  const [below, setBelow] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const { data: initial = [] } = useQuery<Item[]>({
    queryKey: ["evaluations"],
    queryFn: async () => (await api.get("/evaluations")).data,
  });

  useEffect(() => {
    const es = new EventSource(withToken(`${API_URL}/evaluations/stream`));
    es.onmessage = (e) => setLive((prev) => [JSON.parse(e.data), ...prev]);
    return () => es.close();
  }, []);

  const all = useMemo(() => {
    const seen = new Set<string>();
    return [...live, ...initial].filter((i) => (seen.has(i.id) ? false : seen.add(i.id)));
  }, [live, initial]);

  const pipelines = useMemo(
    () => Array.from(new Map(all.map((i) => [i.pipeline_id, i.pipeline_name])).entries()),
    [all]
  );

  const shown = all.filter((i) => {
    if (pipeline && i.pipeline_id !== pipeline) return false;
    if (metric && below !== "" && !((i[metric] ?? 1) < Number(below))) return false;
    const day = i.evaluated_at.slice(0, 10);
    if (from && day < from) return false;
    if (to && day > to) return false;
    return true;
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold">Evaluation Feed</h1>

      <div className="flex flex-wrap gap-2 rounded border bg-white p-3 text-sm">
        <select className="rounded border p-1" value={pipeline} onChange={(e) => setPipeline(e.target.value)}>
          <option value="">All pipelines</option>
          {pipelines.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <select className="rounded border p-1" value={metric} onChange={(e) => setMetric(e.target.value as Metric | "")}>
          <option value="">Metric...</option>
          {METRICS.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <input
          className="w-24 rounded border p-1"
          placeholder="below e.g. 0.7"
          value={below}
          onChange={(e) => setBelow(e.target.value)}
        />
        <input type="date" className="rounded border p-1" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className="rounded border p-1" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>

      {shown.length === 0 && <p className="text-gray-500">No evaluations yet.</p>}

      {shown.map((i) => (
        <div
          key={i.id}
          onClick={() => setExpanded(expanded === i.id ? null : i.id)}
          className="cursor-pointer space-y-2 rounded border bg-white p-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{i.pipeline_name}</span>
            <span className={`rounded px-2 py-0.5 text-sm text-white ${color(i.overall_score)}`}>
              {i.overall_score?.toFixed(2) ?? "-"}
            </span>
          </div>
          <p className={expanded === i.id ? "" : "line-clamp-1"}>{i.query}</p>
          <div className="grid grid-cols-2 gap-2">
            {METRICS.map((m) => (
              <div key={m} className="text-xs">
                <div className="flex justify-between">
                  <span>{m.replace("_", " ")}</span>
                  <span>{i[m]?.toFixed(2) ?? "-"}</span>
                </div>
                <div className="h-1.5 rounded bg-gray-200">
                  <div className={`h-1.5 rounded ${color(i[m])}`} style={{ width: `${(i[m] ?? 0) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="text-xs text-gray-500">{new Date(i.evaluated_at).toLocaleString()}</div>
          {expanded === i.id && (
            <div className="whitespace-pre-wrap rounded bg-gray-50 p-2 text-sm">{i.generation}</div>
          )}
        </div>
      ))}
    </div>
  );
}
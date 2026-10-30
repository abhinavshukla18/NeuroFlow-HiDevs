"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, PolarAngleAxis, PolarGrid,
  PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Legend, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/lib/api";

type Pct = { p50: number | null; p95: number | null; p99: number | null };
type Analytics = {
  completed_runs: number;
  retrieval_latency_ms: Pct;
  total_latency_ms: Pct;
  avg_evaluation_scores: Record<string, number | null>;
  cost_per_query_usd: number | null;
  queries_per_day: { date: string; queries: number }[];
};
type Run = { run_id: string; query: string; status: string; created_at: string; model_used: string | null };

export default function AnalyticsDrawer({
  pipeline,
  onClose,
}: {
  pipeline: { id: string; name: string };
  onClose: () => void;
}) {
  const { data } = useQuery<Analytics>({
    queryKey: ["analytics", pipeline.id],
    queryFn: async () => (await api.get(`/pipelines/${pipeline.id}/analytics`)).data,
  });
  const { data: runs } = useQuery<{ items: Run[] }>({
    queryKey: ["runs", pipeline.id],
    queryFn: async () => (await api.get(`/pipelines/${pipeline.id}/runs?page_size=100`)).data,
  });

  const latency = data
    ? (["p50", "p95", "p99"] as const).map((k) => ({
        name: k.toUpperCase(),
        retrieval: data.retrieval_latency_ms[k] ?? 0,
        total: data.total_latency_ms[k] ?? 0,
      }))
    : [];

  const cost = data
    ? data.queries_per_day.map((d) => ({
        date: d.date.slice(5),
        cost: +(d.queries * (data.cost_per_query_usd ?? 0)).toFixed(6),
      }))
    : [];

  const radar = data
    ? Object.entries(data.avg_evaluation_scores)
        .filter(([k]) => k !== "overall_score")
        .map(([k, v]) => ({ metric: k.replace("_", " "), score: v ?? 0 }))
    : [];

  const failed = (runs?.items ?? []).filter(
    (r) => !["complete", "queued", "running"].includes(r.status)
  );

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="h-full w-full max-w-xl space-y-6 overflow-y-auto bg-white p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold">{pipeline.name}</h2>
          <button onClick={onClose} className="rounded border px-3 py-1">Close</button>
        </div>

        {!data && <p className="text-gray-500">Loading...</p>}

        {data && (
          <>
            <section>
              <h3 className="mb-2 font-semibold">Latency (ms)</h3>
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={latency}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="retrieval" fill="#3b82f6" />
                    <Bar dataKey="total" fill="#10b981" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section>
              <h3 className="mb-2 font-semibold">Estimated daily cost (USD, last 30 days)</h3>
              <div className="h-56">
                <ResponsiveContainer>
                  <LineChart data={cost}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="cost" stroke="#f59e0b" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section>
              <h3 className="mb-2 font-semibold">Evaluation metrics</h3>
              <div className="h-64">
                <ResponsiveContainer>
                  <RadarChart data={radar}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="metric" />
                    <PolarRadiusAxis domain={[0, 1]} />
                    <Radar dataKey="score" stroke="#6366f1" fill="#6366f1" fillOpacity={0.4} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section>
              <h3 className="mb-2 font-semibold">Recent failed runs</h3>
              {failed.length === 0 && <p className="text-sm text-gray-500">No failed runs.</p>}
              <ul className="space-y-2">
                {failed.slice(0, 5).map((r) => (
                  <li key={r.run_id} className="rounded bg-red-50 p-2 text-sm">
                    <div className="font-medium text-red-700">{r.status}</div>
                    <div className="line-clamp-2">{r.query}</div>
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
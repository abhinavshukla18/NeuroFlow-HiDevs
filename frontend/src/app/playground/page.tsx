"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSSEStream, StreamState } from "@/hooks/useSSEStream";
import EvalGauges from "@/components/EvalGauges";
import CitationDrawer, { citationNumber } from "@/components/CitationDrawer";
import { diffWords } from "@/lib/diff";

type Pipeline = { id: string; name: string; avg_overall_score: string | null };

function Panel({
  title,
  stream,
  runId,
  onCite,
}: {
  title?: string;
  stream: StreamState;
  runId: string | null;
  onCite: (c: any, i: number, sources: any[]) => void;
}) {
  const [rated, setRated] = useState<number | null>(null);

  async function rate(v: number) {
    if (!runId) return;
    await api.patch(`/runs/${runId}/rating`, { rating: v });
    setRated(v);
  }

  return (
    <div className="space-y-3">
      {title && <h2 className="font-semibold">{title}</h2>}
      {stream.status === "retrieving" && <p className="text-sm text-gray-500">Retrieving sources...</p>}

      {stream.sources.length > 0 && (
        <div className="space-y-2 rounded border bg-white p-3">
          <h3 className="font-semibold">Retrieved sources ({stream.sources.length})</h3>
          {stream.sources.map((s: any, i: number) => (
            <div key={i} className="rounded bg-gray-50 p-2 text-sm">
              <div className="font-medium">
                [Source {i + 1}] {s.filename ?? s.document_name ?? s.title ?? ""}
                {(s.score ?? s.relevance ?? s.rrf_score) != null && (
                  <span className="ml-2 text-gray-500">
                    {Number(s.score ?? s.relevance ?? s.rrf_score).toFixed(3)}
                  </span>
                )}
              </div>
              <div className="line-clamp-2 text-gray-600">{s.content ?? s.text ?? s.chunk ?? ""}</div>
            </div>
          ))}
        </div>
      )}

      {(stream.answer || stream.status === "streaming") && (
        <div className="whitespace-pre-wrap rounded border bg-white p-3">
          {stream.answer}
          {stream.status === "streaming" && <span className="animate-pulse">▍</span>}
        </div>
      )}

      {stream.citations.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {stream.citations.map((c: any, i: number) => (
            <button
              key={i}
              onClick={() => onCite(c, i, stream.sources)}
              className="rounded-full bg-blue-100 px-3 py-1 text-sm text-blue-800 hover:bg-blue-200"
            >
              Source {citationNumber(c, i)}
            </button>
          ))}
        </div>
      )}

      {stream.status === "error" && <p className="text-red-600">Error: {stream.error}</p>}

      {stream.status === "done" && runId && (
        <>
          <EvalGauges runId={runId} />
          <div className="flex gap-3">
            <button onClick={() => rate(5)} className={`rounded border px-3 py-1 ${rated === 5 ? "bg-green-200" : ""}`}>
              👍
            </button>
            <button onClick={() => rate(1)} className={`rounded border px-3 py-1 ${rated === 1 ? "bg-red-200" : ""}`}>
              👎
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default function Playground() {
  const [compare, setCompare] = useState(false);
  const [pipelineA, setPipelineA] = useState("");
  const [pipelineB, setPipelineB] = useState("");
  const [query, setQuery] = useState("");
  const [runA, setRunA] = useState<string | null>(null);
  const [runB, setRunB] = useState<string | null>(null);
  const [cite, setCite] = useState<{ c: any; i: number; sources: any[] } | null>(null);
  const A = useSSEStream();
  const B = useSSEStream();

  const { data: pipelines = [] } = useQuery<Pipeline[]>({
    queryKey: ["pipelines"],
    queryFn: async () => (await api.get("/pipelines")).data,
  });

  async function launch(pid: string, stream: ReturnType<typeof useSSEStream>, setRun: (id: string) => void) {
    const res = await api.post("/query", { query, pipeline_id: pid || null, stream: true });
    setRun(res.data.run_id);
    stream.start(res.data.run_id);
  }

  async function run() {
    if (!query.trim()) return;
    setRunA(null);
    setRunB(null);
    await Promise.all([
      launch(pipelineA, A, setRunA),
      compare ? launch(pipelineB, B, setRunB) : Promise.resolve(),
    ]);
  }

  const busy = [A, B].some((s) => s.status === "retrieving" || s.status === "streaming");
  const bothDone = compare && A.status === "done" && B.status === "done";
  const diff = bothDone ? diffWords(A.answer, B.answer) : null;

  const selector = (value: string, set: (v: string) => void) => (
    <select className="w-full rounded border bg-white p-2" value={value} onChange={(e) => set(e.target.value)}>
      <option value="">Default pipeline</option>
      {pipelines.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name} {p.avg_overall_score ? `(score ${p.avg_overall_score})` : ""}
        </option>
      ))}
    </select>
  );

  return (
    <div className={`mx-auto space-y-4 ${compare ? "max-w-6xl" : "max-w-3xl"}`}>
      <h1 className="text-2xl font-bold">Query Playground</h1>

      <div className={`grid gap-3 ${compare ? "grid-cols-2" : "grid-cols-1"}`}>
        {selector(pipelineA, setPipelineA)}
        {compare && selector(pipelineB, setPipelineB)}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
        Compare mode
      </label>

      <div>
        <textarea
          className="h-32 w-full rounded border bg-white p-2"
          placeholder="Ask a question..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={2000}
        />
        <div className="text-right text-xs text-gray-500">{query.length}/2000</div>
      </div>

      <button
        onClick={run}
        disabled={busy || !query.trim()}
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
      >
        {busy ? "Running..." : "Run query"}
      </button>

      <div className={`grid gap-4 ${compare ? "grid-cols-2" : "grid-cols-1"}`}>
        <Panel
          key={runA ?? "a"}
          title={compare ? "Pipeline A" : undefined}
          stream={A}
          runId={runA}
          onCite={(c, i, sources) => setCite({ c, i, sources })}
        />
        {compare && (
          <Panel
            key={runB ?? "b"}
            title="Pipeline B"
            stream={B}
            runId={runB}
            onCite={(c, i, sources) => setCite({ c, i, sources })}
          />
        )}
      </div>

      {diff && (
        <div className="space-y-2 rounded border bg-white p-3">
          <h2 className="font-semibold">Where the answers diverge</h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            {[diff.left, diff.right].map((toks, k) => (
              <p key={k} className="leading-relaxed">
                {toks.map((t, i) => (
                  <span key={i} className={t.changed ? (k === 0 ? "bg-red-200" : "bg-green-200") : ""}>
                    {t.text}{" "}
                  </span>
                ))}
              </p>
            ))}
          </div>
        </div>
      )}

      {cite && (
        <CitationDrawer citation={cite.c} index={cite.i} sources={cite.sources} onClose={() => setCite(null)} />
      )}
    </div>
  );
}
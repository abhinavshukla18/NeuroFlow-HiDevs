"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

const METRICS = ["faithfulness", "answer_relevance", "context_precision", "context_recall"] as const;
const C = 2 * Math.PI * 28;

function Gauge({ label, value }: { label: string; value: number | null }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setV(value ?? 0), 50);
    return () => clearTimeout(t);
  }, [value]);
  const stroke = v > 0.8 ? "#22c55e" : v >= 0.6 ? "#eab308" : "#ef4444";
  return (
    <div className="flex flex-col items-center text-xs">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="28" fill="none" stroke="#e5e7eb" strokeWidth="7" />
        <circle
          cx="36"
          cy="36"
          r="28"
          fill="none"
          stroke={stroke}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - v)}
          transform="rotate(-90 36 36)"
          style={{ transition: "stroke-dashoffset 1s ease-out" }}
        />
        <text x="36" y="40" textAnchor="middle" fontSize="14" fontWeight="600">
          {value !== null ? value.toFixed(2) : "-"}
        </text>
      </svg>
      <span>{label.replace("_", " ")}</span>
    </div>
  );
}

export default function EvalGauges({ runId }: { runId: string }) {
  const { data } = useQuery<Record<string, number | null> | null>({
    queryKey: ["eval", runId],
    queryFn: async () => {
      try {
        return (await api.get(`/evaluations/${runId}`)).data;
      } catch {
        return null;
      }
    },
    refetchInterval: (q) => (q.state.data ? false : 2000),
  });

  if (!data) return <p className="text-sm text-gray-500">Evaluating...</p>;
  return (
    <div className="flex flex-wrap justify-around gap-2 rounded border bg-white p-3">
      {METRICS.map((m) => (
        <Gauge key={m} label={m} value={(data[m] as number | null) ?? null} />
      ))}
    </div>
  );
}
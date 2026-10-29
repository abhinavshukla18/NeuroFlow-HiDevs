"use client";

import { useCallback, useRef, useState } from "react";
import { API_URL, withToken } from "@/lib/api";

export type StreamState = {
  status: "idle" | "retrieving" | "streaming" | "done" | "error";
  sources: any[];
  answer: string;
  citations: any[];
  error?: string;
};

const initial: StreamState = { status: "idle", sources: [], answer: "", citations: [] };

export function useSSEStream() {
  const [state, setState] = useState<StreamState>(initial);
  const esRef = useRef<EventSource | null>(null);

  const start = useCallback((runId: string) => {
    esRef.current?.close();
    setState({ ...initial, status: "retrieving" });
    const es = new EventSource(withToken(`${API_URL}/query/${runId}/stream`));
    esRef.current = es;

    es.onmessage = (e) => {
      const ev = JSON.parse(e.data);
      setState((s) => {
        switch (ev.type) {
          case "retrieval_complete":
            return { ...s, sources: ev.sources ?? [], status: "streaming" };
          case "token":
            return { ...s, answer: s.answer + ev.delta, status: "streaming" };
          case "done":
            return { ...s, citations: ev.citations ?? [], status: "done" };
          case "error":
            return { ...s, status: "error", error: ev.message };
          default:
            return s;
        }
      });
      if (ev.type === "done" || ev.type === "error") es.close();
    };

    es.onerror = () => {
      es.close();
      setState((s) =>
        s.status === "done" ? s : { ...s, status: "error", error: "Stream connection failed" }
      );
    };
  }, []);

  return { ...state, start };
}
"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function Login() {
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    try {
      const res = await api.post("/auth/token", { client_id: clientId, client_secret: secret });
      localStorage.setItem("nf_token", res.data.access_token);
      location.href = "/playground";
    } catch {
      setError("Invalid credentials");
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-3 rounded border bg-white p-6">
      <h1 className="text-xl font-bold">Sign in</h1>
      <input className="w-full rounded border p-2" placeholder="Client ID" value={clientId}
        onChange={(e) => setClientId(e.target.value)} />
      <input className="w-full rounded border p-2" type="password" placeholder="Client secret" value={secret}
        onChange={(e) => setSecret(e.target.value)} />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button onClick={submit} className="w-full rounded bg-blue-600 py-2 text-white">Sign in</button>
    </div>
  );
}

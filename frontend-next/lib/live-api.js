/* Live engine client for the test bench (Next.js port).

   Mirrors frontend/assets/js/live-api.js — talks to the Flask endpoint in
   code/serve_api.py, which runs the REAL deterministic pipeline on demand so the
   bench can execute modified requests instead of replaying baseline.json.

   Local development supports ?api=http://host:port. Hosted builds use the
   configured API URL or their own origin, keeping account credentials local
   to the trusted deployment.
   Everything is SSR-safe: nothing touches window/location at module scope. */

import { authHeaders } from "./session";

const START_CMD = "python3 code/serve_api.py";

const LABELS = {
  amount: "AMOUNT SAFE TO PAY",
  status: "AFFORDABILITY STATUS",
  method: "PAYMENT METHOD",
  plan: "PAYMENT PLAN",
  earliest: "EARLIEST FULL PAYMENT",
  spending: "SPENDING CHANGES",
  explanation: "EXPLANATION",
};

export function apiBase() {
  if (typeof window === "undefined") return process.env.NEXT_PUBLIC_KAIROS_API || "";
  const params = new URLSearchParams(window.location.search);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
  const fallback = process.env.NEXT_PUBLIC_KAIROS_API || window.KAIROS_API || (local ? "http://127.0.0.1:8000" : "");
  return String((local && params.get("api")) || fallback).replace(/\/+$/, "");
}

/* health probe with a hard timeout so an absent server never hangs the page */
export async function health(timeoutMs = 1500) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(apiBase() + "/api/health", { signal: ctrl.signal });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export async function requests() {
  const res = await fetch(apiBase() + "/api/requests");
  if (!res.ok) throw new Error("HTTP " + res.status);
  const body = await res.json();
  return body.requests || [];
}

/* run the real pipeline, optionally over a modified request */
export async function decide(payload) {
  const res = await fetch(apiBase() + "/api/decide", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok || !body || body.ok === false) {
    throw new Error((body && body.error) || "engine request failed: HTTP " + res.status);
  }
  return body;
}

function brief(value, limit = 90) {
  const text = String(value === null || value === undefined ? "—" : value).replace(/\s+/g, " ").trim();
  return text.length > limit ? text.slice(0, limit - 1) + "…" : text;
}

/* human-readable field-level delta between the submitted baseline and the live run */
export function deltas(result) {
  return (result.changed || []).map((field) => ({
    field,
    label: LABELS[field] || field.toUpperCase(),
    from: brief(result.baseline ? result.baseline[field] : ""),
    to: brief(result.decision[field]),
  }));
}

export const LIVE = { START_CMD, apiBase, health, requests, decide, deltas, brief };

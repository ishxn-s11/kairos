/* Live engine client for the test bench.

   Talks to the Flask endpoint in code/serve_api.py, which runs the REAL
   deterministic pipeline on demand so the bench can execute modified requests
   (new amount / request date / partial-payment flag) instead of replaying
   baseline.json. Pure logic — no DOM — so the static page and the Next.js port
   share one implementation (browser global: window.LiveAPI).

   The base URL defaults to the local server; override with window.KAIROS_API
   or ?api=http://host:port on the page URL. */
(() => {
  const params = new URLSearchParams(location.search);
  const DEFAULT_BASE = (typeof window !== "undefined" && window.KAIROS_API) || "http://127.0.0.1:8000";
  const BASE = String(params.get("api") || DEFAULT_BASE).replace(/\/+$/, "");

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

  /* health probe with a hard timeout so an absent server never hangs the page */
  async function health(timeoutMs = 1500) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(BASE + "/api/health", { signal: ctrl.signal });
      if (!res.ok) return null;
      return await res.json();
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  async function requests() {
    const res = await fetch(BASE + "/api/requests");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const body = await res.json();
    return body.requests || [];
  }

  /* run the real pipeline, optionally over a modified request */
  async function decide(payload) {
    const res = await fetch(BASE + "/api/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
  function deltas(result) {
    return (result.changed || []).map((field) => ({
      field,
      label: LABELS[field] || field.toUpperCase(),
      from: brief(result.baseline ? result.baseline[field] : ""),
      to: brief(result.decision[field]),
    }));
  }

  /* normalize an API payload into the shape the decision renderer already uses */
  function adapt(row) {
    return {
      request_id: row.request_id,
      status: row.status,
      method: row.method,
      amount: row.amount,
      plan: row.plan,
      earliest: row.earliest,
      spending: row.spending,
      explanation: row.explanation,
    };
  }

  window.LiveAPI = { BASE, START_CMD, health, requests, decide, deltas, adapt, brief };
})();

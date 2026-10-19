"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { LIVE } from "../../lib/live-api";
import { authHeaders, clearSession, getToken, saveSession } from "../../lib/session";

const empty = { name: "", email: "", password: "" };

async function api(path, options = {}) {
  const res = await fetch(`${LIVE.apiBase()}${path}`, {
    ...options,
    headers: authHeaders({ "Content-Type": "application/json", ...(options.headers || {}) }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

const ACTION_LABELS = {
  register: "Account created",
  login: "Signed in",
  decision_run: "Decision calculated",
  report_run: "Report generated",
  scenarios_run: "Scenarios compared",
};

function prettyTime(value) {
  try { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
  catch { return value; }
}

export default function AccountPage() {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState(empty);
  const [user, setUser] = useState(null);
  const [activity, setActivity] = useState([]);
  const [stats, setStats] = useState({ total_actions: 0, decisions: 0 });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [online, setOnline] = useState(null);

  const initials = useMemo(() => user?.name?.split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "K", [user]);

  const loadAccount = async () => {
    if (!getToken()) return;
    try {
      const [me, log] = await Promise.all([api("/api/auth/me"), api("/api/activity")]);
      setUser(me.user);
      setStats(me.stats || {});
      setActivity(log.actions || []);
    } catch (err) {
      clearSession();
      setUser(null);
      setMessage(err.message);
    }
  };

  useEffect(() => {
    let alive = true;
    LIVE.health().then((h) => { if (alive) setOnline(!!h); });
    loadAccount();
    return () => { alive = false; };
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const payload = mode === "register"
        ? { name: form.name, email: form.email, password: form.password }
        : { email: form.email, password: form.password };
      const body = await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(payload) });
      saveSession(body.token, body.user);
      setUser(body.user);
      setForm(empty);
      setMessage(mode === "register" ? "Account created. Your decisions can now be saved to this profile." : "Welcome back.");
      await loadAccount();
    } catch (err) {
      setMessage(err.message);
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } catch { /* local logout still succeeds */ }
    clearSession();
    setUser(null);
    setActivity([]);
    setStats({ total_actions: 0, decisions: 0 });
    setMessage("Signed out safely.");
  };

  if (user) {
    return (
      <main className="account-page">
        <section className="account-shell account-dashboard">
          <div className="account-profile">
            <div className="profile-avatar">{initials}</div>
            <div><span className="section-kicker">Your Kairos account</span><h1>{user.name}</h1><p>{user.email}</p></div>
            <button className="secondary-button" onClick={logout}>Log out</button>
          </div>
          <div className="account-stats">
            <article><strong>{stats.decisions || 0}</strong><span>decisions run</span></article>
            <article><strong>{stats.total_actions || 0}</strong><span>account actions</span></article>
            <article><strong>Private</strong><span>local account data</span></article>
          </div>
          <div className="activity-panel">
            <div className="activity-heading"><div><span className="section-kicker">Activity ledger</span><h2>What you’ve done</h2></div><Link className="primary-cta small" href="/test">Run a decision <span>↗</span></Link></div>
            {activity.length ? (
              <div className="activity-list">
                {activity.map((item) => (
                  <article key={item.id}>
                    <span className="activity-mark">{item.action === "decision_run" ? "K" : "✓"}</span>
                    <div><strong>{ACTION_LABELS[item.action] || item.action.replaceAll("_", " ")}</strong><p>{item.details?.request_id ? `${item.details.request_id} · ${item.details.status || "completed"}` : "Account activity"}</p></div>
                    <time>{prettyTime(item.created_at)}</time>
                  </article>
                ))}
              </div>
            ) : <div className="activity-empty">No decisions yet. Your authenticated test-bench runs will appear here.</div>}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="account-page">
      <section className="account-shell auth-layout">
        <div className="auth-story">
          <span className="section-kicker">Personal decision history</span>
          <h1>Money decisions,<br /><em>remembered.</em></h1>
          <p>Create a private Kairos account to keep an auditable history of every decision, report, and scenario you run.</p>
          <div className="auth-benefits"><span>01</span><b>Private by default</b><span>02</span><b>Passwords securely hashed</b><span>03</span><b>Actions tied to your account</b></div>
        </div>
        <div className="auth-card">
          <div className="auth-tabs">
            <button className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setMessage(""); }}>Log in</button>
            <button className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setMessage(""); }}>Register</button>
          </div>
          <form onSubmit={submit}>
            <div className={`backend-state ${online === false ? "offline" : ""}`}><i></i>{online === null ? "Checking backend…" : online ? "Secure backend connected" : "Backend offline — start code/serve_api.py"}</div>
            {mode === "register" ? <label><span>Name</span><input required minLength={2} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name" /></label> : null}
            <label><span>Email</span><input required type="email" autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" /></label>
            <label><span>Password</span><input required minLength={8} type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="At least 8 characters" /></label>
            {message ? <p className="auth-message" role="status">{message}</p> : null}
            <button className="auth-submit" disabled={busy || online === false}>{busy ? "Please wait…" : mode === "register" ? "Create account" : "Log in"}<span>↗</span></button>
          </form>
          <p className="auth-footnote">Kairos stores only your account and action history. Financial calculations remain deterministic.</p>
        </div>
      </section>
    </main>
  );
}

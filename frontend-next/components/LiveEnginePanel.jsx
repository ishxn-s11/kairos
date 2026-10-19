"use client";

import { useEffect, useRef, useState } from "react";
import { LIVE } from "../lib/live-api";
import { STATUS_COLOR } from "../lib/decisions";

/* Live engine panel: runs modified requests through the real Python pipeline
   (code/serve_api.py) and diffs the answer against the submitted baseline.
   Mirrors frontend/assets/js/live-ui.js. */

const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });

const planRows = (plan) => (!plan || plan === "none"
  ? []
  : plan.split("|").map((p) => {
      const [date, amount] = p.split(":");
      return { date, amount };
    }));

export default function LiveEnginePanel() {
  const [online, setOnline] = useState(null); // null = probing
  const [health, setHealth] = useState(null);
  const [pick, setPick] = useState("");
  const [amt, setAmt] = useState("");
  const [date, setDate] = useState("");
  const [partial, setPartial] = useState(false);
  const [result, setResult] = useState(null);
  const [msg, setMsg] = useState("PROBING THE LIVE ENGINE…");
  const [busy, setBusy] = useState(false);
  const [autoRun, setAutoRun] = useState(false);

  const indexRef = useRef(new Map());
  const loadedRef = useRef(false);
  const ref = useRef({});
  ref.current = { pick, amt, date, partial };

  const loadIndex = async () => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    try {
      (await LIVE.requests()).forEach((r) => indexRef.current.set(r.request_id, r));
    } catch { /* the form still works if the index call fails */ }
  };

  const writeURL = (payload) => {
    if (typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search);
    p.set("lv", "1");
    p.set("id", payload.request_id);
    if (payload.requested_amount !== undefined) p.set("amt", payload.requested_amount); else p.delete("amt");
    if (payload.request_date) p.set("date", payload.request_date); else p.delete("date");
    if (payload.allows_partial_payment !== undefined) p.set("partial", payload.allows_partial_payment ? "1" : "0"); else p.delete("partial");
    const qs = p.toString();
    history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : ""));
  };

  const runLive = async () => {
    const { pick: pick0, amt: amt0, date: date0, partial: partial0 } = ref.current;
    const id = (pick0 || "").trim();
    if (!id) { setMsg("PICK A REQUEST ID FIRST."); return; }
    await loadIndex();
    const row = indexRef.current.get(id);
    if (!row) { setMsg(`UNKNOWN REQUEST ${id} — PICK ONE FROM THE LIST.`); return; }

    const payload = { request_id: id };
    if (amt0 && Number(amt0) !== Number(row.requested_amount)) payload.requested_amount = amt0;
    if (date0 && date0 !== row.request_date) payload.request_date = date0;
    if (partial0 !== !!row.allows_partial_payment) payload.allows_partial_payment = partial0;

    setBusy(true);
    setMsg("RUNNING THE REAL PIPELINE…");
    try {
      const res = await LIVE.decide(payload);
      setResult(res);
      setMsg("");
      writeURL(payload);
    } catch (err) {
      setMsg(`ENGINE ERROR — ${String((err && err.message) || err)}`);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    let dead = false;
    (async () => {
      const h = await LIVE.health();
      if (dead) return;
      setHealth(h);
      setOnline(!!h);
      if (!h) {
        setMsg(`LIVE ENGINE OFFLINE — start it with ${LIVE.START_CMD} (expected at ${LIVE.apiBase()}). The baseline bench above still works.`);
        return;
      }
      const params = new URLSearchParams(window.location.search);
      if (params.get("lv") !== "1" || !params.get("id")) {
        setMsg("SHAREABLE RUNS: the URL records the request, amount, date and partial flag. Try request_26 ×5 (affordable_now → not_affordable) or request_28 ×0.5 (not_affordable → affordable_later).");
        return;
      }
      setMsg("RESTORING THE SHARED LIVE RUN…");
      const id = params.get("id");
      setPick(id);
      await loadIndex();
      const row = indexRef.current.get(id);
      if (!row) { setMsg(`UNKNOWN REQUEST ${id} IN THIS LINK.`); return; }
      setAmt(params.get("amt") || row.requested_amount);
      setDate(params.get("date") || row.request_date);
      setPartial(params.get("partial") ? params.get("partial") === "1" : !!row.allows_partial_payment);
      setAutoRun(true);
    })();
    return () => { dead = true; };
  }, []);

  /* deep link: run once the inputs from the URL have been applied */
  useEffect(() => {
    if (!autoRun) return;
    setAutoRun(false);
    runLive();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRun]);

  const multiply = (k) => {
    const value = Number(ref.current.amt);
    if (!value) return;
    setAmt(String(Math.round(value * k * 100) / 100));
  };

  const changes = result ? LIVE.deltas(result) : [];
  const overrides = result ? result.modified || [] : [];
  const live = result ? result.decision : null;
  const shownPlan = live ? planRows(live.plan) : [];

  return (
    <div className="tb-live res-block">
      <h2>
        LIVE ENGINE{" "}
        <span className="tb-live-state" data-state={online === null ? "checking" : online ? "online" : "offline"}>
          {online === null ? "CHECKING…" : online ? `ONLINE · ${health.requests} REQUESTS · ${LIVE.apiBase().replace(/^https?:\/\//, "")}` : "OFFLINE"}
        </span>
      </h2>
      <p className="res-sub">
        The same real Python pipeline, executed on demand. Change the requested amount, move the
        request date, or toggle partial payment and the engine decides again — then diff the answer
        against the submitted baseline. Start it with <code>{LIVE.START_CMD}</code>; without it the
        bench stays on baseline.json.
      </p>

      <div className="tb-controls">
        <input
          list="tbList"
          placeholder="request id (e.g. request_26)"
          value={pick}
          disabled={online === false}
          onChange={async (e) => {
            const value = e.target.value;
            setPick(value);
            await loadIndex();
            const row = indexRef.current.get(value.trim());
            if (row) {
              setAmt(row.requested_amount);
              setDate(row.request_date);
              setPartial(!!row.allows_partial_payment);
              setMsg("DATASET VALUES LOADED — CHANGE ANYTHING, THEN RUN LIVE.");
            }
          }}
        />
        <input
          type="number" min="0" step="0.01" placeholder="requested amount" value={amt}
          disabled={online === false}
          onChange={(e) => setAmt(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") runLive(); }}
        />
        <input
          type="date" value={date} disabled={online === false}
          onChange={(e) => setDate(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") runLive(); }}
        />
        <label className="tb-toggle">
          <input type="checkbox" checked={partial} disabled={online === false} onChange={(e) => setPartial(e.target.checked)} /> ALLOW PARTIAL PAYMENT
        </label>
        <button disabled={online === false} onClick={() => multiply(0.5)}>×0.5</button>
        <button disabled={online === false} onClick={() => multiply(2)}>×2</button>
        <button disabled={online === false} onClick={() => multiply(5)}>×5</button>
        <button
          disabled={online === false}
          onClick={async () => {
            await loadIndex();
            const row = indexRef.current.get(pick.trim());
            if (row) {
              setAmt(row.requested_amount);
              setDate(row.request_date);
              setPartial(!!row.allows_partial_payment);
              setMsg("DATASET VALUES RESTORED — RUN LIVE TO RE-DECIDE.");
            }
          }}
        >
          DATASET VALUES
        </button>
        <button className="hot" disabled={online === false || busy} onClick={runLive}>RUN LIVE &gt;</button>
      </div>

      <div className="tb-out">
        {msg ? <div className="tb-hint">{msg}</div> : null}
        {live ? (
          <div className="tb-decision">
            <div className="dec-top">
              <b>{live.request_id}</b>
              <span className="lv-tag">LIVE</span>
              <span className="dec-status" style={{ "--sc": STATUS_COLOR[live.status] || "#fff" }}>{live.status}</span>
            </div>
            <div className="dec-facts">
              <div><i>AMOUNT SAFE TO PAY</i><span className="ev-amt">{live.amount}</span></div>
              <div><i>METHOD</i><span>{live.method}</span></div>
              <div><i>EARLIEST FULL PAYMENT</i><span>{live.earliest || "—"}</span></div>
              <div><i>SPENDING CHANGES</i><span>{live.spending}</span></div>
            </div>
            <div className="lv-request">
              <i>REQUEST AS EXECUTED</i>
              <span>
                {result.request.request_date} · {fmt(result.request.requested_amount)} {result.request.home_currency}
                {" · "}partial {result.request.allows_partial_payment ? "allowed" : "not allowed"}
                {overrides.length ? ` · overridden: ${overrides.join(", ")}` : ""}
              </span>
            </div>
            <table className="dec-plan">
              <thead><tr><th>#</th><th>DATE</th><th>AMOUNT</th></tr></thead>
              <tbody>
                {shownPlan.length
                  ? shownPlan.map((p, i) => (
                      <tr key={i}><td>{i + 1}</td><td>{p.date}</td><td className="ev-amt">{fmt(p.amount)}</td></tr>
                    ))
                  : <tr><td colSpan={3} className="dec-none">none</td></tr>}
              </tbody>
            </table>
            <div className="dec-expl-full"><i>DECISION EXPLANATION (LIVE ENGINE)</i>{live.explanation}</div>

            {changes.length ? (
              <div className="tb-cmp diff lv-delta-panel">
                <b>LIVE ENGINE — {changes.length} FIELD{changes.length === 1 ? "" : "S"} CHANGED VS SUBMITTED BASELINE</b>
                <ul className="lv-delta">
                  {changes.map((c) => (
                    <li key={c.field}>
                      <i>{c.label}</i>
                      <span className="lv-from">{c.from}</span>
                      <span className="lv-arrow">→</span>
                      <span className="lv-to">{c.to}</span>
                    </li>
                  ))}
                </ul>
                <pre>{result.baseline ? result.baseline.explanation : ""}</pre>
              </div>
            ) : (
              <div className="tb-cmp ok lv-delta-panel">
                <b>LIVE ENGINE — IDENTICAL TO THE SUBMITTED BASELINE</b>
                <p className="lv-note">
                  {overrides.length
                    ? "The override did not change the decision — the ledger absorbs it."
                    : "No overrides applied: this is the same request the agent answered."}
                </p>
              </div>
            )}

            <div className="lv-usage">
              engine report — model calls: {result.usage.calls_for_this_run} · tokens: {result.usage.tokens_total} · cost: ${result.usage.cost_usd_total} · deterministic pipeline
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
